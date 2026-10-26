"""
One student's HPC card in the web app: the form, autosaved drafts, checks, submit, preview,
and bulk entry of one field across a class.

The form shows the same fields as the class workbook (backend/hpc/stages). Edits are kept as
a server-side DRAFT per teacher, academic session and student - nothing goes to the portal
until the teacher submits, which runs the same sync as a workbook upload.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.hpc import sync
from backend.hpc.fields import Field
from backend.hpc.portal import Portal, stage_code
from backend.hpc.stages import activity_grid, get_stage
from backend.hpc.stages.common import Lookups
from backend.services import hpc_sessions

LIST_KINDS = ("multi", "flags")
_LOOKUP_TTL = 30 * 60
_lookup_cache: Dict[Tuple[str, str], Tuple[float, Lookups]] = {}
_lock = threading.Lock()


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
    d = hpc_sessions.session_dir("teacher", teacher_id) / "drafts" / str(session)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{stage.lower()}_{student_id}.json"


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
            "max_len": f.max_len, "required": f.required, "multiple": f.kind in LIST_KINDS}


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


def stage_fields(stage: str, lookups: Lookups) -> List[Dict[str, Any]]:
    return [{"code": p.code, "title": p.title, "fields": [field_meta(f) for f in p.fields(lookups)]}
            for p in get_stage(stage).PARTS]


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


def card(client: Portal, owner: str, teacher_id: str, session: str, stage: str, student_id: str) -> Dict[str, Any]:
    """The form: every part's fields with portal values, the teacher's draft on top, and per-part status."""
    lookups = lookups_for(owner, client, stage)
    data = sync.fetch_student(client, stage, student_id)
    portal_row = sync.to_row(stage, data, lookups)
    draft = load_draft(teacher_id, session, stage, student_id)
    row = {**portal_row, **((draft or {}).get("values") or {})}
    index = _field_index(stage, lookups)
    errors = _part_errors(stage, data, {**portal_row, **_cell_values(stage, index, (draft or {}).get("values") or {})},
                          lookups, _resolver(teacher_id, stage, lookups))
    parts = []
    for p in get_stage(stage).PARTS:
        fields = []
        for f in p.fields(lookups):
            fields.append({**field_meta(f), "value": to_api_value(f, row.get(f.key)),
                           "portal_value": to_api_value(f, portal_row.get(f.key)),
                           "changed": draft is not None and f.key in draft["values"]})
        parts.append({"code": p.code, "title": p.title, "fields": fields, "problems": errors.get(p.code, []),
                      "complete": not errors.get(p.code)})
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
                               before_save=snapshots.hook(f"teacher_{teacher_id}", stage, "card submit"))
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


def bulk_read(client: Portal, owner: str, teacher_id: str, session: str, stage: str, key: str) -> Dict[str, Any]:
    lookups = lookups_for(owner, client, stage)
    part, f = _part_of(stage, lookups, key)
    students = sync.roster(client, stage, lookups)

    def value_for(s):
        raw = client.student(stage, s["student_id"], part.col).get("formdata")
        portal_value = f.read(part.load(raw))
        draft = load_draft(teacher_id, session, stage, s["student_id"])
        in_draft = bool(draft and key in draft["values"])
        value = draft["values"][key] if in_draft else to_api_value(f, portal_value)
        return {"student_id": s["student_id"], "student_name": s["student_name"], "grade": s["grade"],
                "section": s["section"], "status": s["status"], "value": value,
                "portal_value": to_api_value(f, portal_value), "in_draft": in_draft}

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(value_for, students))
    return {"field": {**field_meta(f), "part": part.code, "part_title": part.title}, "rows": rows}


def bulk_write(client: Portal, owner: str, teacher_id: str, session: str, stage: str, key: str,
               values: Dict[str, Any]) -> Dict[str, Any]:
    """Puts one field's value into each listed student's draft. Invalid values are reported, not saved."""
    lookups = lookups_for(owner, client, stage)
    _, f = _part_of(stage, lookups, key)
    saved, problems = [], {}
    for student_id, value in values.items():
        err = validate_values(stage, lookups, {key: value}).get(key)
        if err:
            problems[student_id] = err
            continue
        save_draft(teacher_id, session, stage, str(student_id), {key: value})
        saved.append(str(student_id))
    return {"saved": saved, "problems": problems}
