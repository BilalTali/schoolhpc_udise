"""
The dashboard's Activities grid: every student of a stage, per subject an activity and three levels.

Values live in the teacher's draft (the same one the card editor uses), so the card editor, the
workbook download and every save to PARAKH see the same choices. PARAKH's current Part B and Part C
are read once and cached for a few minutes; "refresh" reads them again.
Each student's problems are worked out with the same code the real save uses, so what the grid shows
is what a sync would say.
"""
import copy
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from backend.database import SessionLocal
from backend.hpc import sync
from backend.hpc.portal import Portal
from backend.hpc.stages import activity_grid as grid
from backend.hpc.stages import get_stage
from backend.services import activity_library, card_store, hpc_cards

def _stage_info(stage: str):
    st = get_stage(stage)
    return st, st.DOMAINS, dict(zip(st.DOMAINS, st.SUBJECTS))


def _portal_parts(client: Portal, teacher_id: str, stage: str, students: List[Dict[str, Any]],
                  refresh: bool) -> Dict[str, Dict[str, Any]]:
    """student_id -> {"part_b": formdata, "part_c": formdata}: the app's stored copy (card_store), read from
    PARAKH only for students not kept yet, or all again with refresh."""
    ids = [s["student_id"] for s in students]
    raw, _ = card_store.class_parts(client, f"teacher_{teacher_id}", client.ay, stage, ids, ("part_b", "part_c"), refresh)
    card_store.start_check(client, f"teacher_{teacher_id}", client.ay, stage, ids, ("part_b", "part_c"))
    return raw


def forget(teacher_id: str, stage: str, student_id: Optional[str] = None) -> None:
    """After a save to PARAKH the stored copy of that student is out of date."""
    if student_id:
        card_store.forget_everywhere(f"teacher_{teacher_id}", stage, student_id)


def _parts(stage: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    st = get_stage(stage)
    return {p.col: p.load(raw.get(p.col)) for p in st.PARTS if p.col in ("part_b", "part_c")}


def student_row(stage: str, student: Dict[str, Any], raw: Dict[str, Any], draft: Optional[Dict[str, Any]],
                resolve, labels: Dict[str, str]) -> Dict[str, Any]:
    """One grid row: values, where they came from, what PARAKH has, and what a save would complain about."""
    st, subjects, names = _stage_info(stage)
    parts = _parts(stage, raw)
    draft_values = (draft or {}).get("values") or {}
    now, values, source = sync.grid_state(stage, parts, draft_values, None, grid.typed_keys(resolve))
    replace = str(values.get(grid.REPLACE_KEY, "")).lower() in ("yes", "true", "1")
    unchanged = all(values[k] == now.values.get(k, "") for k in values if k != grid.REPLACE_KEY)
    stale = grid.stale_texts(parts["part_b"], now, resolve)          # edited in the library since
    notes: List[str] = []
    if now.existing and unchanged and not replace and now.locked:
        problems = [f"Activity '{e['name']}' on PARAKH is not finished." for e in now.existing if not e["complete"]]
        notes.append("Kept exactly as it is on PARAKH (its activities share subjects).")
    else:
        result = grid.plan(subjects, names, st.ACTIVITY_GRID, copy.deepcopy(parts["part_b"]), values, resolve)
        problems = result.errors
        notes += [f"{c['action'].capitalize()}: {c['name']} ({', '.join(c['subjects'])})"
                  for c in result.changes if c["action"] != "keep"] if not unchanged or replace or stale else []
    covered = [s for s in subjects if values.get(grid.act_key(s))]
    return {
        "student_id": student["student_id"], "student_name": student.get("student_name", ""),
        "grade": student.get("grade", ""), "section": student.get("section", ""), "status": student.get("status", ""),
        "values": values, "source": source, "locked": now.locked, "replace": replace,
        "existing": [{**e, "subject_names": [names[s] for s in e["subjects"]],
                      "label": labels.get(e["key"], e["name"])} for e in now.existing],
        "missing_subjects": [names[s] for s in subjects if s not in covered],
        "problems": problems, "notes": notes, "ready": not problems,
        "draft_version": (draft or {}).get("version", 0), "saved_at": (draft or {}).get("saved_at"),
    }


def _context(client: Portal, teacher, stage: str):
    """Dropdown entries, labels and the activity resolver for this teacher and stage. Until the
    Activity Library has been synced, PARAKH's own activity list is used instead."""
    actor = activity_library.Actor("TEACHER", teacher.id, teacher.school_id, teacher.teacher_name)
    with SessionLocal() as db:
        entries = activity_library.dropdown_entries(db, actor, stage)
        everything = activity_library.library_entries(db, actor, stage)
    if everything:
        labels = {e["key"]: e["label"] for e in everything.values()}
        return entries, labels, activity_library.resolver_for_teacher(teacher.id, stage)
    lookups = hpc_cards.lookups_for(f"teacher_{teacher.id}", client, stage)
    entries = [{"key": f"P{i}", "label": lookups.activity_label(i)} for i in lookups.activities]
    return entries, {e["key"]: e["label"] for e in entries}, grid.resolver_from_lookups(lookups)


def load(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], refresh: bool = False) -> Dict[str, Any]:
    session = hpc_cards.check_session(client, None, writing=False)
    st, subjects, names = _stage_info(stage)
    entries, labels, resolve = _context(client, teacher, stage)
    raw = _portal_parts(client, teacher.id, stage, students, refresh)
    rows = [student_row(stage, s, raw[s["student_id"]],
                        hpc_cards.load_draft(teacher.id, session, stage, s["student_id"]), resolve, labels)
            for s in students]
    return {"stage": stage, "session": session,
            "subjects": [{"code": c, "name": names[c]} for c in subjects],
            "options": [{"key": e["key"], "label": e["label"]} for e in entries],
            "labels": labels, "students": rows,
            "grades": sorted({f"{r['grade']} - {r['section']}".strip(" -") for r in rows}),
            "summary": {"ready": sum(r["ready"] for r in rows), "total": len(rows),
                        "locked": sum(r["locked"] for r in rows)}}


def _check_values(stage: str, values: Dict[str, Any], allowed: set, current_keys: set) -> Dict[str, str]:
    _, subjects, _ = _stage_info(stage)
    known = set(grid.grid_keys(subjects))
    problems = {}
    for k, v in values.items():
        if k not in known:
            problems[k] = "Unknown field."
            continue
        problem = grid.check_value(k, v)
        if problem:
            problems[k] = problem
        elif k.startswith("b_act_") and v and v not in allowed and v not in current_keys:
            problems[k] = "This activity is not offered in your Activity Library (it may be turned off)."
    return problems


def save(client: Portal, teacher, stage: str, student: Dict[str, Any], values: Dict[str, Any],
         base_version: Optional[int]) -> Dict[str, Any]:
    """Autosave of one student's grid values (merged into the draft)."""
    session = hpc_cards.check_session(client, None, writing=True)
    entries, labels, resolve = _context(client, teacher, stage)
    raw = _portal_parts(client, teacher.id, stage, [student], False)[student["student_id"]]
    _, subjects, _ = _stage_info(stage)
    now = grid.current(subjects, _parts(stage, raw)["part_b"], grid.typed_keys(resolve))
    problems = _check_values(stage, values, {e["key"] for e in entries}, set(now.values.values()))
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"problems": problems})
    clean = {k: ("" if v is None else str(v).strip()) for k, v in values.items()}
    draft = hpc_cards.save_draft(teacher.id, session, stage, student["student_id"], clean, base_version)
    return student_row(stage, student, raw, draft, resolve, labels)


def quick_fill(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], activity_key: str,
               subject_codes: Optional[List[str]], levels: Dict[str, str], replace_filled: bool,
               apply: bool, expected_cells: Optional[int]) -> Dict[str, Any]:
    """Fills many cells at once. Without apply it only reports what would change."""
    session = hpc_cards.check_session(client, None, writing=apply)
    st, subjects, names = _stage_info(stage)
    entries, labels, resolve = _context(client, teacher, stage)
    if activity_key and activity_key not in {e["key"] for e in entries}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose an activity from your Activity Library.")
    bad_levels = {a: v for a, v in levels.items() if a not in dict(grid.ABILITIES) or v not in grid.LEVEL_TO_PORTAL}
    if bad_levels:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Levels must be Beginner, Proficient or Advanced.")
    if not activity_key and not levels:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose an activity or at least one level to fill in.")
    scope = [s for s in subjects if not subject_codes or s in subject_codes]
    raw = _portal_parts(client, teacher.id, stage, students, False)

    plans, skipped, cells, kept = [], [], 0, 0
    for s in students:
        sid = s["student_id"]
        draft = hpc_cards.load_draft(teacher.id, session, stage, sid)
        row = student_row(stage, s, raw[sid], draft, resolve, labels)
        if row["locked"] and not row["replace"]:
            skipped.append({"student_id": sid, "student_name": row["student_name"],
                            "reason": "Its activities on PARAKH share subjects. Tick 'Replace' for this student first."})
            continue
        change: Dict[str, str] = {}
        for subj in scope:
            targets = ([(grid.act_key(subj), activity_key)] if activity_key else []) + \
                      [(grid.level_key(subj, a), v) for a, v in levels.items()]
            for key, value in targets:
                if row["values"].get(key) == value:
                    continue
                if row["values"].get(key) and not replace_filled:
                    kept += 1
                    continue
                change[key] = value
        if change:
            plans.append((s, change))
            cells += len(change)

    if apply:
        if expected_cells is not None and expected_cells != cells:
            raise HTTPException(status.HTTP_409_CONFLICT, "Something changed since the preview. Please preview again.")
        for s, change in plans:
            hpc_cards.save_draft(teacher.id, session, stage, s["student_id"], change)
        from backend.services import audit
        audit.record(f"teacher:{teacher.id}", "quick_fill", "activities_grid", stage, None,
                     {"cells": cells, "students": len(plans), "activity": activity_key, "levels": levels,
                      "subjects": scope, "replace_filled": replace_filled})
    return {"applied": apply, "cells": cells, "students": len(plans), "kept": kept, "skipped": skipped,
            "subjects": [names[s] for s in scope]}


def draft_values(teacher_id: str, session: str, stage: str, student_id: str) -> Dict[str, Any]:
    """The grid's values from a student's draft (merged into workbook rows when syncing an upload)."""
    _, subjects, _ = _stage_info(stage)
    keys = set(grid.grid_keys(subjects))
    draft = hpc_cards.load_draft(teacher_id, session, stage, student_id) or {}
    return {k: v for k, v in (draft.get("values") or {}).items() if k in keys}


def clear_draft_values(teacher_id: str, session: str, stage: str, student_id: str) -> None:
    """After a save reached PARAKH, the grid reads PARAKH again instead of the old choices."""
    _, subjects, _ = _stage_info(stage)
    hpc_cards.drop_draft_keys(teacher_id, session, stage, student_id, grid.grid_keys(subjects))


def summary_text(stage: str, values: Dict[str, str], labels: Dict[str, str]) -> str:
    _, subjects, names = _stage_info(stage)
    return grid.summary_text(subjects, names, values, labels)


def workbook_summaries(teacher, session: str, stages: List[str], roster_for) -> Dict[str, Dict[str, str]]:
    """{stage: {student_id: summary}} from each student's PARAKH baseline with the grid's draft on top."""
    out = {}
    actor = activity_library.Actor("TEACHER", teacher.id, teacher.school_id, teacher.teacher_name)
    for stage in stages:
        with SessionLocal() as db:                 # names from the library; no PARAKH call on download
            labels = {e["key"]: e["label"] for e in activity_library.library_entries(db, actor, stage).values()}
        out[stage] = {s["student_id"]: summary_text(stage, {**(s.get("grid_baseline") or {}),
                                                            **draft_values(teacher.id, session, stage, s["student_id"])},
                                                    labels)
                      for s in roster_for(stage) if "grid_baseline" in s}   # older class lists: left as they are
    return out


def import_old_layout(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], rows: Dict[str, Dict[str, Any]],
                      apply: bool, expected_cells: Optional[int]) -> Dict[str, Any]:
    """Brings activity choices from an old-layout workbook into the grid (only where they differ)."""
    session = hpc_cards.check_session(client, None, writing=apply)
    st, subjects, names = _stage_info(stage)
    entries, labels, resolve = _context(client, teacher, stage)
    raw = _portal_parts(client, teacher.id, stage, students, False)
    plans, cells, unknown = [], 0, []
    for s in students:
        sid = s["student_id"]
        old = grid.from_old_columns(subjects, names, rows.get(sid) or {})
        if not old:
            continue
        row = student_row(stage, s, raw[sid], hpc_cards.load_draft(teacher.id, session, stage, sid), resolve, labels)
        change = {k: v for k, v in old.items() if row["values"].get(k) != v}
        allowed = {e["key"] for e in entries} | set(grid.current(subjects, _parts(stage, raw[sid])["part_b"],
                                                                 grid.typed_keys(resolve)).values.values())
        if any(k.startswith("b_act_") and v not in allowed for k, v in change.items()):
            unknown.append(row["student_name"])
            continue
        if change:
            plans.append((s, change))
            cells += len(change)
    if apply:
        if expected_cells is not None and expected_cells != cells:
            raise HTTPException(status.HTTP_409_CONFLICT, "Something changed since the preview. Please preview again.")
        for s, change in plans:
            hpc_cards.save_draft(teacher.id, session, stage, s["student_id"], change)
        from backend.services import audit
        audit.record(f"teacher:{teacher.id}", "import_old_layout", "activities_grid", stage, None,
                     {"cells": cells, "students": len(plans)})
    return {"applied": apply, "cells": cells, "students": len(plans),
            "not_available": unknown, "names": [s.get("student_name", "") for s, _ in plans]}
