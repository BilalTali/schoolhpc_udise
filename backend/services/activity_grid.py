"""
The dashboard's Activities grid: every student of a stage, per subject an activity and three levels.

Values live in the teacher's draft (the same one the card editor uses), so the card editor, the
workbook download and every save to PARAKH see the same choices. PARAKH's current Part B and Part C
are read once and cached for a few minutes; "refresh" reads them again.
Each student's problems are worked out with the same code the real save uses, so what the grid shows
is what a sync would say.
"""
import copy
import random
import re
import secrets
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


def grade_id_of(stage: str, student: Dict[str, Any]) -> Optional[int]:
    """The student's PARAKH grade id (class lists made before it was kept: found from the grade's name)."""
    gid = student.get("grade_id")
    if str(gid or "").isdigit():
        return int(gid)
    by_name = {n: i for i, n in activity_library.STAGE_GRADES.get(stage.capitalize(), {}).items()}
    return by_name.get(student.get("grade", ""))


def answers_missing(stage: str, parts: Dict[str, Any], draft_values: Dict[str, Any]) -> List[str]:
    """Required Part B answers (the student's own: self-assessment, reflection ...) that are empty - the draft's
    value where there is one, else what PARAKH holds."""
    part_b = next(p for p in get_stage(stage).PARTS if p.code == "B")
    out = []
    for f in part_b.fields(None):
        if not f.required:
            continue
        value = draft_values[f.key] if f.key in draft_values else f.read(parts["part_b"])
        if isinstance(value, list) and not value or str(value if value is not None else "").strip() in ("", "[]"):
            out.append(f.label)
    return out


def student_row(stage: str, student: Dict[str, Any], raw: Dict[str, Any], draft: Optional[Dict[str, Any]],
                resolve, labels: Dict[str, str]) -> Dict[str, Any]:
    """One grid row: values, where they came from, what PARAKH has, and what a save would complain about."""
    st, subjects, names = _stage_info(stage)
    parts = _parts(stage, raw)
    draft_values = (draft or {}).get("values") or {}
    now, values, source = sync.grid_state(stage, parts, draft_values, None, grid.typed_keys(resolve),
                                          grid.defaults_for(resolve, grade_id_of(stage, student)))
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
    missing_answers = answers_missing(stage, parts, draft_values)
    if missing_answers:                              # PARAKH counts the activities unfinished without them
        problems = [*problems, "Part B answers not filled: " + ", ".join(missing_answers)]
    covered = [s for s in subjects if values.get(grid.act_key(s))]
    return {
        "student_id": student["student_id"], "student_name": student.get("student_name", ""),
        "grade": student.get("grade", ""), "grade_id": grade_id_of(stage, student),
        "section": student.get("section", ""), "status": student.get("status", ""),
        "values": values, "source": source, "locked": now.locked, "replace": replace,
        "existing": [{**e, "subject_names": [names[s] for s in e["subjects"]],
                      "label": labels.get(e["key"], e["name"])} for e in now.existing],
        "missing_subjects": [names[s] for s in subjects if s not in covered], "missing_answers": missing_answers,
        "problems": problems, "notes": notes, "ready": not problems,
        "draft_version": (draft or {}).get("version", 0), "saved_at": (draft or {}).get("saved_at"),
    }


def _grade_names(client: Portal, teacher, stage: str) -> Dict[Any, str]:
    """PARAKH grade id -> name (e.g. 7 -> "Grade 4"), as the class list names grades; the app's own table when
    PARAKH's list cannot be read."""
    names = dict(activity_library.STAGE_GRADES.get(stage.capitalize(), {}))
    try:
        lookups = hpc_cards.lookups_for(f"teacher_{teacher.id}", client, stage)
        names.update({g["id"]: g["grade_caption"] for g in lookups.grades})
    except Exception:                                  # names are only shown; the grade id decides
        pass
    return names


def short_name(label: str) -> str:
    """What the grid shows for an activity: the library's "name (code)" label without the workbook's key or
    PARAKH's number - "Important Idea Circle (L2CG1,C-1.1)", or the code alone when it has no name."""
    label = re.sub(r"\s*\(#[^()]*\)$", "", str(label or "")).strip()
    return re.sub(r"^\d+:\s+", "", label)                        # "85: Conversation in pairs"


def _context(client: Portal, teacher, stage: str):
    """Dropdown entries, labels and the activity resolver for this teacher and stage. Until the
    Activity Library has been synced, PARAKH's own activity list is used instead. Labels are the
    activities' names only (the workbook keeps its own labels with keys)."""
    actor = activity_library.Actor("TEACHER", teacher.id, teacher.school_id, teacher.teacher_name)
    with SessionLocal() as db:
        entries = [{**e, "label": short_name(e["label"])} for e in activity_library.dropdown_entries(db, actor, stage)]
        everything = activity_library.library_entries(db, actor, stage)
    if everything:
        labels = {e["key"]: short_name(e["label"]) for e in everything.values()}
        return entries, labels, activity_library.resolver_for_teacher(teacher.id, stage)
    lookups = hpc_cards.lookups_for(f"teacher_{teacher.id}", client, stage)
    entries = [{"key": f"P{i}", "label": short_name(lookups.activity_label(i))} for i in lookups.activities]
    return entries, {e["key"]: e["label"] for e in entries}, grid.resolver_from_lookups(lookups)


def load(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], refresh: bool = False) -> Dict[str, Any]:
    session = hpc_cards.check_session(client, None, writing=False)
    st, subjects, names = _stage_info(stage)
    entries, labels, resolve = _context(client, teacher, stage)
    grade_names = _grade_names(client, teacher, stage)
    raw = _portal_parts(client, teacher.id, stage, students, refresh)
    rows = [student_row(stage, s, raw[s["student_id"]],
                        hpc_cards.load_draft(teacher.id, session, stage, s["student_id"]), resolve, labels)
            for s in students]
    return {"stage": stage, "session": session,
            "subjects": [{"code": c, "name": names[c]} for c in subjects],
            "options": [{"key": e["key"], "label": e["label"], "subjects": e.get("subjects"),
                         "grade_id": e.get("grade_id"), "grade": grade_names.get(e.get("grade_id"), "")}
                        for e in entries],
            "labels": labels, "students": rows,
            "grades": sorted({f"{r['grade']} - {r['section']}".strip(" -") for r in rows}),
            "summary": {"ready": sum(r["ready"] for r in rows), "total": len(rows),
                        "locked": sum(r["locked"] for r in rows)}}


def subjects_for(scope: List[str], activity_subjects: Optional[List[str]]) -> List[str]:
    """The subjects of scope an activity may be chosen for: only its own. All of them when its subjects are not
    known (PARAKH's own lists, before the Activity Library was synced)."""
    return [s for s in scope if activity_subjects is None or s in activity_subjects]


def wrong_grade(stage: str, entry: Dict[str, Any], grade_id: Optional[int]) -> str:
    """Why an activity cannot be chosen for a student of this grade, or "" when it can. Every activity belongs
    to one grade; activities whose subjects are not known (PARAKH's own lists) are not checked."""
    if entry.get("subjects") is None or grade_id is None or entry.get("grade_id") == grade_id:
        return ""
    names = activity_library.STAGE_GRADES.get(stage.capitalize(), {})
    if entry.get("grade_id") is None:
        return "This activity has no grade yet. Set its grade in the Activity Library first."
    return f"This activity is for {names.get(entry['grade_id'], 'another grade')}, not {names.get(grade_id, 'this grade')}."


def _check_values(stage: str, values: Dict[str, Any], entries: Dict[str, Dict[str, Any]], current_keys: set,
                  grade_id: Optional[int]) -> Dict[str, str]:
    """entries: activity key -> its dropdown entry. A new choice must be an activity of that subject and of the
    student's grade; what the student already has stays allowed."""
    _, subjects, names = _stage_info(stage)
    known = set(grid.grid_keys(subjects))
    problems = {}
    for k, v in values.items():
        if k not in known:
            problems[k] = "Unknown field."
            continue
        problem = grid.check_value(k, v)
        if problem:
            problems[k] = problem
        elif k.startswith("b_act_") and v and v not in entries and v not in current_keys:
            problems[k] = "This activity is not offered in your Activity Library (it may be turned off)."
        elif k.startswith("b_act_") and v and v not in current_keys:
            own = entries[v].get("subjects")
            if own is not None and k[len("b_act_"):] not in own:
                problems[k] = (f"This activity is for {', '.join(names.get(s, s) for s in own)}, not "
                               f"{names.get(k[len('b_act_'):], k)}. Choose one of this subject's activities.")
            elif wrong_grade(stage, entries[v], grade_id):
                problems[k] = wrong_grade(stage, entries[v], grade_id) + " Choose one of this grade's activities."
    return problems


def save(client: Portal, teacher, stage: str, student: Dict[str, Any], values: Dict[str, Any],
         base_version: Optional[int]) -> Dict[str, Any]:
    """Autosave of one student's grid values (merged into the draft)."""
    session = hpc_cards.check_session(client, None, writing=True)
    entries, labels, resolve = _context(client, teacher, stage)
    raw = _portal_parts(client, teacher.id, stage, [student], False)[student["student_id"]]
    _, subjects, _ = _stage_info(stage)
    now = grid.current(subjects, _parts(stage, raw)["part_b"], grid.typed_keys(resolve))
    problems = _check_values(stage, values, {e["key"]: e for e in entries}, set(now.values.values()),
                             grade_id_of(stage, student))
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"problems": problems})
    clean = {k: ("" if v is None else str(v).strip()) for k, v in values.items()}
    draft = hpc_cards.save_draft(teacher.id, session, stage, student["student_id"], clean, base_version)
    return student_row(stage, student, raw, draft, resolve, labels)


EACH_SUBJECT = "each_subject"     # quick fill: every subject its own activity for the student's grade


def quick_fill(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], activity_key: str,
               subject_codes: Optional[List[str]], levels: Dict[str, str], replace_filled: bool,
               apply: bool, expected_cells: Optional[int], replace_on_parakh: bool = False,
               mix_seed: Optional[str] = None) -> Dict[str, Any]:
    """Fills many cells at once. Without apply it only reports what would change. activity_key EACH_SUBJECT gives
    every subject its own activity for each student's grade (the default one). Cells the grid only filled in by
    itself (source "default"), and cells holding an activity of another subject or grade, count as empty.
    replace_on_parakh ticks 'Replace activities on PARAKH' for the students filled (locked ones included), so
    their older activities that no subject uses any more are removed on the next save.
    A level "Mixed": for each subject and ability, Beginner / Proficient / Advanced dealt out in shuffled rounds
    over the students (each about equally often). The deal comes from mix_seed, so the apply writes exactly what
    its preview showed (the preview returns the seed it used)."""
    session = hpc_cards.check_session(client, None, writing=apply)
    st, subjects, names = _stage_info(stage)
    entries, labels, resolve = _context(client, teacher, stage)
    each = activity_key == EACH_SUBJECT
    if activity_key and not each and activity_key not in {e["key"] for e in entries}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose an activity from your Activity Library.")
    bad_levels = {a: v for a, v in levels.items()
                  if a not in dict(grid.ABILITIES) or (v not in grid.LEVEL_TO_PORTAL and v != MIXED)}
    if bad_levels:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Levels must be Beginner, Proficient, Advanced or Mixed.")
    if not activity_key and not levels and not replace_on_parakh:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose an activity or at least one level to fill in.")
    by_key = {e["key"]: e for e in entries}

    def misplaced(subj: str, key: str, grade_id: Optional[int]) -> bool:
        """An activity in a cell where it does not belong (another subject or grade, or gone from the library)."""
        e = by_key.get(key)
        if e is None:
            return bool(key)
        return (e.get("subjects") is not None and subj not in e["subjects"]) or bool(wrong_grade(stage, e, grade_id))
    scope = [s for s in subjects if not subject_codes or s in subject_codes]
    entry = next((e for e in entries if e["key"] == activity_key), {})
    if activity_key and not each:                     # an activity goes only under its own subjects
        own = entry.get("subjects")
        scope = subjects_for(scope, own)
        if not scope:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"This activity is for {', '.join(names.get(s, s) for s in own or [])}. "
                                "Choose that subject, or another activity.")
    raw = _portal_parts(client, teacher.id, stage, students, False)
    mixing = [a for a, v in levels.items() if v == MIXED]
    seed = (mix_seed or secrets.token_hex(4)) if mixing else None
    dealt = _deal(seed, stage, scope, mixing, [s["student_id"] for s in students]) if mixing else {}

    plans, skipped, cells, kept, none_for, older = [], [], 0, 0, [], []
    for s in students:
        sid = s["student_id"]
        draft = hpc_cards.load_draft(teacher.id, session, stage, sid)
        row = student_row(stage, s, raw[sid], draft, resolve, labels)
        has_older = (row["locked"] or any("would remove" in p for p in row["problems"])) and not row["replace"]
        if has_older and not replace_on_parakh:
            older.append(row["student_name"])
        if row["locked"] and not row["replace"] and not replace_on_parakh:
            skipped.append({"student_id": sid, "student_name": row["student_name"],
                            "reason": "Its activities on PARAKH share subjects. Tick 'Replace' for this student first."})
            continue
        if activity_key and not each and wrong_grade(stage, entry, row["grade_id"]):   # only to its own grade
            skipped.append({"student_id": sid, "student_name": row["student_name"],
                            "reason": wrong_grade(stage, entry, row["grade_id"])})
            continue
        own = (grid.defaults_for(resolve, row["grade_id"]) or {}) if each else {}
        change: Dict[str, str] = {}
        for subj in scope:
            key_for_subject = own.get(subj, "") if each else activity_key
            if each and not key_for_subject:
                gap = f"{row['grade'] or 'no grade'}: {names[subj]}"
                if gap not in none_for:
                    none_for.append(gap)
            targets = ([(grid.act_key(subj), key_for_subject)] if key_for_subject else []) + \
                      [(grid.level_key(subj, a), dealt[(sid, subj, a)] if v == MIXED else v) for a, v in levels.items()]
            for key, value in targets:
                # a filled-in default is not a choice, nor is an activity that does not belong in this cell
                chosen = row["values"].get(key) and row["source"].get(key) != "default" \
                    and not (key.startswith("b_act_") and misplaced(subj, row["values"][key], row["grade_id"]))
                if chosen and row["values"].get(key) == value:
                    continue
                if chosen and not replace_filled:
                    kept += 1
                    continue
                change[key] = value
        if replace_on_parakh and row["existing"] and not row["replace"]:
            change[grid.REPLACE_KEY] = "Yes"
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
                      "subjects": scope, "replace_filled": replace_filled, "replace_on_parakh": replace_on_parakh})
    return {"applied": apply, "cells": cells, "students": len(plans), "kept": kept, "skipped": skipped,
            "subjects": [names[s] for s in scope], "no_activity": none_for, "older_on_parakh": older, "mix_seed": seed}


MIXED = "Mixed"


def _deal(seed: str, stage: str, subjects: List[str], abilities: List[str], student_ids: List[str]) -> Dict[tuple, str]:
    """{(student, subject, ability): level}: for each subject and ability, the three levels in shuffled rounds over
    the students (in id order), so each comes up about equally often - the same every time for the same seed."""
    out = {}
    order = sorted(student_ids)
    for subj in subjects:
        for ability in abilities:
            rng = random.Random(f"{seed}:{stage}:{subj}:{ability}")
            dealing: List[str] = []
            for sid in order:
                if not dealing:
                    dealing = list(grid.LEVEL_TO_PORTAL)
                    rng.shuffle(dealing)
                out[(sid, subj, ability)] = dealing.pop()
    return out


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


def mix_all(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], apply: bool,
            seed: Optional[str] = None) -> Dict[str, Any]:
    """Global Mix, the Activities grid part: every empty cell of every student is filled - each subject an activity
    of that subject and the student's grade from the library (when there are several, they are dealt in turn over
    the students, so each is used about equally) and each empty level Beginner / Proficient / Advanced dealt the
    same way. A cell the teacher chose is kept; a student whose activities on PARAKH share subjects is skipped (as in
    quick fill). Without apply it only counts."""
    session = hpc_cards.check_session(client, None, writing=apply)
    st, subjects, names = _stage_info(stage)
    entries, labels, resolve = _context(client, teacher, stage)
    seed = seed or secrets.token_hex(4)
    raw = _portal_parts(client, teacher.id, stage, students, False)
    pools: Dict[tuple, List[str]] = {}
    any_subject: List[str] = []                        # PARAKH's own lists (no library yet): subjects not known
    for e in entries:
        if e.get("subjects") is None:
            any_subject.append(e["key"])
        for subj in e.get("subjects") or []:
            pools.setdefault((e.get("grade_id"), subj), []).append(e["key"])
    rounds: Dict[tuple, List[str]] = {}

    def deal(pool_key: tuple, pool: List[str]) -> str:
        if not rounds.get(pool_key):
            rounds[pool_key] = sorted(pool)
            random.Random(f"{seed}:{stage}:{pool_key}:{len(rounds)}").shuffle(rounds[pool_key])
        return rounds[pool_key].pop()

    plans, skipped, no_activity, cells = [], [], set(), 0
    for s in sorted(students, key=lambda x: str(x["student_id"])):
        sid = s["student_id"]
        row = student_row(stage, s, raw[sid], hpc_cards.load_draft(teacher.id, session, stage, sid), resolve, labels)
        if row["locked"] and not row["replace"]:
            skipped.append({"student_id": sid, "student_name": row["student_name"],
                            "reason": "Its activities on PARAKH share subjects. Tick 'Replace' for this student first."})
            continue
        change: Dict[str, str] = {}
        for subj in subjects:
            key = grid.act_key(subj)
            current = row["values"].get(key)
            entry = next((e for e in entries if e["key"] == current), None)
            kept = current and row["source"].get(key) != "default" and entry is not None \
                and (entry.get("subjects") is None or subj in entry["subjects"]) and not wrong_grade(stage, entry, row["grade_id"])
            if not kept:
                pool = pools.get((row["grade_id"], subj)) or any_subject
                if not pool:                                   # the library has none: the grid's own default, if any
                    fallback = (grid.defaults_for(resolve, row["grade_id"]) or {}).get(subj)
                    if fallback:
                        change[key] = fallback
                    else:
                        no_activity.add(f"{row['grade'] or 'no grade'}: {names[subj]}")
                elif current != (chosen := deal((row["grade_id"], subj), pool)) or row["source"].get(key) == "default":
                    change[key] = chosen
            for ability, _ in grid.ABILITIES:
                lkey = grid.level_key(subj, ability)
                if not row["values"].get(lkey):
                    change[lkey] = deal(("level", subj, ability), list(grid.LEVEL_TO_PORTAL))
        if change:
            plans.append((s, change))
            cells += len(change)
    if apply:
        for s, change in plans:
            hpc_cards.save_draft(teacher.id, session, stage, s["student_id"], change)
    return {"cells": cells, "students": len(plans), "skipped": skipped, "no_activity": sorted(no_activity), "seed": seed}
