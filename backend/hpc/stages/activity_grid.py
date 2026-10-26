"""
Part B from the dashboard's Activities grid: per subject, an activity and three levels.

Grid values (kept in the teacher's draft, never in Excel):
  b_act_<subject>               library key of the activity: "P85" (PARAKH bank) or "T40321" (teacher's own)
  b_lvl_<subject>_<ability>     Beginner | Proficient | Advanced   (ability: awareness, sensitivity, creativity)
  b_replace                     "Yes" lets the save remove activities on PARAKH that the grid no longer uses

PARAKH stores levels per activity, not per subject, so subjects are grouped by (activity, levels):
the same activity with the same levels is sent once with those subjects; with different levels it
is sent as separate activities (PARAKH allows the same activity twice). Activities already on PARAKH
are kept whenever they still fit, with their own answers; an activity is only removed with b_replace.
The student's other Part B answers (the Excel columns) go into new or changed activities and into
the first activity, as the workbook always did.
"""
import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.hpc.stages.activity import bank_dt, filled

ABILITIES = (("awareness", "awr"), ("sensitivity", "sen"), ("creativity", "cre"))
LEVEL_TO_PORTAL = {"Beginner": "beginner", "Proficient": "proficient", "Advanced": "advance"}
PORTAL_TO_LEVEL = {v: k for k, v in LEVEL_TO_PORTAL.items()}
REPLACE_KEY = "b_replace"

# key -> {"portal_id", "caption", "content", "is_global", "usable", "reason"}, or None when unknown
Resolver = Callable[[str], Optional[Dict[str, Any]]]


@dataclass
class GridSpec:
    """What a stage's Part B needs besides the shared activity code."""
    blank: Callable[[], Dict[str, Any]]
    shared: Tuple[str, ...]                          # dt keys that hold the student's own answers
    from_bank: Callable[[Dict[str, Any]], Dict[str, Any]] = lambda content: {}
    shared_any_other: Tuple[int, ...] = ()           # Middle: any_other[1] and [2] are the student's, [0] the activity's
    derive: Callable[[Dict[str, Any]], None] = lambda dt: None    # values the stage computes from the levels


def act_key(subject: str) -> str:
    return f"b_act_{subject}"


def level_key(subject: str, ability: str) -> str:
    return f"b_lvl_{subject}_{ability}"


def grid_keys(subjects: List[str]) -> List[str]:
    return [k for s in subjects for k in (act_key(s), *(level_key(s, a) for a, _ in ABILITIES))] + [REPLACE_KEY]


def check_value(key: str, value: Any) -> Optional[str]:
    """Problem with one grid value, or None. Blank always means "not chosen yet"."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    if key.startswith("b_act_"):
        return None if portal_id(text) is not None else "Choose an activity from the list."
    if key.startswith("b_lvl_"):
        return None if text in LEVEL_TO_PORTAL else "Choose Beginner, Proficient or Advanced."
    if key == REPLACE_KEY:
        return None if text.lower() in ("yes", "no", "true", "false") else "Use Yes or No."
    return "Unknown field."


def key_for(bank_id: Any, is_global: Any) -> str:
    return f"{'T' if is_global is False else 'P'}{int(bank_id)}"


def portal_id(key: str) -> Optional[int]:
    return int(key[1:]) if key and key[0] in "PT" and key[1:].isdigit() else None


def _real(act: Dict[str, Any]) -> bool:
    dt = act.get("dt") or {}
    return bool(dt.get("act_bank_id") or dt.get("domain"))


# ---------------------------------------------------------------------------
# What PARAKH holds now, shown one subject per column
# ---------------------------------------------------------------------------

@dataclass
class Current:
    values: Dict[str, str]                           # grid keys -> values
    existing: List[Dict[str, Any]] = field(default_factory=list)
    locked: bool = False                             # a subject is covered by more than one activity


def current(subjects: List[str], fd: List[Dict[str, Any]]) -> Current:
    acts = [a for a in fd or [] if _real(a)]
    values: Dict[str, str] = {}
    cover: Dict[str, int] = {}
    existing = []
    for i, act in enumerate(acts):
        dt = act["dt"]
        bank = dt.get("act_bank_id")
        key = key_for(bank, dt.get("is_global")) if str(bank or "").isdigit() else ""
        domains = [s for s in subjects if s in (dt.get("domain") or [])]
        existing.append({"key": key, "name": act.get("nm") or "Activity", "subjects": domains,
                         "complete": bool(act.get("is_complete")), "from_bank": bool(key)})
        for s in domains:
            cover[s] = cover.get(s, 0) + 1
            if act_key(s) in values or not key:
                continue                             # first activity wins; teacher-typed ones have no key
            values[act_key(s)] = key
            for ability, short in ABILITIES:
                level = PORTAL_TO_LEVEL.get(str((dt.get(short) or ["", "", "", ""])[3]).strip(), "")
                if level:
                    values[level_key(s, ability)] = level
    return Current(values, existing, locked=any(n > 1 for n in cover.values()))


def effective(subjects: List[str], now: Current, draft: Dict[str, Any], part_c_levels: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Grid values to use and where each came from: the teacher's draft, PARAKH, or the student's Part C."""
    values, source = {}, {}
    for key in grid_keys(subjects):
        if key in draft and draft[key] not in (None,):
            values[key], source[key] = str(draft[key] or ""), "draft"
        elif now.values.get(key):
            values[key], source[key] = now.values[key], "portal"
        elif key in part_c_levels and part_c_levels[key]:
            values[key], source[key] = part_c_levels[key], "part_c"
        else:
            values[key], source[key] = "", ""
    return values, source


# ---------------------------------------------------------------------------
# Grid values -> PARAKH's activity list
# ---------------------------------------------------------------------------

@dataclass
class Plan:
    activities: List[Dict[str, Any]]
    changes: List[Dict[str, Any]]                    # {"action": keep|update|add|remove, "name", "subjects"}
    errors: List[str]


def plan(subjects: List[str], names: Dict[str, str], spec: GridSpec, fd: List[Dict[str, Any]],
         values: Dict[str, str], resolve: Resolver) -> Plan:
    """Pure: works out the new activity list. Nothing is changed when there are errors."""
    now = current(subjects, fd)
    replace = str(values.get(REPLACE_KEY, "")).strip().lower() in ("yes", "true", "1")
    errors: List[str] = []
    if now.locked and not replace:
        return Plan(fd, [], ["This student has activities on PARAKH that share subjects, so they cannot be shown "
                             "one per subject. Tick 'Replace activities on PARAKH' to use the ones chosen here instead."])

    # 1. groups of subjects with the same activity and levels, in subject order
    missing_activity, missing_levels = [], []
    groups: Dict[Tuple[str, Tuple[str, str, str]], List[str]] = {}
    for s in subjects:
        key = str(values.get(act_key(s)) or "").strip()
        levels = tuple(str(values.get(level_key(s, a)) or "").strip() for a, _ in ABILITIES)
        if not key:
            missing_activity.append(names[s])
            continue
        gaps = [label for (a, _), label, v in zip(ABILITIES, ("Awareness", "Sensitivity", "Creativity"), levels)
                if v not in LEVEL_TO_PORTAL]
        if gaps:
            missing_levels.append(f"{names[s]} ({', '.join(gaps)})")
            continue
        groups.setdefault((key, levels), []).append(s)
    if missing_activity:
        errors.append("No activity chosen for: " + ", ".join(missing_activity))
    if missing_levels:
        errors.append("Levels not chosen for: " + "; ".join(missing_levels))

    # 2. match groups to the activities PARAKH already has (exact subjects first, then same activity)
    existing = [(i, a) for i, a in enumerate(fd or []) if _real(a)]
    first = existing[0][0] if existing else None
    matched: Dict[Tuple[str, Tuple[str, str, str]], int] = {}
    used = set()
    for exact in (True, False):
        for gk, subs in groups.items():
            if gk in matched:
                continue
            for i, act in existing:
                dt = act["dt"]
                if i in used or str(dt.get("act_bank_id") or "") != str(portal_id(gk[0]) or "-"):
                    continue
                if exact and set(dt.get("domain") or []) != set(subs):
                    continue
                matched[gk] = i
                used.add(i)
                break

    # 3. build the new list
    shared_src = copy.deepcopy((fd[0] if fd else {"dt": spec.blank()})["dt"])
    out, changes = [], []
    for gk, subs in groups.items():
        key, levels = gk
        portal_levels = [LEVEL_TO_PORTAL[v] for v in levels]
        if gk in matched:
            i = matched[gk]
            act = copy.deepcopy(fd[i])
            dt = act["dt"]
            before = (sorted(dt.get("domain") or []), [str((dt.get(k) or ["", "", "", ""])[3]) for _, k in ABILITIES])
            changed = before != (sorted(subs), portal_levels)
            take_shared = changed or i == first
            changes.append({"action": "update" if changed else "keep", "name": act.get("nm") or key,
                            "subjects": [names[s] for s in subs]})
        else:
            entry = resolve(key)
            if entry is None:
                errors.append(f"The activity chosen for {', '.join(names[s] for s in subs)} is not in your Activity Library any more.")
                continue
            if not entry.get("usable", True):
                errors.append(f"'{entry['caption']}' cannot be added: {entry.get('reason') or 'not available'}")
                continue
            dt = bank_dt(spec.blank, entry["content"], int(entry["portal_id"]), bool(entry.get("is_global", True)),
                         spec.from_bank, portal_levels)
            act = {"nm": entry["caption"], "dt": dt, "is_modified": False}
            take_shared = True
            changes.append({"action": "add", "name": entry["caption"], "subjects": [names[s] for s in subs]})
        dt["domain"] = list(subs)
        for (_, k), level in zip(ABILITIES, portal_levels):
            texts = (list(dt.get(k) or []) + ["", "", "", ""])[:4]
            texts[3] = level
            dt[k] = texts
        if take_shared:
            for k in spec.shared:
                if k in shared_src:
                    dt[k] = copy.deepcopy(shared_src[k])
            if spec.shared_any_other:
                other = (list(dt.get("any_other") or []) + ["", "", ""])[:3]
                src = (list(shared_src.get("any_other") or []) + ["", "", ""])[:3]
                for n in spec.shared_any_other:
                    other[n] = src[n]
                dt["any_other"] = other
            spec.derive(dt)
        out.append(act)

    # 4. activities on PARAKH that the grid no longer uses
    for i, act in existing:
        if i in used:
            continue
        subs = [names.get(s, s) for s in (act["dt"].get("domain") or [])]
        label = f"'{act.get('nm') or 'Activity'}'" + (f" ({', '.join(subs)})" if subs else "")
        if replace:
            changes.append({"action": "remove", "name": act.get("nm") or "Activity", "subjects": subs})
        else:
            unfinished = "" if act.get("is_complete") or filled((act["dt"].get("desc") or [""])[0]) else " (it is not finished)"
            errors.append(f"Saving would remove activity {label}{unfinished} from PARAKH. "
                          "Choose it again, or tick 'Replace activities on PARAKH' to remove it.")

    if errors:
        return Plan(fd, changes, errors)
    return Plan(out, changes, [])


def apply(subjects: List[str], names: Dict[str, str], spec: GridSpec, fd: List[Dict[str, Any]],
          values: Dict[str, str], resolve: Resolver) -> List[str]:
    """Replaces fd's activities with the planned ones (in place); returns the errors."""
    result = plan(subjects, names, spec, fd, values, resolve)
    if not result.errors:
        fd[:] = result.activities
    return result.errors


def summary_text(subjects: List[str], names: Dict[str, str], values: Dict[str, str], labels: Dict[str, str]) -> str:
    """'Language 1 (R1), Mathematics: L1CG 1, C 1.1 (P/A/B) · ...' for the workbook's read-only column."""
    short = {"Beginner": "B", "Proficient": "P", "Advanced": "A"}
    groups: Dict[Tuple[str, str], List[str]] = {}
    for s in subjects:
        key = values.get(act_key(s), "")
        if key:
            lv = "/".join(short.get(values.get(level_key(s, a), ""), "-") for a, _ in ABILITIES)
            groups.setdefault((key, lv), []).append(names[s])
    out = [f"{', '.join(subs)}: {labels.get(key, key)} ({lv})" for (key, lv), subs in groups.items()]
    missing = [names[s] for s in subjects if not values.get(act_key(s))]
    if missing:
        out.append("Not chosen yet: " + ", ".join(missing))
    return " · ".join(out)


def from_old_columns(subjects: List[str], names: Dict[str, str], row: Dict[str, Any]) -> Dict[str, str]:
    """Grid values from a workbook made before the Activities tab (one Activity, Subjects and level columns)."""
    pid = str(row.get("b_activity") or "").split(":")[0].strip()
    if not pid.isdigit():
        return {}
    listed = [x.strip() for x in str(row.get("b_subjects") or "").split(",") if x.strip()]
    by_name = {n.lower(): s for s, n in names.items()}
    chosen = subjects if not listed or "all" in (x.lower() for x in listed) else \
        [by_name[x.lower()] for x in listed if x.lower() in by_name]
    out = {}
    for s in chosen:
        out[act_key(s)] = f"P{pid}"
        for (ability, _), col in zip(ABILITIES, ("b_awareness", "b_sensitivity", "b_creativity")):
            level = str(row.get(col) or "").strip()
            if level in LEVEL_TO_PORTAL:
                out[level_key(s, ability)] = level
    return out


def resolver_from_lookups(lookups) -> Resolver:
    """Activities PARAKH's own lists offer (the bank without picture activities)."""
    def resolve(key: str) -> Optional[Dict[str, Any]]:
        pid = portal_id(key)
        entry = lookups.activities.get(pid) if pid is not None else None
        if entry is None:
            return None
        return {"portal_id": pid, "caption": entry["activity_caption"], "content": entry["content"].get("dt") or {},
                "is_global": True, "usable": True, "reason": ""}
    return resolve
