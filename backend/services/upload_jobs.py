"""
Checking and uploading a teacher's filled workbook.

check_workbook()  dry run: reads every student's current portal data, applies the workbook
                  and runs the portal's own checks. Nothing is written.
run_job()         background task: syncs every student marked Sync=Yes and records the
                  outcome of each one in student_records as it goes.
"""
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.database import SessionLocal
from backend.hpc import sync, workbook
from backend.hpc.portal import Portal
from backend.models.entities import StudentRecord, UploadJob


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


def change_summary(changes: List[str], names: int = 6) -> str:
    """'A1 (14 fields), C (3 fields), Part B activities. First: Mother Tongue, ...' (field names, no values)."""
    counts: Dict[str, int] = {}
    for c in changes:
        if ": " in c:
            part = c.split(": ", 1)[0]
            counts[part] = counts.get(part, 0) + 1
    parts = [f"{p} ({n} field{'s' if n != 1 else ''})" for p, n in counts.items()]
    if "Part B activities" in changes:
        parts.append("Part B activities")
    first = [c.split(": ", 1)[1] for c in changes if ": " in c][:names]
    return ", ".join(parts) + (f". First: {', '.join(first)}" + (" ..." if len(changes) > names + 1 else "") if first else "")


def check_workbook(client: Portal, path: Path, teacher_id: Optional[str] = None) -> Dict[str, Any]:
    """Validation report in the shape the web app shows."""
    rows = workbook.read(path)
    row_numbers = {sid: i for i, sid in enumerate(rows, start=3)}     # Students sheet row
    exception_problems: List[str] = []
    results = sync.sync_workbook(client, path, dry_run=True, exception_problems=exception_problems,
                                 **_grid_hooks(client, teacher_id))
    meta = workbook.template_info(path)
    included = set(meta.get("included") or [])
    ready_as_of = str(meta.get("ready_as_of") or "").replace("T", " ")[:16]
    for r in results:                                    # Part B changed on the dashboard after the download
        if r.student_id in included and any(e.startswith("Part B") for e in r.errors):
            r.errors = [f"{e.partition(': ')[0]}: no longer ready since the file was made (ready as of {ready_as_of} UTC)"
                        f" - {e.partition(': ')[2]}" if e.startswith("Part B") else e for e in r.errors]
    errors: List[Dict[str, Any]] = []
    for r in results:
        for message in r.errors:
            part, _, detail = message.partition(": ")
            errors.append({"row": row_numbers.get(r.student_id, 0), "field": f"{r.name} ({r.stage}) - {part}",
                           "message": detail or message, "severity": "ERROR", "sheet": part,
                           "rejected_value": None, "guidance": ""})
    ready = [r for r in results if r.status == "READY"]
    skipped = [r for r in results if r.status == "SKIPPED"]
    warnings = [{"row": row_numbers.get(r.student_id, 0), "field": r.name, "message": "Sync is set to No - skipped",
                 "severity": "WARNING", "sheet": "Students", "rejected_value": None, "guidance": ""} for r in skipped]
    for message in exception_problems:
        warnings.append({"row": 0, "field": "Exceptions", "message": message, "severity": "WARNING", "sheet": "Exceptions",
                         "rejected_value": None, "guidance": ""})
    for r in ready:
        if r.changes:
            warnings.append({"row": row_numbers.get(r.student_id, 0), "field": f"Student {r.student_id}",
                             "message": "Will change on PARAKH: " + change_summary(r.changes),
                             "severity": "INFO", "sheet": r.stage, "rejected_value": None, "guidance": ""})
    old = old_layout_rows(rows)
    if old:
        warnings.append({"row": 0, "field": "Part B", "severity": "WARNING", "sheet": "B", "rejected_value": None,
                         "message": f"This file uses the old Activity columns ({len(old)} student(s) have them filled in). "
                                    "Those columns are no longer read: activities and levels are set on the Activities tab. "
                                    "Use 'Import from this file' there to bring them in.",
                         "guidance": ""})
    return {
        "is_valid": bool(ready),
        "total_records": len(ready),
        "detected_stage": ", ".join(workbook.detect_stages(path)),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "seeder_working_days": "",
        "seeder_max_marks": "",
        "ready_students": [r.student_id for r in ready],
    }


# What each running job is doing right now (in memory; the database keeps the results).
_live: Dict[str, Dict[str, Any]] = {}
_live_lock = threading.Lock()
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


def run_job(job_id: str, client: Portal, path: str, teacher_id: Optional[str] = None) -> None:
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
                                       else f"Saved: {', '.join(result.saved_parts)}" if result.saved_parts else None)
            row.completed_at = datetime.utcnow()
            job.success_count = sum(1 for r in records.values() if r.status == "SUCCESS")
            job.failed_count = sum(1 for r in records.values() if r.status in ("FAILED", "INVALID"))
            db.commit()

        from backend.services import audit
        actor = f"teacher:{teacher_id}" if teacher_id else "unknown"
        audit.record(actor, "upload_sync_start", "upload_job", job_id, None, {"students": len(records)})

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
                activity_grid.forget(teacher_id, result.stage, result.student_id)
                activity_grid.clear_draft_values(teacher_id, client.ay, result.stage, result.student_id)

        from backend.services import snapshots
        owner = f"teacher_{teacher_id}" if teacher_id else "unknown"
        sync.sync_workbook(client, Path(path), on_result=record_and_tidy, **_grid_hooks(client, teacher_id),
                           before_save_for=lambda stage: snapshots.hook(owner, stage, f"workbook upload (job {job_id[:8]})"),
                           on_step=step)
        done = [r for r in records.values() if r.status != "SKIPPED"]
        job.status = ("COMPLETED" if done and all(r.status == "SUCCESS" for r in done)
                      else "PARTIAL_SUCCESS" if any(r.status == "SUCCESS" for r in done) else "FAILED")
        audit.record(actor, "upload_sync_end", "upload_job", job_id, None,
                     {"status": job.status, "success": job.success_count, "failed": job.failed_count})
    except Exception as exc:
        db.rollback()
        job.status = "FAILED"
        for r in job.records:
            if r.status in ("PENDING", "IN_PROGRESS"):
                r.status, r.error_message = "FAILED", f"Upload stopped: {exc}"
    finally:
        job.completed_at = datetime.utcnow()
        db.commit()
        db.close()


def recover_interrupted_jobs() -> int:
    """Jobs left IN_PROGRESS by a server restart are marked FAILED (re-upload to continue)."""
    db = SessionLocal()
    try:
        stuck = db.query(UploadJob).filter(UploadJob.status.in_(["PENDING", "IN_PROGRESS"])).all()
        for job in stuck:
            job.status = "FAILED"
            job.completed_at = datetime.utcnow()
            for r in job.records:
                if r.status in ("PENDING", "IN_PROGRESS", "VALIDATED"):
                    r.status, r.error_message = "FAILED", "Server restarted during upload. Upload the file again."
        db.commit()
        return len(stuck)
    finally:
        db.close()
