"""
One student's HPC card in the web app: the form, autosaved drafts, checks, submit, preview,
and bulk entry of one field across a class.

The form shows the same fields as the class workbook (backend/hpc/stages). Edits are kept as
a server-side DRAFT per teacher, academic session and student - nothing goes to the portal
until the teacher submits, which runs the same sync as a workbook upload.
"""
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.hpc import sync
from backend.hpc.fields import STUDENT_DEFAULTS, Field
from backend.hpc import checks, notes
from backend.hpc.suggestions import FILL_ONLY, has_suggestions, mixable, multi_mix, record_kind, suggestions_for
from backend.hpc.portal import Portal, stage_code
from backend.hpc.stages import activity_grid, get_stage
from backend.hpc.stages.common import Lookups
from backend.services import card_store, hpc_sessions
from backend.services.safe_paths import inside

LIST_KINDS = ("multi", "flags")
_LOOKUP_TTL = 12 * 60 * 60                 # PARAKH's dropdown lists rarely change
_lookup_cache: Dict[Tuple[str, str], Tuple[float, Lookups]] = {}
_lock = threading.RLock()
_dob_seen: Dict[tuple, str] = {}           # (owner, session, stage, student) -> date of birth read from PARAKH


# ---------------------------------------------------------------------------
# Academic sessions
# ---------------------------------------------------------------------------

def session_label(code: str) -> str:
    """'2627' -> '2026-27'."""
    code = str(code or "")
    return f"20{code[:2]}-{code[2:]}" if len(code) == 4 and code.isdigit() else code


def academic_sessions(client: Portal) -> List[Dict[str, Any]]:
    """The portal only exposes the school's current year, so that is the one (editable) session for now."""
    return [{"code": client.ay, "label": session_label(client.ay), "terms": [], "current": True, "read_only": False}]


def check_session(client: Portal, session: Optional[str], writing: bool) -> str:
    """Validates a requested session code; past sessions are read-only."""
    from fastapi import HTTPException, status
    code = session or client.ay
    known = {s["code"]: s for s in academic_sessions(client)}
    if code not in known:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Academic session {session_label(code)} is not available.")
    if writing and known[code]["read_only"]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{known[code]['label']} is a past session and is read-only.")
    return code


# ---------------------------------------------------------------------------
# Lookups (dropdown lists) are slow to load, so they are cached per teacher and stage
# ---------------------------------------------------------------------------

def cached_lookups(owner: str, stage: str) -> Optional[Lookups]:
    """The lists already loaded for this teacher and stage (e.g. by the upload check), without asking PARAKH."""
    with _lock:
        hit = _lookup_cache.get((owner, stage_code(stage)))
    return hit[1] if hit and time.time() - hit[0] < _LOOKUP_TTL else None


def lookups_for(owner: str, client: Portal, stage: str) -> Lookups:
    key = (owner, stage_code(stage))
    with _lock:
        hit = _lookup_cache.get(key)
        if hit and time.time() - hit[0] < _LOOKUP_TTL:
            return hit[1]
    lk = Lookups(client, stage_code(stage))
    with _lock:
        _lookup_cache[key] = (time.time(), lk)
    return lk


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------

def _draft_path(teacher_id: str, session: str, stage: str, student_id: str) -> Path:
    path = inside(hpc_sessions.session_dir("teacher", teacher_id), "drafts", str(session), f"{stage.lower()}_{student_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_draft(teacher_id: str, session: str, stage: str, student_id: str) -> Optional[Dict[str, Any]]:
    path = _draft_path(teacher_id, session, stage, student_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def save_draft(teacher_id: str, session: str, stage: str, student_id: str, values: Dict[str, Any],
               base_version: Optional[int] = None) -> Dict[str, Any]:
    """Merges values into the draft. base_version guards against two tabs overwriting each other."""
    from fastapi import HTTPException, status
    current = load_draft(teacher_id, session, stage, student_id) or {"values": {}, "version": 0}
    before = {k: current["values"].get(k) for k in values if current["values"].get(k) != values[k]}
    if base_version is not None and base_version != current["version"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This card was changed in another tab or window. Reload it to see the latest version.")
    current["values"].update(values)
    current["version"] += 1
    current["saved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path = _draft_path(teacher_id, session, stage, student_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)                      # atomic: a crash never leaves half a draft
    if before:
        from backend.services import audit
        audit.record(f"teacher:{teacher_id}", "save_draft", "draft", student_id, before,
                     {k: values[k] for k in before} | {"stage": stage, "session": session})
    return current


def drop_draft_keys(teacher_id: str, session: str, stage: str, student_id: str, keys) -> None:
    """Removes some values from a draft (e.g. the Activities grid's after they reached PARAKH)."""
    draft = load_draft(teacher_id, session, stage, student_id)
    if not draft or not any(k in draft["values"] for k in keys):
        return
    for k in keys:
        draft["values"].pop(k, None)
    if not draft["values"]:
        delete_draft(teacher_id, session, stage, student_id)
        return
    draft["version"] += 1
    path = _draft_path(teacher_id, session, stage, student_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def delete_draft(teacher_id: str, session: str, stage: str, student_id: str) -> None:
    path = _draft_path(teacher_id, session, stage, student_id)
    if path.exists():
        path.unlink()


# ---------------------------------------------------------------------------
# Field metadata and values
# ---------------------------------------------------------------------------

def field_meta(f: Field) -> Dict[str, Any]:
    return {"key": f.key, "label": f.label, "kind": f.kind, "options": list(f.options),
            "max_len": f.max_len, "required": f.required, "multiple": f.kind in LIST_KINDS,
            "suggestions": suggestions_for(f.key, f.max_len, f.label) if not f.options else [],
            "mixable": mixable(f.key, f.label),  # "Mix" may hand answers out at random (not for facts like mother tongue)
            "from_records": record_kind(f.label, f.key),   # name / age / friend / levels (Part C notes): from the records
            # a several-option question Mix may fill: which options, and how many each student gets
            "mix_pool": multi_mix(f.key, f.options)[0] if f.kind in LIST_KINDS else [],
            "mix_pick": multi_mix(f.key, f.options)[1] if f.kind in LIST_KINDS else 0}


def to_api_value(f: Field, value: Any) -> Any:
    """Workbook-style cell value -> what the web app shows (lists for multi-choice fields)."""
    if f.kind in LIST_KINDS:
        if isinstance(value, list):                     # already a list (from a draft)
            return [str(v) for v in value]
        return [v.strip() for v in str(value or "").split(",") if v.strip()]
    return "" if value is None else value


def to_cell_value(f: Field, value: Any) -> Any:
    """What the web app sends -> the workbook-style cell value the stage code reads."""
    if f.kind in LIST_KINDS and isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


# Bulk entry covers answers where most of the class picks the same option and only a few differ: every
# pick-from-a-list question in A3/A4 (feelings, peer and parent answers, resources, support) and the Part C levels,
# and every text answer the app has ready phrases for (backend/hpc/suggestions.py: mother tongue, the "all about
# me" favourites and goals, ambition, home support, Part C remarks ...). Not names, ages, friends or relations
# (they differ per student) - except name, age and Foundational friends, which "Mix all" takes from the app's records
# - and where the student lives (FILL_ONLY: "Apply to all" with the village); not class settings, not marks.
# Part B's answers (self-assessment, reflection, strengths, "I learnt" ...) are all class-wide, text included -
# shown on the Activities tab, next to the activities they belong to (the Excel file leaves Part B out, and
# PARAKH counts an activity finished only when they are filled).
COMMON_PARTS = ("A3", "A4", "C")
COMMON_KINDS = ("choice", "inlist", "multi", "flags")


def is_common(part_code: str, f: Field) -> bool:
    return part_code == "B" or (part_code == "A2" and f.kind == "choice") \
        or (f.kind == "text" and (has_suggestions(f.key, f.label) or bool(record_kind(f.label, f.key)) or f.label in FILL_ONLY)) \
        or (part_code in COMMON_PARTS and f.kind in COMMON_KINDS)


def _common_fields(stage: str, lookups: Lookups) -> Dict[str, Field]:
    return {f.key: f for p in get_stage(stage).PARTS for f in p.fields(lookups) if is_common(p.code, f)}


def stage_fields(stage: str, lookups: Lookups, common: bool = False) -> List[Dict[str, Any]]:
    out = []
    for p in get_stage(stage).PARTS:
        fields = [field_meta(f) for f in p.fields(lookups) if not common or is_common(p.code, f)]
        if fields:
            out.append({"code": p.code, "title": p.title, "fields": fields})
    return out


def _common_only(stage: str, lookups: Lookups, key: str) -> None:
    if key not in _common_fields(stage, lookups):
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"'{key}' is not one of the class-wide fields bulk entry covers.")


def common_values(teacher_id: str, session: str, stage: str, student_id: str, lookups) -> Dict[str, Any]:
    """Every answer in a student's draft - bulk entry and the card editor alike - as cell values (they go into the
    class file: the Excel template, and the class sent to PARAKH straight from the app)."""
    index = _field_index(stage, lookups)
    draft = (load_draft(teacher_id, session, stage, student_id) or {}).get("values") or {}
    return {k: to_cell_value(index[k], v) for k, v in draft.items() if k in index}


def _field_index(stage: str, lookups: Lookups) -> Dict[str, Field]:
    return {f.key: f for p in get_stage(stage).PARTS for f in p.fields(lookups)}


def validate_values(stage: str, lookups: Lookups, values: Dict[str, Any]) -> Dict[str, str]:
    """Field-level problems in submitted values, by field key (unknown keys are rejected)."""
    index = _field_index(stage, lookups)
    grid = set(activity_grid.grid_keys(get_stage(stage).DOMAINS))
    problems = {}
    for key, value in values.items():
        f = index.get(key)
        if f is None and key in grid:
            problem = activity_grid.check_value(key, value)
            if problem:
                problems[key] = problem
            continue
        if f is None:
            problems[key] = "Unknown field."
            continue
        _, err = f.parse(to_cell_value(f, value))
        if err and not (f.required and str(value or "").strip() == ""):   # empty required = shown as incomplete
            problems[key] = err.split(": ", 1)[-1]
    return problems


# ---------------------------------------------------------------------------
# The card
# ---------------------------------------------------------------------------

def _student_summary(stage: str, data: sync.StudentData, lookups: Lookups) -> Dict[str, Any]:
    stu = data.record.get("stu_info") or {}
    info = {"student_id": data.student_id, "student_name": stu.get("student_name", ""), "stage": stage}
    sync.add_details(info, data.record)
    info.update({"grade": next((g["grade_caption"] for g in lookups.grades if g["id"] == stu.get("grade_id")), ""),
                 "section": lookups.section_name(stu.get("section_id")), "apaar_id": stu.get("std_apaar_id", ""),
                 "current_part": data.current_part, "completed": data.current_part == "mc"})
    return info


def _resolver(teacher_id: str, stage: str, lookups: Lookups):
    from backend.services.activity_library import resolver_for_teacher
    return resolver_for_teacher(teacher_id, stage, fallback=activity_grid.resolver_from_lookups(lookups))


def _cell_values(stage: str, index: Dict[str, Field], values: Dict[str, Any]) -> Dict[str, Any]:
    """Draft values as workbook cells; Activities grid values pass through as they are."""
    grid = set(activity_grid.grid_keys(get_stage(stage).DOMAINS))
    return {k: to_cell_value(index[k], v) if k in index else v for k, v in values.items() if k in index or k in grid}


def _part_errors(stage: str, data: sync.StudentData, row: Dict[str, Any], lookups: Lookups,
                 resolve=None) -> Dict[str, List[str]]:
    _, errors = sync.build_payloads(stage, data, row, lookups, resolve)
    by_part: Dict[str, List[str]] = {p.code: [] for p in get_stage(stage).PARTS}
    titles = {p.title: p.code for p in get_stage(stage).PARTS}
    for e in errors:
        title, _, detail = e.partition(": ")
        by_part.setdefault(titles.get(title, "?"), []).append(detail or e)
    return by_part


def _part_b(stage: str, raw_parts: Dict[str, Any]) -> List[Dict[str, Any]]:
    b = next((p for p in get_stage(stage).PARTS if p.code == "B"), None)
    loaded = b.load((raw_parts or {}).get(b.col)) if b else []
    return loaded if isinstance(loaded, list) else []


def card_warnings(stage: str, row: Dict[str, Any], raw_parts: Dict[str, Any], fields: Optional[List[Field]] = None,
                  student: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
    """{part code: warnings} - content PARAKH accepts but that reads wrong (checks.py, part_a_checks.py); they never
    block a save."""
    from backend.hpc import part_a_checks
    st = get_stage(stage)
    values = {k: (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in row.items()}
    c = checks.part_c_warnings(stage, st.DOMAINS, st.SUBJECTS, values) + \
        checks.part_b_vs_c(st.DOMAINS, st.SUBJECTS, values, _part_b(stage, raw_parts))
    b = checks.part_b_warnings(_part_b(stage, raw_parts))
    out = part_a_checks.part_a_warnings(stage, row, fields or [], student or {})
    for k, v in (("B", b), ("C", c)):
        if v:
            out[k] = out.get(k, []) + v
    return out


def card(client: Portal, owner: str, teacher_id: str, session: str, stage: str, student_id: str) -> Dict[str, Any]:
    """The form: every part's fields with portal values, the teacher's draft on top, and per-part status."""
    lookups = lookups_for(owner, client, stage)
    data = sync.fetch_student(client, stage, student_id)
    portal_row = sync.to_row(stage, data, lookups)
    draft = load_draft(teacher_id, session, stage, student_id)
    locked = sync.school_values(stage, data)              # set by the school in the School Register: read only here
    row = {**portal_row, **((draft or {}).get("values") or {}), **locked}
    index = _field_index(stage, lookups)
    errors = _part_errors(stage, data, {**portal_row, **_cell_values(stage, index, (draft or {}).get("values") or {})},
                          lookups, _resolver(teacher_id, stage, lookups))
    warnings = card_warnings(stage, row, data.raw_parts, [f for p in get_stage(stage).PARTS for f in p.fields(lookups)],
                             data.record.get("stu_info") or {})
    parts = []
    for p in get_stage(stage).PARTS:
        fields = []
        for f in p.fields(lookups):
            fields.append({**field_meta(f), "value": to_api_value(f, row.get(f.key)),
                           "portal_value": to_api_value(f, portal_row.get(f.key)),
                           "changed": (draft is not None and f.key in draft["values"]) or
                                      (f.key in locked and str(locked[f.key]) != str(portal_row.get(f.key, ""))),
                           **({"set_by_school": True} if f.key in locked else {})})
            if record_kind(f.label, f.key) == "levels":       # the note the levels give, to use or compare
                fields[-1]["from_levels"] = notes.note(notes.note_key(f.key), notes.levels_from_row(row, notes.note_key(f.key)),
                                                       f.max_len, notes.activity_names(_part_b(stage, data.raw_parts))
                                                       .get(notes.note_key(f.key), ""))
        parts.append({"code": p.code, "title": p.title, "fields": fields, "problems": errors.get(p.code, []),
                      "warnings": warnings.get(p.code, []), "complete": not errors.get(p.code)})
    return {"student": _student_summary(stage, data, lookups),
            "session": {"code": session, "label": session_label(session)},
            "parts": parts, "ready": all(p["complete"] for p in parts),
            "draft": {"version": draft["version"], "saved_at": draft["saved_at"]} if draft else None}


def submit(client: Portal, owner: str, teacher_id: str, session: str, stage: str, student_id: str) -> Dict[str, Any]:
    """Saves the card to the portal part by part (same code as a workbook upload). The draft is kept on failure."""
    lookups = lookups_for(owner, client, stage)
    data = sync.fetch_student(client, stage, student_id)
    draft = load_draft(teacher_id, session, stage, student_id) or {"values": {}}
    index = _field_index(stage, lookups)
    row = {**sync.to_row(stage, data, lookups), **_cell_values(stage, index, draft["values"])}
    from backend.services import snapshots
    result = sync.sync_student(client, stage, student_id, row, lookups, resolve=_resolver(teacher_id, stage, lookups),
                               before_save=snapshots.hook(f"teacher_{teacher_id}", stage, "card submit"),
                               data=data)                # just read above: not read a second time
    from backend.services import audit
    audit.record(f"teacher:{teacher_id}", "save_to_parakh", "student", student_id, None,
                 {"stage": stage, "status": result.status, "saved_parts": result.saved_parts, "errors": result.errors[:5],
                  "via": "card"})
    if result.status == "COMPLETED":
        delete_draft(teacher_id, session, stage, student_id)
        from backend.services import activity_grid
        activity_grid.forget(teacher_id, stage, student_id)
    return {"status": result.status, "errors": result.errors, "saved_parts": result.saved_parts}


def preview(client: Portal, owner: str, teacher_id: str, session: str, stage: str, student_id: str,
            include_draft: bool = True) -> Dict[str, Any]:
    """Read-only card for printing: each part as label/value pairs, blanks left out."""
    c = card(client, owner, teacher_id, session, stage, student_id)
    sections = []
    for p in c["parts"]:
        items = []
        for f in p["fields"]:
            value = f["value"] if include_draft else f["portal_value"]
            text = ", ".join(value) if isinstance(value, list) else str(value)
            if text.strip():
                items.append({"label": f["label"], "value": text})
        sections.append({"code": p["code"], "title": p["title"], "items": items, "complete": p["complete"]})
    return {"student": c["student"], "session": c["session"], "sections": sections, "ready": c["ready"],
            "includes_draft": include_draft and c["draft"] is not None}


# ---------------------------------------------------------------------------
# Bulk entry: one field for the whole class
# ---------------------------------------------------------------------------

def _part_of(stage: str, lookups: Lookups, key: str):
    for p in get_stage(stage).PARTS:
        for f in p.fields(lookups):
            if f.key == key:
                return p, f
    from fastapi import HTTPException, status
    raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown field '{key}'.")


# Bulk Entry and the Part C levels screen load from the app's stored copy of the class's cards (card_store):
# PARAKH is read only for parts not kept yet, or when the teacher asks to read again.

def class_list(client: Portal, teacher_id: str, stage: str, lookups: Lookups) -> List[Dict[str, Any]]:
    """The class as last fetched on the roster tab (kept by the app); PARAKH only when it was never fetched."""
    path = inside(hpc_sessions.session_dir("teacher", teacher_id), f"roster_{stage.lower()}.json")
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        stored = []
    done = lambda s: str(s.get("status") or "").upper() == "COMPLETED"     # nothing left to do on those cards
    return [{"status": "", **s} for s in stored if not done(s)] or [s for s in sync.roster(client, stage, lookups) if not done(s)]


def in_class(client: Portal, teacher_id: str, stage: str, lookups: Lookups) -> set:
    """The student ids a teacher may keep drafts for: their class list (C-2)."""
    return {str(s["student_id"]) for s in class_list(client, teacher_id, stage, lookups)}


def _blank(value: Any) -> bool:
    return (isinstance(value, list) and not value) or str(value if value is not None else "").strip() in ("", "[]")


def part_progress(client: Portal, owner: str, teacher_id: str, session: str, stage: str, part_code: str) -> Dict[str, Any]:
    """For each class-wide field of a part: how many students have an answer (the draft's, else PARAKH's as
    stored), so the screen can mark a question done or say how many are left."""
    lookups = lookups_for(owner, client, stage)
    part = next((p for p in get_stage(stage).PARTS if p.code == part_code), None)
    if part is None:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown part '{part_code}'.")
    fields = [f for f in part.fields(lookups) if is_common(part.code, f)]
    students = class_list(client, teacher_id, stage, lookups)
    raw, _ = card_store.class_parts(client, owner, session, stage, [s["student_id"] for s in students], [part.col], False)
    filled = {f.key: 0 for f in fields}
    for s in students:
        fd = part.load(raw[s["student_id"]][part.col])
        draft = (load_draft(teacher_id, session, stage, s["student_id"]) or {}).get("values") or {}
        for f in fields:
            if not _blank(draft[f.key] if f.key in draft else f.read(fd)):
                filled[f.key] += 1
    return {"total": len(students),
            "fields": {f.key: {"filled": filled[f.key], "required": f.required} for f in fields}}


def bulk_mix(client: Portal, owner: str, teacher_id: str, session: str, stage: str, keys: List[str], replace: bool,
             apply: bool, level_hints: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Any]:
    """Every listed class-wide question at once: each student gets one of the question's suggestions (text) or
    options (a single-choice question), handed out at random so each is used about equally. Only empty answers
    unless replace. Part B's several-option assessment lists get a few options each (suggestions.MULTI_MIX); facts
    about a student (mother tongue, resources at home ...) are not mixed - except those the app's records answer:
    name (the class list), age (the date of birth on PARAKH) and, in Foundational, five classmates as friends.
    A student never gets the same phrase twice in one go (Preparatory's five "things about me"). Without apply it
    only counts; with apply each student's answers are saved in one draft save."""
    lookups = lookups_for(owner, client, stage)
    index = _common_fields(stage, lookups)
    part_of = {f.key: p for p in get_stage(stage).PARTS for f in p.fields(lookups)}
    mixed, skipped = {}, []
    for key in keys:
        f = index.get(key)
        if f is None:
            skipped.append({"key": key, "label": key, "reason": "not a class-wide question"})
            continue
        pick = 1
        if key in STUDENT_DEFAULTS:                      # the school's default (mother tongue: Kashmiri), not at random
            mixed[key] = (f, [STUDENT_DEFAULTS[key]], 1)
            continue
        if record_kind(f.label, f.key):
            mixed[key] = (f, [], 1)                      # from the records, worked out per student below
            continue
        if f.kind in LIST_KINDS:
            pool, pick = multi_mix(f.key, f.options)
        else:
            pool = suggestions_for(f.key, f.max_len, f.label) if not f.options else list(f.options)
        if f.label in FILL_ONLY:
            skipped.append({"key": key, "label": f.label, "reason": "where each student lives - type it and use 'Apply to all'"})
        elif not mixable(f.key, f.label):
            skipped.append({"key": key, "label": f.label, "reason": "a fact about each student - fill it yourself"})
        elif f.kind in LIST_KINDS and not pool:
            skipped.append({"key": key, "label": f.label, "reason": "several options can be ticked - fill it yourself"})
        elif len(pool) < 2:
            skipped.append({"key": key, "label": f.label, "reason": "nothing to mix"})
        else:
            mixed[key] = (f, pool, pick)
    students = class_list(client, teacher_id, stage, lookups)
    wants_age = any(record_kind(f.label) == "age" for f, _, _ in mixed.values())
    wants_notes = any(record_kind(f.label, f.key) == "levels" for f, _, _ in mixed.values())
    a1 = next((p for p in get_stage(stage).PARTS if p.code == "A1"), None)
    b_part = next((p for p in get_stage(stage).PARTS if p.code == "B"), None)
    cols = sorted({part_of[k].col for k in mixed} | ({a1.col} if wants_age and a1 else set())
                  | ({b_part.col} if wants_notes and b_part else set()))
    raw, _ = card_store.class_parts(client, owner, session, stage, [s["student_id"] for s in students], cols, False) \
        if cols else ({s["student_id"]: {} for s in students}, None)
    rng = random.Random()
    rounds: Dict[str, List[str]] = {k: [] for k in mixed}

    def draw(key: str) -> str:                           # a shuffled round of the pool, again and again
        if not rounds[key]:
            rounds[key] = list(mixed[key][1])
            rng.shuffle(rounds[key])
        return rounds[key].pop()

    classmates: Dict[tuple, List[str]] = {}
    for s in students:                                    # first names, per grade and section
        first = (s.get("student_name") or "").split()
        if first:
            classmates.setdefault((s.get("grade"), s.get("section")), []).append(first[0].title())

    def from_records(f: Field, s: Dict[str, Any], loaded: Dict[str, Any], taken: List[str]) -> Any:
        kind = record_kind(f.label)
        name = " ".join(w.title() for w in (s.get("student_name") or "").split())
        if kind == "name":
            return name if not f.max_len or len(name) <= f.max_len else name.split()[0][:f.max_len]
        if kind == "age":
            dob = dobs.get(s["student_id"], "")
            try:
                born = datetime.strptime(dob[:10], "%Y-%m-%d").date()
            except ValueError:
                return ""
            today = datetime.now(timezone.utc).date()
            return str(today.year - born.year - ((today.month, today.day) < (born.month, born.day)))
        if kind == "friend":
            mine = name.split()[0] if name else ""
            pool = [n for n in classmates.get((s.get("grade"), s.get("section")), []) if n != mine and n not in taken]
            return rng.choice(pool)[:f.max_len or None] if pool else ""
        return ""

    def next_value(key: str, taken: List[str]):
        f, _, pick = mixed[key]
        if f.kind not in LIST_KINDS:
            value = draw(key)
            for _ in range(len(mixed[key][1])):           # not the same phrase twice for one student
                if value not in taken:
                    break
                value = draw(key)
            return value
        chosen: List[str] = []
        while len(chosen) < pick:                         # several different options for one student
            option = draw(key)
            if option not in chosen:
                chosen.append(option)
        return [o for o in f.options if o in chosen]      # in the question's own order

    # dates of birth: Part A1 when PARAKH has it, else the class list (kept since its last fetch), else the
    # student's record - read in parallel, once
    dobs: Dict[str, str] = {}
    if wants_age and a1 is not None:
        missing = []
        for s in students:
            sid = s["student_id"]
            gen = (a1.load(raw[sid].get(a1.col)) or {}).get("gen") or []
            dobs[sid] = str(gen[4] if len(gen) > 4 and gen[4]
                            else s.get("dob") or _dob_seen.get((owner, session, stage, sid), ""))   # class list, then memory
            if not dobs[sid]:
                missing.append(sid)

        def record_dob(sid: str) -> str:
            try:
                return str((client.student(stage, sid).get("stu_info") or {}).get("dob") or "")
            except Exception:
                return ""                                 # no age for this student; the others still get theirs
        with ThreadPoolExecutor(max_workers=6) as pool:
            for sid, dob in zip(missing, pool.map(record_dob, missing)):
                dobs[sid] = dob
                if dob:
                    _dob_seen[(owner, session, stage, sid)] = dob

    parts_by_col = {part_of[k].col: part_of[k] for k in mixed}
    no_levels: Dict[str, List[str]] = {}                  # Part C notes left blank: the subject has no levels yet
    changes: Dict[str, Dict[str, Any]] = {}
    filled = {k: 0 for k in mixed}
    for s in students:
        draft = (load_draft(teacher_id, session, stage, s["student_id"]) or {}).get("values") or {}
        loaded = {c: part.load(raw[s["student_id"]].get(c)) for c, part in parts_by_col.items()}
        if wants_age and a1 is not None:
            loaded[a1.col] = a1.load(raw[s["student_id"]].get(a1.col))
        taken: List[str] = []                             # what this student already got in this go
        notes_last = sorted(mixed.items(), key=lambda kv: record_kind(kv[1][0].label, kv[0]) == "levels")
        for key, (f, _, _) in notes_last:              # notes after levels: a level mixed now counts for its note
            current = draft[key] if key in draft else to_api_value(f, f.read(loaded[part_of[key].col]))
            if not _blank(current) and (not replace or key in STUDENT_DEFAULTS):
                continue                                  # a default never replaces what is there (Urdu stays Urdu)
            if record_kind(f.label, f.key) == "levels":
                part_b = b_part.load(raw[s["student_id"]].get(b_part.col)) if b_part else []
                value = note_from_levels(f, {**draft, **changes.get(s["student_id"], {})}, loaded[part_of[key].col],
                                         index, part_b)
                if _blank(value):
                    no_levels.setdefault(key, []).append(s.get("student_name", ""))
            else:
                hint = _level_hint(key, f, (level_hints or {}).get(str(s["student_id"])))
                value = hint or (from_records(f, s, loaded, taken) if record_kind(f.label) else next_value(key, taken))
            if _blank(value):
                continue                                  # no record for it (no date of birth, no levels ...)
            changes.setdefault(s["student_id"], {})[key] = value
            taken.append(value if isinstance(value, str) else "")
            filled[key] += 1
    if apply:
        for sid, values in changes.items():
            save_draft(teacher_id, session, stage, sid, values)
    for key, names in no_levels.items():                  # reported, never filled with a stock sentence
        skipped.append({"key": key, "label": mixed[key][0].label,
                        "reason": f"left blank for {len(names)} student(s) without all three levels for this subject"
                                  f" ({', '.join(n for n in names[:5] if n)}{' ...' if len(names) > 5 else ''})"})
    return {"applied": apply, "students": len(changes), "cells": sum(filled.values()),
            "fields": [{"key": k, "label": mixed[k][0].label, "filled": filled[k]} for k in mixed],
            "skipped": skipped}


def _level_hint(key: str, f: Field, hints: Optional[Dict[str, str]]) -> str:
    """A Part C level from the school's summative marks (Global Mix): c_<subject>_<ability> -> that subject's level."""
    if not hints or not key.startswith("c_") or not key.endswith(("_awareness", "_sensitivity", "_creativity")):
        return ""
    level = hints.get(key[2:].rsplit("_", 1)[0], "")
    return level if level in (f.options or {}) else ""


def note_from_levels(f: Field, draft: Dict[str, Any], part_c: Any, index: Dict[str, Field], part_b: Any) -> str:
    """A Part C note written from the subject's three levels: the draft's where set, else PARAKH's (notes.note)."""
    domain = notes.note_key(f.key)
    row = {}
    for ability in notes.ABILITIES:
        for key in (f"c_{domain}_{ability}", f"c_{domain}_{notes.SHORT[ability]}"):
            lf = index.get(key)
            if lf is not None:
                row[key] = draft[key] if key in draft else lf.read(part_c)
    activity = notes.activity_names(part_b if isinstance(part_b, list) else []).get(domain, "")
    return notes.note(domain, notes.levels_from_row(row, domain), f.max_len, activity)


def bulk_read(client: Portal, owner: str, teacher_id: str, session: str, stage: str, key: str,
              refresh: bool = False) -> Dict[str, Any]:
    lookups = lookups_for(owner, client, stage)
    _common_only(stage, lookups, key)
    part, f = _part_of(stage, lookups, key)
    students = class_list(client, teacher_id, stage, lookups)
    from_levels = record_kind(f.label, f.key) == "levels"
    b_part = next((p for p in get_stage(stage).PARTS if p.code == "B"), None) if from_levels else None
    raw, read_at = card_store.class_parts(client, owner, session, stage, [s["student_id"] for s in students],
                                          [part.col] + ([b_part.col] if b_part else []), refresh)
    index = _common_fields(stage, lookups) if from_levels else {}

    def value_for(s):
        loaded = part.load(raw[s["student_id"]][part.col])
        portal_value = f.read(loaded)
        draft = load_draft(teacher_id, session, stage, s["student_id"])
        in_draft = bool(draft and key in draft["values"])
        value = draft["values"][key] if in_draft else to_api_value(f, portal_value)
        out = {"student_id": s["student_id"], "student_name": s["student_name"], "grade": s["grade"],
               "section": s["section"], "status": s["status"], "value": value,
               "portal_value": to_api_value(f, portal_value), "in_draft": in_draft}
        if from_levels:                                # the note this student's levels give ("" without them)
            part_b = b_part.load(raw[s["student_id"]].get(b_part.col)) if b_part else []
            out["from_levels"] = note_from_levels(f, (draft or {}).get("values") or {}, loaded, index, part_b)
        return out

    check = card_store.start_check(client, owner, session, stage, [s["student_id"] for s in students], [part.col])
    meta = {**field_meta(f), "part": part.code, "part_title": part.title}
    if f.label in FILL_ONLY:                         # where students live: the school's town and district to start from
        places = []
        for s in students:
            for place in (s.get("school_place") or "", (s.get("school_place") or "").split(",")[0].strip()):
                if place and (not f.max_len or len(place) <= f.max_len) and place not in places:
                    places.append(place)
        meta["suggestions"] = places
    return {"field": meta, "rows": [value_for(s) for s in students], "read_at": read_at, "check": check}


def levels_read(client: Portal, owner: str, teacher_id: str, session: str, stage: str,
                refresh: bool = False) -> Dict[str, Any]:
    """Part C levels for the whole class on one screen: subjects, their three levels each, and every
    student's values (the draft's where there is one, else PARAKH's as stored)."""
    lookups = lookups_for(owner, client, stage)
    part = next(p for p in get_stage(stage).PARTS if p.code == "C")
    fields = [f for f in part.fields(lookups) if is_common("C", f) and f.kind != "text"]   # levels; remarks: bulk entry
    subjects: Dict[str, Dict[str, Any]] = {}
    for f in fields:
        name, _, ability = f.label.partition(":")
        code = f.key[2:].rsplit("_", 1)[0]
        subjects.setdefault(code, {"code": code, "name": name.strip(), "fields": []})["fields"].append(
            {"key": f.key, "ability": ability.replace("level", "").strip()})
    students = class_list(client, teacher_id, stage, lookups)
    raw, read_at = card_store.class_parts(client, owner, session, stage, [s["student_id"] for s in students],
                                          [part.col], refresh)

    def row_for(s):
        loaded = part.load(raw[s["student_id"]][part.col])
        draft = (load_draft(teacher_id, session, stage, s["student_id"]) or {}).get("values") or {}
        values, portal, in_draft = {}, {}, []
        for f in fields:
            portal[f.key] = to_api_value(f, f.read(loaded))
            values[f.key] = draft[f.key] if f.key in draft else portal[f.key]
            if f.key in draft:
                in_draft.append(f.key)
        return {"student_id": s["student_id"], "student_name": s["student_name"], "grade": s["grade"],
                "section": s["section"], "values": values, "portal": portal, "in_draft": in_draft}

    check = card_store.start_check(client, owner, session, stage, [s["student_id"] for s in students], [part.col])
    return {"options": list(fields[0].options) if fields else [], "subjects": list(subjects.values()),
            "rows": [row_for(s) for s in students], "read_at": read_at, "check": check}


def levels_write(client: Portal, owner: str, teacher_id: str, session: str, stage: str,
                 values: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Saves Part C levels for many students into their drafts. Only Part C level fields are accepted."""
    lookups = lookups_for(owner, client, stage)
    allowed = {f.key for p in get_stage(stage).PARTS if p.code == "C" for f in p.fields(lookups)
               if is_common("C", f) and f.kind != "text"}
    saved, problems = [], {}
    mine = in_class(client, teacher_id, stage, lookups)
    for student_id, per_key in values.items():
        if str(student_id) not in mine:
            problems[str(student_id)] = "This student is not in your class list."
            continue
        unknown = [k for k in per_key if k not in allowed]
        errs = validate_values(stage, lookups, {k: v for k, v in per_key.items() if k in allowed})
        if unknown or errs:
            problems[str(student_id)] = "; ".join([*(f"{k}: not a Part C level" for k in unknown), *errs.values()])
            continue
        save_draft(teacher_id, session, stage, str(student_id), per_key)
        saved.append(str(student_id))
    return {"saved": saved, "problems": problems}


def bulk_write(client: Portal, owner: str, teacher_id: str, session: str, stage: str, key: str,
               values: Dict[str, Any]) -> Dict[str, Any]:
    """Puts one field's value into each listed student's draft. Invalid values are reported, not saved."""
    lookups = lookups_for(owner, client, stage)
    _common_only(stage, lookups, key)
    _, f = _part_of(stage, lookups, key)
    saved, problems = [], {}
    mine = in_class(client, teacher_id, stage, lookups)
    for student_id, value in values.items():
        if str(student_id) not in mine:
            problems[str(student_id)] = "This student is not in your class list."
            continue
        err = validate_values(stage, lookups, {key: value}).get(key)
        if err:
            problems[student_id] = err
            continue
        save_draft(teacher_id, session, stage, str(student_id), {key: value})
        saved.append(str(student_id))
    return {"saved": saved, "problems": problems}
