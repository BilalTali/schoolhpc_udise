"""
Checking and uploading a teacher's filled workbook.

check_workbook()  the upload's check, from the file alone: who can be synced, and which cells keep
                  the others out. Nothing is read from PARAKH and nothing is written.
run_job()         background task: syncs every student marked Sync=Yes and records the
                  outcome of each one in student_records as it goes.
"""
import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.hpc.xl import grid_sheets, keep_text
from backend.database import SessionLocal
from backend.hpc import sync, workbook
from backend.hpc.portal import Portal, stage_code
from backend.hpc.stages import get_stage
from backend.models.entities import UploadJob


def file_settings(client: Portal, teacher_id: Optional[str], path: Path, choices: bool = True) -> Dict[str, Dict[str, Any]]:
    """The class settings each stage's Settings sheet holds (the teacher may change them in the file), checked with
    the same rules as the web app's Class settings: {stage: {"values", "problems", "changes", "sheet"}}.
    choices=False: Medium and Rural/Urban are not checked against PARAKH's lists (nothing is asked of PARAKH)."""
    if not teacher_id:
        return {}
    from openpyxl import load_workbook
    from backend.hpc import template
    from backend.services import class_settings, hpc_cards
    wb = load_workbook(path)
    meta = template.info(wb)
    if not meta.get("is_template"):
        return {}
    stages = meta.get("stages") or []
    out = {}
    for stage, raw in template.read_settings(wb, stages).items():
        try:
            if not choices:
                raise LookupError("not asked")
            lk = hpc_cards.lookups_for(f"teacher_{teacher_id}", client, stage)
            medium, location = list(lk.options(lk.medium)), list(lk.options(lk.location))
        except Exception:                                 # PARAKH's lists not at hand: the choices are not checked
            medium = location = None
        saved = class_settings.load(teacher_id, stage)
        now = saved.values if saved else class_settings.blank(stage)
        blank = lambda v: v in (None, "")                 # an empty cell keeps the app's setting ...
        days = raw["working_days"]                        # ... except working days: the sheet's months exactly
        raw = {**raw, **{k: now.get(k, "") for k in ("medium", "rural_urban", "declaration") if blank(raw.get(k))},
               "working_days": days if any(not blank(d) for d in days) else list(now.get("working_days") or [None] * 12),
               "max_marks": {n: (now.get("max_marks") or {}).get(n) if blank(m) else m for n, m in raw["max_marks"].items()}}
        clean, problems, _ = class_settings.validate(stage, raw, medium, location)
        names = dict(class_settings.marks_subjects(stage))
        changes = [f"{label}: {before if before not in (None, '') else '-'} -> {after if after not in (None, '') else '-'}"
                   for label, before, after in (
                       [("Medium", now.get("medium"), clean["medium"]), ("Rural/Urban", now.get("rural_urban"), clean["rural_urban"]),
                        ("Declaration", now.get("declaration"), clean["declaration"])]
                       + [(f"Working days {template.MONTH_LABELS[i]}", (now.get("working_days") or [None] * 12)[i],
                           clean["working_days"][i]) for i in range(12)]
                       + [(f"Max marks {names.get(n, n)}", (now.get("max_marks") or {}).get(n), clean["max_marks"].get(n))
                          for n in clean["max_marks"]])
                   if str(before if before is not None else "") != str(after if after is not None else "")]
        out[stage] = {"values": clean, "problems": problems, "changes": changes,
                      "sheet": template.sheet_names(stage, len(stages) > 1)["settings"]}
    return out


def save_file_settings(teacher_id: Optional[str], settings: Dict[str, Dict[str, Any]]) -> None:
    """Before an upload syncs: a stage's Settings sheet that was changed (and has no problems) becomes its class
    settings, so every student of the stage - and the next file - uses them."""
    from backend.database import SessionLocal as Session
    from backend.models.entities import Teacher
    from backend.services import class_settings
    with Session() as db:
        teacher = db.get(Teacher, teacher_id) if teacher_id else None
        if teacher is not None:
            db.expunge(teacher)
    if teacher is None:
        return
    for stage, s in settings.items():
        if s["changes"] and not s["problems"]:
            class_settings.save(teacher, stage, s["values"], None)


def _with_file_settings(hooks: Dict[str, Any], settings: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Class settings for each row: a stage's Settings sheet from the file when it has no problems, else as before."""
    if not settings:
        return hooks
    from backend.services import class_settings
    before = hooks.get("base_values")

    def settings_for(stage, sid):
        own = settings.get(stage)
        if own and not own["problems"]:
            return class_settings.row_values(stage, own["values"])
        return before(stage, sid) if before else {}
    return {**hooks, "base_values": settings_for}


def _grid_hooks(client: Portal, teacher_id: Optional[str]) -> Dict[str, Any]:
    """The Activities grid's choices live in the teacher's drafts, not in the file: add them to each row."""
    if not teacher_id:
        return {}
    from backend.services import activity_library, class_settings, class_template

    def settings_for(stage, sid):
        row = class_settings.load(teacher_id, stage)
        return class_settings.row_values(stage, row.values) if row else {}
    return {"extra_values": lambda stage, sid: class_template.dashboard_values(teacher_id, client.ay, stage, sid),
            "base_values": settings_for,
            "resolver_for": lambda stage: activity_library.resolver_for_teacher(teacher_id, stage)}


def old_layout_rows(rows: Dict[str, Dict[str, Any]]) -> List[str]:
    """Students whose row still has the old single Activity / Subjects / level columns filled in."""
    old = ("b_activity", "b_subjects", "b_awareness", "b_sensitivity", "b_creativity")
    return [sid for sid, row in rows.items() if any(str(row.get(k) or "").strip() for k in old)]


def file_cell_errors(client: Portal, teacher_id: Optional[str], path: Path, rows: Dict[str, Dict[str, Any]],
                     hooks: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every cell the save would refuse (too long, not one of the choices, a required one empty), found from the
    file alone - the same rule as the save (Field.parse on the same values), without reading PARAKH - each with
    the sheet, row and column to fix."""
    from backend.services import hpc_cards
    where, columns = workbook.layout(path)
    stages = workbook.detect_stages(path)
    base = hooks.get("base_values") or (lambda stage, sid: {})
    extra = hooks.get("extra_values") or (lambda stage, sid: {})
    lookups: Dict[str, Any] = {}
    errors: List[Dict[str, Any]] = []
    for sid, row in rows.items():
        stage = str(row.get(workbook.STAGE_KEY) or (stages[0] if len(stages) == 1 else ""))
        if not row.get(workbook.SYNC_KEY) or stage.lower() not in ("foundational", "preparatory", "middle"):
            continue
        if stage not in lookups:
            try:
                lookups[stage] = hpc_cards.lookups_for(f"teacher_{teacher_id}", client, stage) if teacher_id else None
            except Exception:
                lookups[stage] = None                     # PARAKH's lists not at hand: the full check finds these
        if lookups[stage] is None:
            continue
        values = {**base(stage, sid), **row, **extra(stage, sid)}
        sheet, line = where.get(sid, (stage, 0))
        name = str(row.get(workbook.NAME_KEY) or sid)
        for part in get_stage(stage).PARTS:
            for f in part.fields(lookups[stage]):
                if f.key not in values:
                    continue
                _, problem = f.parse(values[f.key])
                if not problem:
                    continue
                letter = columns.get(sheet, {}).get(f.key, ("", ""))[0]
                errors.append({"row": line, "field": f"{name} (ID {sid})", "student_id": sid, "severity": "ERROR", "sheet": sheet,
                               "part": part.title,
                               "message": problem[len(f.label) + 2:] if problem.startswith(f.label + ": ") else problem,
                               "column": f"{f.label} (column {letter})" if letter else (
                                   "Activities tab (Part B)" if part.code == "B" else f"{part.title} - {f.label}"),
                               "rejected_value": None, "guidance": ""})
    return errors


def check_workbook(client: Portal, path: Path, teacher_id: Optional[str] = None) -> Dict[str, Any]:
    """The upload's check, from the file alone (seconds, PARAKH is not read): every cell the save would refuse,
    with the sheet, row and column to fix. Those students are left out; every other one may be synced at once (the
    save checks each against PARAKH again before writing anything); one saved before with these same answers is
    not sent again."""
    rows = workbook.read(path)
    row_numbers = {sid: i for i, sid in enumerate(rows, start=3)}     # Students sheet row
    settings = file_settings(client, teacher_id, path)
    hooks = _with_file_settings(_grid_hooks(client, teacher_id), settings)
    errors = file_cell_errors(client, teacher_id, path, rows, hooks)
    errors += [{"row": 0, "field": f"Settings ({stage})", "message": message, "severity": "ERROR", "sheet": s["sheet"],
                "column": "Value (column B)", "rejected_value": None,
                "guidance": f"Fix it on the sheet '{s['sheet']}', or in Class settings (tab 4)."}
               for stage, s in settings.items() for message in s["problems"].values()]
    return _file_report(path, rows, row_numbers, errors, settings,
                        unchanged=already_saved(client, teacher_id, rows, hooks, path))


def _settings_notes(settings: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"row": 0, "field": f"Settings ({stage})", "severity": "INFO", "sheet": s["sheet"], "rejected_value": None,
             "guidance": "", "message": "Changed in the file - used for every student and saved as the class settings: "
                                        + "; ".join(s["changes"])}
            for stage, s in settings.items() if s["changes"] and not s["problems"]]


SAVED_ROWS = "saved_rows.json"      # per teacher: {academic year: {student id: {"fp", "at"}}}


def _saved_path(teacher_id: str) -> Path:
    from backend.services import hpc_sessions
    return hpc_sessions.session_dir("teacher", teacher_id) / SAVED_ROWS


def row_fingerprint(stage: str, sid: str, row: Dict[str, Any], hooks: Dict[str, Any]) -> str:
    """What a save sends for a student, as one hash: the file's row with the class settings and the dashboard's
    Part B answers. The Activities grid's choices are left out: they are cleared once saved (see grid_pending)."""
    from backend.hpc.stages import activity_grid as grid
    skip = set(grid.grid_keys(get_stage(stage).DOMAINS))
    base = (hooks.get("base_values") or (lambda st, s: {}))(stage, sid)
    extra = (hooks.get("extra_values") or (lambda st, s: {}))(stage, sid)
    values = {**base, **row, **extra}
    values = {k: v for k, v in values.items()
              if k not in skip and k not in (workbook.SYNC_KEY, workbook.PROBLEMS_KEY) and v not in (None, "")}
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def grid_pending(stage: str, sid: str, hooks: Dict[str, Any]) -> bool:
    """Activities-grid choices waiting for the student (made after the last save): the student has changes."""
    from backend.hpc.stages import activity_grid as grid
    keys = set(grid.grid_keys(get_stage(stage).DOMAINS))
    extra = (hooks.get("extra_values") or (lambda st, s: {}))(stage, sid)
    return any(k in keys and v not in (None, "") for k, v in extra.items())


def mark_saved(teacher_id: str, ay: str, stage: str, sid: str, row: Dict[str, Any], hooks: Dict[str, Any]) -> None:
    """After PARAKH confirmed a student's save: remember what was sent, so the same answers are not sent again."""
    path = _saved_path(teacher_id)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault(ay, {})[sid] = {"fp": row_fingerprint(stage, sid, row, hooks),
                                    "at": datetime.utcnow().isoformat(timespec="seconds") + "Z"}
    path.write_text(json.dumps(data), encoding="utf-8")


def already_saved(client: Portal, teacher_id: Optional[str], rows: Dict[str, Dict[str, Any]], hooks: Dict[str, Any],
                  path: Path) -> Dict[str, str]:
    """{student id: when saved} for students whose answers are exactly what was last saved to PARAKH."""
    if not teacher_id or not _saved_path(teacher_id).exists():
        return {}
    saved = json.loads(_saved_path(teacher_id).read_text(encoding="utf-8")).get(getattr(client, "ay", ""), {})
    stages = workbook.detect_stages(path)
    out = {}
    for sid, row in rows.items():
        stage = str(row.get(workbook.STAGE_KEY) or (stages[0] if len(stages) == 1 else ""))
        if sid not in saved or not row.get(workbook.SYNC_KEY) or row.get(workbook.PROBLEMS_KEY):
            continue
        try:
            same = (saved[sid]["fp"] == row_fingerprint(stage, sid, row, hooks) and not grid_pending(stage, sid, hooks))
        except Exception:                                  # unknown stage and the like: the gate reports it
            continue
        if same:
            out[sid] = saved[sid]["at"]
    return out


def _file_report(path: Path, rows: Dict[str, Dict[str, Any]], row_numbers: Dict[str, int],
                 errors: List[Dict[str, Any]], settings: Dict[str, Dict[str, Any]],
                 unchanged: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The upload's report from the file alone: who can be synced now, which cells keep the others out, and who
    is already saved with these same answers (not sent again)."""
    stages = workbook.detect_stages(path)
    where, _ = workbook.layout(path)
    bad = {e["student_id"] for e in errors if e.get("student_id")}
    unchanged = {sid: at for sid, at in (unchanged or {}).items() if sid not in bad}
    ready, warnings = [], []
    for sid, row in rows.items():
        sheet, line = where.get(sid, ("Students", row_numbers.get(sid, 0)))
        name = str(row.get(workbook.NAME_KEY) or sid)
        stage = str(row.get(workbook.STAGE_KEY) or (stages[0] if len(stages) == 1 else ""))
        if not row.get(workbook.SYNC_KEY):
            warnings.append({"row": line, "field": name, "message": "Sync is set to No - skipped", "severity": "WARNING",
                             "sheet": sheet, "rejected_value": None, "guidance": ""})
            continue
        if sid in unchanged:
            warnings.append({"row": line, "field": f"{name} (ID {sid})", "severity": "INFO", "sheet": sheet,
                             "rejected_value": None, "guidance": "",
                             "message": f"Already saved to PARAKH with these same answers ({unchanged[sid][:16].replace('T', ' ')} UTC) - not sent again"})
            continue
        problems = list(row.get(workbook.PROBLEMS_KEY) or [])
        if stage.lower() not in ("foundational", "preparatory", "middle"):
            problems.append(f"unknown stage '{stage}'")
        for message in problems:
            errors.append({"row": line, "field": f"{name} (ID {sid})", "student_id": sid, "severity": "ERROR",
                           "sheet": sheet, "column": "", "message": message, "rejected_value": None, "guidance": ""})
        if problems:
            bad.add(sid)
        elif sid not in bad:
            ready.append(sid)
    blocked = any(s["problems"] for s in settings.values())
    if ready and not blocked:
        warnings.insert(0, {"row": 0, "field": "File", "severity": "INFO", "sheet": "", "rejected_value": None, "guidance": "",
                            "message": f"{len(ready)} student(s) can be synced now"
                                       + (f"; {len(bad)} with a cell to fix are left out" if bad else "")
                                       + (f"; {len(unchanged)} already saved with these answers are not sent again"
                                          if unchanged else "")
                                       + ". Each one is checked against PARAKH just before it is saved: one PARAKH "
                                         "would refuse is not saved (nothing of it is written) and the others carry "
                                         "on. After the sync, download the saved and the not-saved students as two "
                                         "Excel files; fix the not-saved file and upload it."})
    warnings += _settings_notes(settings)
    old = old_layout_rows(rows)
    if old:                                               # the web app offers "Import from this file" on this note
        warnings.append({"row": 0, "field": "Part B", "severity": "WARNING", "sheet": "B", "rejected_value": None,
                         "guidance": "", "message": f"This file uses the old Activity columns ({len(old)} student(s) have "
                         "them filled in). Those columns are no longer read: activities and levels are set on the "
                         "Activities tab. Use 'Import from this file' there to bring them in."})
    return {"is_valid": bool(ready) and not blocked, "total_records": len(ready),
            "detected_stage": ", ".join(stages), "error_count": len(errors), "warning_count": len(warnings),
            "errors": errors, "warnings": warnings, "seeder_working_days": "", "seeder_max_marks": "",
            "already_saved": len(unchanged), "ready_students": ready}


RESULT_SHEET = "Upload result"


def result_workbook(path: Path, records, saved: bool) -> bytes:
    """The uploaded file again, for the saved students (saved=True) or for the ones not saved: the other rows are
    hidden and set to Sync = No, so the not-saved file can be fixed and uploaded as it is. A first sheet lists
    each student's result and, when not saved, why."""
    import io
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from backend.hpc import template
    chosen = [r for r in sorted(records, key=lambda r: r.row_number or 0)
              if r.status != "SKIPPED" and (r.status == "SUCCESS") == saved]
    keep = {r.admission_number for r in chosen}
    wb = load_workbook(path)
    for ws in wb.worksheets:
        if template.is_locked_sheet(ws.title) or ws.max_row < 2:
            continue
        key_row = next((n for n in (2, 3) if workbook.ID_KEY in [c.value for c in ws[n]]), None)
        if key_row is None:
            continue
        keys = [c.value for c in ws[key_row]]
        id_col = keys.index(workbook.ID_KEY)
        sync_col = keys.index(workbook.SYNC_KEY) if workbook.SYNC_KEY in keys else None
        for row in ws.iter_rows(min_row=key_row + 1):
            sid = row[id_col].value
            if sid in (None, ""):
                continue
            mine = str(sid).split(".")[0].strip() in keep
            if sync_col is not None:
                row[sync_col].value = "Yes" if mine else "No"
            ws.row_dimensions[row[id_col].row].hidden = not mine
    if RESULT_SHEET in wb.sheetnames:                     # a result file uploaded again: a fresh list
        del wb[RESULT_SHEET]
    ws = wb.create_sheet(RESULT_SHEET, 0)
    ws.append(["Student ID", "Student name", "Result", "Saved parts / what to fix"])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="046A38" if saved else "B91C1C")
    for r in chosen:
        ws.append([r.admission_number, r.student_name,
                   "Saved to PARAKH" if saved else "Not saved - nothing written" if r.status == "INVALID" else "Not saved",
                   (r.verification_result or "") if saved else (r.error_message or r.verification_result or "Stopped before saving")])
    for letter, width in zip("ABCD", (14, 30, 26, 110)):
        ws.column_dimensions[letter].width = width
    for row in ws.iter_rows(min_row=2):
        row[3].alignment = Alignment(wrap_text=True, vertical="top")
    wb.active = 0
    for other in wb.worksheets[1:]:
        other.sheet_view.tabSelected = False
    out = io.BytesIO()
    keep_text(wb)                                  # names from UDISE+/PARAKH stay text, never formulas
    grid_sheets(wb)                        # clear cell borders (a fill hides the gridlines)
    wb.save(out)
    return out.getvalue()


SECOND_ROUND_WAIT = 30.0          # seconds before the students PARAKH did not answer for are tried again


# What each running job is doing right now (in memory; the database keeps the results).
_live: Dict[str, Dict[str, Any]] = {}
_live_lock = threading.RLock()
LIVE_EVENTS = 60


def live_view(job_id: str) -> Dict[str, Any]:
    with _live_lock:
        live = _live.get(job_id) or {}
        return {"current": dict(live["current"]) if live.get("current") else None,
                "events": list(live.get("events", []))}


def _live_event(job_id: str, student_id: str, name: str, text: str, kind: str = "step") -> None:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with _live_lock:
        live = _live.setdefault(job_id, {"current": None, "events": []})
        if kind == "step":
            live["current"] = {"student_id": student_id, "student_name": name, "step": text, "since": now}
        else:
            live["current"] = None
        live["events"].append({"at": now, "student_id": student_id, "student_name": name, "text": text, "kind": kind})
        del live["events"][:-LIVE_EVENTS]


def run_job(job_id: str, client: Portal, path: str, teacher_id: Optional[str] = None,
            only: Optional[set] = None) -> None:
    """Saves the workbook's students to PARAKH. only: just these students (retry failed only, M-11)."""
    db = SessionLocal()
    job = db.get(UploadJob, job_id)
    try:
        job.status = "IN_PROGRESS"
        db.commit()
        records = {r.admission_number: r for r in job.records}
        names = {sid: r.student_name for sid, r in records.items()}
        started: set = set()

        def step(student_id: str, text: str) -> None:
            if student_id not in started:            # the list shows this student as being worked on
                started.add(student_id)
                row = records.get(student_id)
                if row is not None and row.status in ("PENDING", "VALIDATED"):
                    row.status = "IN_PROGRESS"
                    db.commit()
            _live_event(job_id, student_id, names.get(student_id, student_id), text)

        def record(result: sync.SyncResult) -> None:
            row = records.get(result.student_id)
            if row is None:
                return
            row.status = {"COMPLETED": "SUCCESS", "SKIPPED": "SKIPPED", "INVALID": "INVALID"}.get(result.status, "FAILED")
            row.attempt_count = (row.attempt_count or 0) + 1
            row.error_message = "; ".join(result.errors)[:4000] or None
            row.verification_result = ("Portal confirms COMPLETED" if result.status == "COMPLETED"
                                       else f"Saved: {', '.join(result.saved_parts) or 'nothing'}; failed at: {result.failed_part}"
                                       if result.failed_part
                                       else f"Saved: {', '.join(result.saved_parts)}" if result.saved_parts else None)
            row.completed_at = datetime.utcnow()
            job.success_count = sum(1 for r in records.values() if r.status == "SUCCESS")
            job.failed_count = sum(1 for r in records.values() if r.status in ("FAILED", "INVALID"))
            db.commit()

        from backend.services import audit
        actor = f"teacher:{teacher_id}" if teacher_id else "unknown"
        audit.record(actor, "upload_sync_start", "upload_job", job_id, None, {"students": len(records)})

        saved_by_stage: Dict[str, List[str]] = {}     # read again in the background once the upload ends

        def record_and_tidy(result: sync.SyncResult) -> None:
            record(result)
            outcome = {"COMPLETED": ("Saved to PARAKH", "saved"), "SKIPPED": ("Skipped (Sync = No)", "skipped")}.get(
                result.status, (("Not saved: " + "; ".join(result.errors[:2]))[:300], "failed"))
            _live_event(job_id, result.student_id, names.get(result.student_id, result.student_id), *outcome)
            if result.status != "SKIPPED":
                audit.record(actor, "save_to_parakh", "student", result.student_id, None,
                             {"stage": result.stage, "status": result.status, "saved_parts": result.saved_parts,
                              "errors": result.errors[:5], "via": f"upload job {job_id[:8]}"})
            if teacher_id and result.status == "COMPLETED":
                from backend.services import activity_grid
                saved_by_stage.setdefault(result.stage, []).append(result.student_id)
                activity_grid.forget(teacher_id, result.stage, result.student_id)
                activity_grid.clear_draft_values(teacher_id, client.ay, result.stage, result.student_id)

        from backend.services import snapshots
        owner = f"teacher_{teacher_id}" if teacher_id else "unknown"
        settings = file_settings(client, teacher_id, Path(path))
        save_file_settings(teacher_id, settings)          # the file's Settings sheets become the class settings
        hooks = _with_file_settings(_grid_hooks(client, teacher_id), settings)
        file_rows = workbook.read(Path(path))
        stages = workbook.detect_stages(Path(path))

        def remember_and_record(result: sync.SyncResult) -> None:
            if teacher_id and result.status == "COMPLETED" and result.student_id in file_rows:
                try:                                      # before the grid's choices are cleared
                    row = file_rows[result.student_id]
                    stage = str(row.get(workbook.STAGE_KEY) or result.stage or (stages[0] if len(stages) == 1 else ""))
                    mark_saved(teacher_id, client.ay, stage, result.student_id, row, hooks)
                except Exception:                         # only means it may be sent again next time
                    pass
            record_and_tidy(result)
        from backend.services import hpc_cards
        sync.sync_workbook(client, Path(path), on_result=remember_and_record, **hooks,
                           lookups_for=lambda stage: (hpc_cards.cached_lookups(owner, stage)   # the check's, else PARAKH
                                                      or sync.Lookups(client, stage_code(stage))),
                           before_save_for=lambda stage: snapshots.hook(owner, stage, f"workbook upload (job {job_id[:8]})"),
                           on_step=step, only=only)
        # a second round for the students PARAKH did not answer for (a stall, its gateway down): often fine moments later
        again = {sid for sid, r in records.items() if r.status == "FAILED" and sync.no_answer(r.error_message or "")}
        if again:
            for sid in again:
                _live_event(job_id, sid, names.get(sid, sid), "PARAKH did not answer - trying this student again", "step")
            time.sleep(SECOND_ROUND_WAIT)
            started.difference_update(again)
            sync.sync_workbook(client, Path(path), on_result=remember_and_record, **hooks,
                               lookups_for=lambda stage: (hpc_cards.cached_lookups(owner, stage)
                                                          or sync.Lookups(client, stage_code(stage))),
                               before_save_for=lambda stage: snapshots.hook(owner, stage, f"workbook upload (job {job_id[:8]}, again)"),
                               on_step=step, only=again)
        done = [r for r in records.values() if r.status != "SKIPPED"]
        job.status = ("COMPLETED" if done and all(r.status == "SUCCESS" for r in done)
                      else "PARTIAL_SUCCESS" if any(r.status == "SUCCESS" for r in done) else "FAILED")
        audit.record(actor, "upload_sync_end", "upload_job", job_id, None,
                     {"status": job.status, "success": job.success_count, "failed": job.failed_count})
        _rewarm(client, owner, saved_by_stage)
    except Exception as exc:
        db.rollback()
        job.status = "FAILED"
        for r in job.records:
            if r.status in ("PENDING", "IN_PROGRESS"):
                r.status, r.error_message = "FAILED", f"Upload stopped: {exc}"
    finally:
        job.completed_at = datetime.utcnow()
        job.active_teacher_id = None                  # the teacher may start the next upload (H-3)
        db.commit()
        db.close()


def _rewarm(client: Portal, owner: str, saved_by_stage: Dict[str, List[str]]) -> None:
    """The cards just saved were dropped from the stored copy (they changed on PARAKH): read them again quietly in
    the background, so the class screens open at once next time instead of reading the whole class then."""
    from backend.services import card_store
    for stage, ids in saved_by_stage.items():
        try:
            cols = [p.col for p in get_stage(stage).PARTS if p.code in ("A1", "A3", "A4", "B", "C")]
            card_store.warm(client, owner, client.ay, stage, ids, cols)
        except Exception:                                 # a screen reads what is missing itself
            pass


def recover_interrupted_jobs() -> int:
    """Jobs left IN_PROGRESS by a server restart are marked FAILED (re-upload to continue)."""
    db = SessionLocal()
    try:
        stuck = db.query(UploadJob).filter(UploadJob.status.in_(["PENDING", "IN_PROGRESS"])).all()
        for job in stuck:
            job.status = "FAILED"
            job.completed_at = datetime.utcnow()
            job.active_teacher_id = None
            for r in job.records:
                if r.status in ("PENDING", "IN_PROGRESS", "VALIDATED"):
                    r.status, r.error_message = "FAILED", "Server restarted during upload. Upload the file again."
        db.commit()
        return len(stuck)
    finally:
        db.close()
