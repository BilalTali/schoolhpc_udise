"""
Part B (activities) logic shared by both stages.

Part B formdata is a list of activities. The workbook edits the first activity; any
others the teacher added in the browser are kept as they are. An activity is copied
from the portal's Activity Bank the same way the page's "Use Activity" button does.
"""
from typing import Any, Callable, Dict, List

from backend.hpc.stages.common import StudentContext

ALL = "__ALL__"   # "All" in the Subjects column


def filled(value: Any) -> bool:
    return bool(str(value if value is not None else "").strip())


def has_value(value: Any) -> bool:
    """True if a cell/list holds something a teacher entered (not just blanks or zeros)."""
    if isinstance(value, list):
        return any(has_value(v) for v in value)
    return filled(value) and str(value).strip() != "0"


def rubric_ok(entry: List[str]) -> bool:
    """awr/sen/cre: three descriptor texts plus a chosen level whose descriptor is filled."""
    if len(entry) < 4 or not all(filled(t) for t in entry[:3]):
        return False
    idx = {"beginner": 0, "proficient": 1, "advance": 2}.get(str(entry[3]).strip())
    return idx is not None and filled(entry[idx])


def activity_id(hpc_id: str, domains: List[str], ctx: StudentContext, n: int) -> str:
    """Portal rule: {hpc_id}_{sorted domain ids joined}_{n}."""
    ids = sorted({d["id"] for d in ctx.lookups.domains if d["ent_code"] in domains})
    return f"{hpc_id}_{''.join(map(str, ids)) or '0'}_{n}"


def apply_bank_activity(act: Dict[str, Any], ctx: StudentContext, all_domains: List[str],
                        blank: Callable[[], Dict[str, Any]], teacher_keys: List[str],
                        from_bank: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """Loads Activity Bank content into the activity when its texts are missing. The activity keeps its
    id and name: which activity a student has is decided by the Activities grid, not here."""
    dt = act["dt"]
    if ALL in (dt.get("domain") or []):
        dt["domain"] = list(all_domains)
    bank_id = dt.get("act_bank_id")
    entry = ctx.lookups.activities.get(int(bank_id)) if str(bank_id or "").isdigit() else None
    if entry is None:
        return

    content = entry["content"].get("dt") or {}
    content_missing = not dt.get("gl") or not filled((dt.get("desc") or [""])[0])
    if content_missing:
        keep = {k: dt.get(k) for k in teacher_keys}
        fresh = bank_dt(blank, content, int(bank_id), dt.get("is_global") is not False, from_bank,
                        [(keep.get(k) or ["", "", "", ""])[3] for k in ("awr", "sen", "cre")])
        dt.clear()
        dt.update(fresh)
        dt.update({k: v for k, v in keep.items() if k not in ("awr", "sen", "cre") and has_value(v)})
        act["nm"] = act.get("nm") or entry["activity_caption"]
        act.setdefault("is_modified", False)
    if not dt.get("domain"):
        own = [d["ent_code"] for d in ctx.lookups.domains if d["id"] in (entry.get("domain_ids") or [])]
        dt["domain"] = own or list(all_domains)


def bank_dt(blank: Callable[[], Dict[str, Any]], content: Dict[str, Any], bank_id: int, is_global: bool,
            from_bank: Callable[[Dict[str, Any]], Dict[str, Any]], levels: List[str]) -> Dict[str, Any]:
    """A student's copy of a bank activity: the bank's texts, rubric descriptors and the chosen levels."""
    dt = blank()
    desc = list(content.get("desc") or [])[:2]
    dt.update({"gl": content.get("gl") or [], "cpt": content.get("cpt") or [],
               "desc": desc + [""] * (2 - len(desc)), "act_bank_id": bank_id, "is_global": is_global})
    for k, level in zip(("awr", "sen", "cre"), levels):
        texts = list(content.get(k) or [])[:3] + [""] * 3
        dt[k] = [texts[0], texts[1], texts[2], level]
    dt.update(from_bank(content))
    return dt


def make_finish_b(all_domains: List[str], blank: Callable[[], Dict[str, Any]], teacher_keys: List[str],
                  from_bank: Callable[[Dict[str, Any]], Dict[str, Any]],
                  complete: Callable[[Dict[str, Any]], bool],
                  prepare: Callable[[Dict[str, Any]], None] = lambda dt: None):
    def finish_b(fd: List[Dict[str, Any]], ctx: StudentContext):
        errors: List[str] = []
        if fd:
            apply_bank_activity(fd[0], ctx, all_domains, blank, teacher_keys, from_bank)
        hpc_id = str(ctx.record.get("hpc_id"))
        act_bank_map, covered = [], set()
        used_ids = {act.get("id") for act in fd if act.get("id")}
        for n, act in enumerate(fd, start=1):
            dt = act["dt"]
            prepare(dt)
            if not act.get("id"):
                bump = n
                while activity_id(hpc_id, dt.get("domain") or [], ctx, bump) in used_ids:
                    bump += 1                            # never reuse an id a kept activity already has
                act["id"] = activity_id(hpc_id, dt.get("domain") or [], ctx, bump)
                used_ids.add(act["id"])
            act["is_complete"] = complete(dt)
            act.setdefault("is_modified", False)
            covered.update(dt.get("domain") or [])
            if dt.get("act_bank_id"):
                act_bank_map.append({"id": act["id"], "bank_id": str(dt["act_bank_id"]),
                                     "is_modified": bool(act["is_modified"]), "is_global": bool(dt.get("is_global", True))})
            if not act["is_complete"]:
                gaps = [label for ok, label in ((dt.get("gl"), "no curricular goal"), (dt.get("cpt"), "no competency"),
                                                ("activity" not in dt or dt.get("activity"), "no approach ticked"))
                        if not ok]
                why = (" (" + ", ".join(gaps) + " - set it in the Activity Library)") if gaps else \
                    " - fill every required Part B column"
                errors.append(f"activity '{act.get('nm') or n}' is not finished{why}")
        missing = [d for d in all_domains if d not in covered]
        if missing:
            names = {d["ent_code"]: d["ent_caption"].strip() for d in ctx.lookups.domains}
            errors.append("every subject needs an activity; not covered: " + ", ".join(names.get(m, m) for m in missing))
        extra = {"hpc_id": hpc_id, "state_code_internal": ctx.lookups.portal.state, "act_bank_map": act_bank_map}
        if fd and fd[0]["dt"].get("act_bank_id"):
            extra["global_activity_bank_id"] = int(fd[0]["dt"]["act_bank_id"])
        return extra, errors
    return finish_b
