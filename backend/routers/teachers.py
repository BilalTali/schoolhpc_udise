"""
Teacher endpoints: HPC portal session, class roster + workbook, and workbook upload.
"""
import csv
import hashlib
import io
import json
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.hpc import portal, sync, workbook
from backend.hpc.portal import PortalError
from backend.models.entities import StudentRecord, Teacher, UploadJob
from backend.schemas.schemas import (
    HpcCaptchaRequest, HpcCredentialsRequest, HpcOtpRequest, HpcSessionStatusResponse, HpcStartSessionRequest,
    UploadJobResponse, ValidationReportResponse,
)
from backend.services import audit, card_store, hpc_sessions, upload_jobs
from backend.services.safe_paths import inside
from backend.services.auth_service import require_teacher

router = APIRouter(prefix="/teacher", tags=["Teacher"])
KIND = "teacher"


SUPPORTED = ("Foundational", "Preparatory", "Middle")


def teacher_stages(teacher: Teacher) -> List[str]:
    """Stages assigned in this app plus the ones the portal lists for the teacher, in stage order."""
    names = {s.strip().lower() for s in teacher.stages}
    sess = hpc_sessions.load_session(KIND, teacher.id)
    if sess:
        names |= {str(s).lower() for s in sess.staff.get("hpc_stage") or []}
    return [s for s in SUPPORTED if s.lower() in names]


def _stage(teacher: Teacher, stage: Optional[str]) -> str:
    stages = teacher_stages(teacher)
    name = (stage or (stages[0] if stages else "")).strip().capitalize()
    if name not in SUPPORTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unsupported stage '{stage}'. Use one of {', '.join(SUPPORTED)}.")
    if stages and name not in stages:                 # only the teacher's own stages (L-3)
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"{name} is not one of your stages ({', '.join(stages)}). Ask your school to add it.")
    return name


def _portal(teacher: Teacher):
    return hpc_sessions.portal_for(KIND, teacher.id, teacher.hpc_login_id, teacher.hpc_password)


def _roster_file(teacher: Teacher, stage: str):
    return inside(hpc_sessions.session_dir(KIND, teacher.id), f"roster_{stage.lower()}.json")


def _workbook_path(teacher: Teacher):
    return hpc_sessions.session_dir(KIND, teacher.id) / "workbook.xlsx"


# ---------------------------------------------------------------------------
# HPC portal session
# ---------------------------------------------------------------------------

@router.get("/hpc/status", response_model=HpcSessionStatusResponse)
def hpc_status(teacher: Teacher = Depends(require_teacher)):
    result = hpc_sessions.status_of(KIND, teacher.id)
    return HpcSessionStatusResponse(
        logged_in=result["logged_in"], user=result.get("user"), school=result.get("school"),
        role=result.get("role"), reason=result.get("reason"), captcha_mode=result.get("captcha_mode", "typed"),
        has_credentials=bool(teacher.hpc_login_id and teacher.hpc_password_encrypted),
        saved_hpc_login_id=teacher.hpc_login_id,
        stages=teacher_stages(teacher),
    )


@router.post("/hpc/save-credentials")
def save_credentials(payload: HpcCredentialsRequest, teacher: Teacher = Depends(require_teacher),
                     db: Session = Depends(get_db)):
    teacher.hpc_login_id = payload.hpc_login_id.strip()
    teacher.hpc_password = payload.hpc_password
    db.commit()
    audit.record(f"teacher:{teacher.id}", "save_parakh_login", "settings", teacher.id, None,
                 {"hpc_login_id": teacher.hpc_login_id})        # never the password
    return {"success": True, "message": "HPC credentials saved. Click 'Start Session' to connect."}


@router.post("/hpc/start-session")
def start_session(payload: HpcStartSessionRequest, teacher: Teacher = Depends(require_teacher)):
    login_id = payload.hpc_login_id or teacher.hpc_login_id
    password = payload.hpc_password or teacher.hpc_password
    if not login_id or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "HPC credentials not found. Save your HPC Login ID and password first.")
    result = hpc_sessions.start(KIND, teacher.id, login_id, password)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "HPC login failed."))
    return result


@router.post("/hpc/refresh-session")
def refresh_session(teacher: Teacher = Depends(require_teacher)):
    """Logs in again with the saved credentials."""
    if not teacher.hpc_login_id or not teacher.hpc_password_encrypted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "HPC credentials not saved. Save your HPC Login ID and password first.")
    result = hpc_sessions.start(KIND, teacher.id, teacher.hpc_login_id, teacher.hpc_password)
    return {**result, "success": result.get("status") in ("authenticated", "captcha_required", "otp_required"),
            "message": result.get("message") or result.get("error") or "Session refreshed."}


@router.post("/hpc/verify-captcha")
def verify_captcha(payload: HpcCaptchaRequest, teacher: Teacher = Depends(require_teacher)):
    """The answer to the captcha picture from start-session; logs in (or asks for the OTP next)."""
    result = hpc_sessions.verify_captcha(KIND, teacher.id, payload.answer)
    if not result.get("success") and result.get("status") != "captcha_required":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "HPC login failed."))
    _warm_up(teacher, result)
    return result


def _warm_up(teacher: Teacher, result) -> None:
    """Once connected: the class's cards are read quietly in the background, so the screens open at once."""
    if result.get("status") != "authenticated":
        return
    from backend.hpc.stages import get_stage
    try:
        client = _portal(teacher)
    except HTTPException:
        return
    for name in teacher_stages(teacher):
        path = _roster_file(teacher, name)
        students = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        cols = [p.col for p in get_stage(name).PARTS if p.code in ("A1", "A3", "A4", "B", "C")]
        if students:
            card_store.warm(client, f"teacher_{teacher.id}", client.ay, name, [s["student_id"] for s in students], cols)


@router.get("/activity")
def server_activity(teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    """Everything the server is doing for this teacher now (for the web app's "Server is working" strip):
    class checks, cards read in the background, re-checks against PARAKH, and a running upload."""
    from backend.services import class_template
    tasks = []
    for stage in teacher_stages(teacher):
        job = class_template.latest(teacher.id, stage)
        if job and job.get("status") == "RUNNING":
            tasks.append({"kind": "class_check", "stage": stage, "done": job.get("done", 0), "total": job.get("total", 0)})
    stage_names = {s.lower(): s for s in teacher_stages(teacher)}
    for t in card_store.running_for(f"teacher_{teacher.id}"):
        tasks.append({**t, "stage": stage_names.get(t["stage"], t["stage"].title())})
    upload = db.query(UploadJob).filter(UploadJob.teacher_id == teacher.id,
                                        UploadJob.status.in_(["PENDING", "IN_PROGRESS"])).first()
    if upload:
        done = sum(1 for r in upload.records if r.status not in ("PENDING", "IN_PROGRESS"))
        tasks.append({"kind": "upload", "stage": upload.detected_stage, "done": done, "total": len(upload.records)})
    return {"parakh_connected": hpc_sessions.status_of(KIND, teacher.id).get("logged_in", False), "tasks": tasks}


@router.post("/hpc/new-captcha")
def new_captcha(teacher: Teacher = Depends(require_teacher)):
    result = hpc_sessions.new_captcha(KIND, teacher.id)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "Please click Connect again."))
    return result


@router.post("/hpc/verify-otp")
def verify_otp(payload: HpcOtpRequest, teacher: Teacher = Depends(require_teacher)):
    result = hpc_sessions.verify_otp(KIND, teacher.id, payload.otp)
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, result.get("error", "Invalid OTP."))
    _warm_up(teacher, result)
    return result


@router.post("/hpc/end-session")
def end_session(teacher: Teacher = Depends(require_teacher)):
    audit.record(f"teacher:{teacher.id}", "disconnect_parakh", "settings", teacher.id)
    return hpc_sessions.end(KIND, teacher.id)


# ---------------------------------------------------------------------------
# Roster and class workbook
# ---------------------------------------------------------------------------

# "Fetch from PARAKH" reads every student's whole card (about 5 minutes for 60 students at the request
# limit), so it runs in the background and the web app shows its progress.
_fetch_jobs: Dict[str, Dict[str, Any]] = {}
_fetch_lock = threading.Lock()
_submit_lock = threading.Lock()           # one upload per teacher: checked and started under this lock (H-3)


def _fetch_view(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if job is None:
        return None
    with _fetch_lock:
        view = {k: v for k, v in job.items() if k not in ("t0", "by_stage")}
    done, total = view["done"], view["total"]
    elapsed = time.time() - job["t0"]
    view["seconds_left"] = int(elapsed / done * (total - done)) if done and view["status"] == "RUNNING" else 0
    return view


def _not_yours_note(stage: str, classes: List[Dict[str, Any]]) -> str:
    """Why some students PARAKH lists are not in the app: this login is not their class teacher."""
    what = ", ".join(f"{c['count']} in {c['grade']} {c['section']}".strip() for c in classes)
    return (f"{stage}: PARAKH lists {what}, but this login is not the class teacher of that class, so PARAKH does not "
            f"let it open their cards. Ask the school to make you class teacher of that class on PARAKH, then fetch again.")


def _run_fetch(job: Dict[str, Any], teacher: Teacher, client, stages: List[str]) -> None:
    def roster_read(name, students):
        _roster_file(teacher, name).write_text(json.dumps(students, ensure_ascii=False, indent=1), encoding="utf-8")
        hidden = getattr(client, "not_yours_classes", {}).get(name) or []
        with _fetch_lock:
            if hidden:
                job["notes"].append(_not_yours_note(name, hidden))
            job["total"] += len(students)
            job["rosters"][name] = len(students)
            job["stage_now"] = name

    def one_done(name):
        with _fetch_lock:
            job["done"] += 1

    keep = lambda name, data: card_store.put_many(f"teacher_{teacher.id}", client.ay, name, data)   # screens open at once
    try:
        _, by_stage = sync.export_workbook(client, stages, _workbook_path(teacher), on_students=keep,
                                           on_roster=roster_read, on_each=one_done)
        for name, students in by_stage.items():          # now with gender and admission numbers
            _roster_file(teacher, name).write_text(json.dumps(students, ensure_ascii=False, indent=1), encoding="utf-8")
        with _fetch_lock:
            job["status"] = "COMPLETED"
            job["summary"] = ", ".join(f"{name}: {len(st)}" for name, st in by_stage.items())
    except Exception as exc:
        with _fetch_lock:
            job["status"], job["error"] = "FAILED", str(exc)
    finally:
        job["finished_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"


@router.post("/roster/sync")
def sync_roster(stage: Optional[str] = Query(None), teacher: Teacher = Depends(require_teacher)):
    """
    Starts fetching all of the teacher's stages from the portal (every student's current HPC data, into one
    workbook and the app's stored copy). Returns at once; GET /roster/sync shows the progress.
    """
    stage = _stage(teacher, stage)
    stages = teacher_stages(teacher) or [stage]
    client = _portal(teacher)
    with _fetch_lock:
        running = _fetch_jobs.get(teacher.id)
        if running and running["status"] == "RUNNING":
            return _fetch_view(running)
        job = {"status": "RUNNING", "stages": stages, "stage_now": None, "rosters": {}, "done": 0, "total": 0,
               "summary": "", "notes": [], "error": None, "started_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
               "finished_at": None, "t0": time.time()}
        _fetch_jobs[teacher.id] = job
    threading.Thread(target=_run_fetch, args=(job, teacher, client, stages), daemon=True, name="fetch-roster").start()
    return _fetch_view(job)


@router.get("/roster/sync")
def sync_roster_status(teacher: Teacher = Depends(require_teacher)):
    """The latest fetch: running or finished, how many students read of how many, per stage."""
    return {"job": _fetch_view(_fetch_jobs.get(teacher.id))}


@router.get("/register/students")
def register_students(stage: Optional[str] = Query(None), teacher: Teacher = Depends(require_teacher)):
    """The teacher's students from the School Register: only the classes PARAKH maps to this teacher. No PARAKH
    request is made here."""
    from backend.services import school_register
    if not school_register.teacher_classes(teacher):
        sess = hpc_sessions.load_session(KIND, teacher.id)
        if sess:                                   # the classes the teacher's own PARAKH sign-in carries
            school_register.remember_teacher_mapping(teacher, sess.staff)
    stage = _stage(teacher, stage) if stage else None
    rows = school_register.for_teacher(teacher, stage)
    return {"students": rows, "total": len(rows),
            "note": "" if rows or school_register.teacher_classes(teacher) else
            "Your classes are not known yet: ask the school to fetch from PARAKH, or connect to PARAKH once."}


@router.get("/roster")
def cached_roster(stage: Optional[str] = Query(None), teacher: Teacher = Depends(require_teacher)):
    stage = _stage(teacher, stage)
    path = _roster_file(teacher, stage)
    students = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return {"success": True, "total_students": len(students), "stage": stage, "students": students}


@router.get("/roster/download")
def download_workbook(stage: Optional[str] = Query(None), teacher: Teacher = Depends(require_teacher)):
    """The workbook with all of the teacher's stages (the stage parameter is accepted but not needed)."""
    path = _workbook_path(teacher)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fetch the roster first (Sync Roster), then download.")
    sess = hpc_sessions.load_session(KIND, teacher.id)
    if sess:                                          # latest Activities tab choices into the read-only column
        from backend.services import activity_grid
        session = str(sess.staff.get("school_cur_ay_code") or "")
        summaries = activity_grid.workbook_summaries(teacher, session, workbook.detect_stages(path), lambda st: (
            json.loads(_roster_file(teacher, st).read_text(encoding="utf-8")) if _roster_file(teacher, st).exists() else []))
        workbook.set_activity_summaries(path, summaries)
    return FileResponse(path, filename="HPC_Class_Workbook.xlsx",
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# Upload: check, then sync in the background
# ---------------------------------------------------------------------------

def _upload_path(teacher: Teacher, file_name: str):
    return inside(hpc_sessions.session_dir(KIND, teacher.id), f"uploaded_{Path(file_name).name}")


def _save_upload(file: UploadFile, path) -> None:
    """Writes the upload, stopping (and keeping nothing) once it is larger than the limit (M-6)."""
    from backend import config
    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > config.MAX_UPLOAD_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        f"The file is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB. "
                                        "Upload the class workbook from this app.")
                out.write(chunk)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise


def _workbook_stages(teacher: Teacher, path) -> List[str]:
    from backend.hpc.xl import unpacked_size_ok
    if not unpacked_size_ok(path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This file could not be opened as an Excel workbook. "
                            "It may be damaged - download the class workbook from this app again.")
    try:
        stages = workbook.detect_stages(path)
    except Exception:                                  # not an Excel file at all, or a damaged one (M-6)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This file could not be opened as an Excel workbook. "
                            "It may be damaged - download the class workbook from this app again.")
    if not stages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This is not a workbook from this app. "
                            "Use 'Sync Roster' and then 'Download Excel' to get one.")
    not_allowed = [s for s in stages if s not in teacher_stages(teacher)]
    if not_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"You are not assigned to: {', '.join(not_allowed)}.")
    return stages


@router.post("/upload/validate", response_model=ValidationReportResponse)
def validate_upload(file: UploadFile = File(...), teacher: Teacher = Depends(require_teacher)):
    """Saves the uploaded workbook and checks every student against the portal (nothing is written)."""
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only .xlsx files are supported.")
    path = _upload_path(teacher, file.filename)
    _save_upload(file, path)
    _workbook_stages(teacher, path)
    try:
        report = upload_jobs.check_workbook(_portal(teacher), path, teacher.id)
    except PortalError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    held: Dict[str, List[str]] = {}
    for e in report["errors"]:
        if e.get("student_id") and e["student_id"] not in report["ready_students"]:
            held.setdefault(e["student_id"], []).append(f"{e.get('column') or e.get('sheet')}: {e['message']}")
    shown = {k: v for k, v in report.items() if k != "ready_students"}
    shown.update(file_name=file.filename, checked_at=datetime.utcnow().isoformat(timespec="seconds") + "Z")
    _checked_path(teacher, file.filename).write_text(json.dumps({   # Sync sends exactly these students
        "file_hash": hashlib.sha256(path.read_bytes()).hexdigest(), "ready": report["ready_students"],
        "held": {sid: "; ".join(m)[:4000] for sid, m in held.items()}, "report": shown,
        "blocked": bool(report["ready_students"]) and not report["is_valid"]}), encoding="utf-8")   # Settings sheet
    return ValidationReportResponse(**shown)


@router.get("/upload/checked")
def last_checked(teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    """The last checked file's report, so a page reload shows it (and its Sync button) without checking again.
    Nothing once the file was replaced. A sync since then is fine: Sync leaves out whoever it saved."""
    found = sorted(hpc_sessions.session_dir(KIND, teacher.id).glob("checked_*.json"), key=lambda p: p.stat().st_mtime)
    if not found:
        return {"report": None}
    data = json.loads(found[-1].read_text(encoding="utf-8"))
    report = data.get("report")
    if not report:
        return {"report": None}
    path = _upload_path(teacher, report["file_name"])
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != data.get("file_hash"):
        return {"report": None}
    return {"report": report}


def _checked_path(teacher: Teacher, file_name: str) -> Path:
    return inside(hpc_sessions.session_dir(KIND, teacher.id), f"checked_{Path(file_name).name}.json")


@router.post("/upload/submit", response_model=UploadJobResponse)
def submit_upload(file_name: str, background_tasks: BackgroundTasks, teacher: Teacher = Depends(require_teacher),
                  db: Session = Depends(get_db), workers: int = Query(1, ge=1, le=5)):
    """Starts syncing a validated workbook. `workers` is accepted for older web app versions and ignored."""
    path = _upload_path(teacher, file_name)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uploaded file not found. Upload and validate it first.")
    checked = _checked_path(teacher, file_name)
    if not checked.exists():                              # a file from before checks were kept: as it is
        return _start_job(teacher, db, background_tasks, file_name, path)
    found = json.loads(checked.read_text(encoding="utf-8"))
    if found.get("file_hash") != hashlib.sha256(path.read_bytes()).hexdigest():
        raise HTTPException(status.HTTP_409_CONFLICT, "The file changed since it was checked. Upload it again.")
    if not found.get("ready"):
        raise HTTPException(status.HTTP_409_CONFLICT, "No student in this file is complete. Fix the cells listed and upload it again.")
    if found.get("blocked"):
        raise HTTPException(status.HTTP_409_CONFLICT, "The file's Settings sheet has a value to fix (see the check). Fix it and upload the file again.")
    # only the students the check found complete are sent, less any saved since (same answers); the others are
    # listed as not saved, with the reason. No new check: nothing is asked of PARAKH here.
    client = _portal(teacher)
    hooks = upload_jobs._with_file_settings(upload_jobs._grid_hooks(client, teacher.id),     # the file's settings, as
                                            upload_jobs.file_settings(client, teacher.id, path, choices=False))   # the check
    saved = upload_jobs.already_saved(client, teacher.id, workbook.read(path), hooks, path)
    ready = set(found["ready"]) - set(saved)
    if not ready:
        raise HTTPException(status.HTTP_409_CONFLICT, "Every complete student in this file is already saved with these answers.")
    return _start_job(teacher, db, background_tasks, file_name, path, only=ready, held=found.get("held") or {})


def _start_job(teacher: Teacher, db: Session, background_tasks: BackgroundTasks, file_name: str, path,
               only: Optional[set] = None, held: Optional[Dict[str, str]] = None) -> UploadJobResponse:
    """Creates the job and its per-student rows, then saves in the background. only: just these students.
    held: students the check kept back {id: why} - listed as not saved (nothing sent), never synced."""
    busy = HTTPException(status.HTTP_409_CONFLICT, "An upload is already running. Wait for it to finish.")
    stages = _workbook_stages(teacher, path)
    rows = workbook.read(path)
    held = {sid: why for sid, why in (held or {}).items() if sid in rows}
    if only is not None:
        rows = {sid: row for sid, row in rows.items() if sid in only or sid in held}
    client = _portal(teacher)
    label = ", ".join(s[:4] for s in stages) if len(stages) > 1 else stages[0]       # fits the 30-char column
    with _submit_lock:
        active = db.query(UploadJob).filter(UploadJob.teacher_id == teacher.id,
                                            UploadJob.status.in_(["PENDING", "IN_PROGRESS"])).first()
        if active:
            raise busy
        job = UploadJob(teacher_id=teacher.id, original_filename=file_name, detected_stage=label, status="PENDING",
                        file_hash=hashlib.sha256(path.read_bytes()).hexdigest(), total_students=len(rows),
                        active_teacher_id=teacher.id)
        db.add(job)
        try:
            db.flush()                         # the database's own guard, should another server process race us
        except IntegrityError:
            db.rollback()
            raise busy
        try:                                   # the file as synced (for its result files), before the job is kept
            shutil.copyfile(path, _job_copy(teacher, job.id))
        except OSError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"The file could not be kept for this upload ({exc}). Try again.")
        for row_number, (sid, row) in enumerate(rows.items(), start=3):
            db.add(StudentRecord(job_id=job.id, row_number=row_number, admission_number=sid,
                                 student_name=str(row.get(workbook.NAME_KEY) or sid), student_key=sid,
                                 grade=str(row.get("grade") or "")[:20], section=str(row.get("section") or "")[:10],
                                 status="INVALID" if sid in held else "PENDING" if row.get(workbook.SYNC_KEY) else "SKIPPED",
                                 error_message=f"Not sent - fix in the file: {held[sid]}"[:4000] if sid in held else None))
        if held:
            job.failed_count = len(held)
        db.commit()
    db.refresh(job)
    if only is None:
        background_tasks.add_task(upload_jobs.run_job, job.id, client, str(path), teacher.id)
    else:
        background_tasks.add_task(upload_jobs.run_job, job.id, client, str(path), teacher.id, set(only) - set(held))
    return _job_response(job)


@router.post("/upload/jobs/{job_id}/retry", response_model=UploadJobResponse)
def retry_failed(job_id: str, background_tasks: BackgroundTasks, teacher: Teacher = Depends(require_teacher),
                 db: Session = Depends(get_db)):
    """A new job from the same uploaded file, for the students whose save FAILED (M-11). Students with a mistake
    in the file (INVALID) need the file fixed and uploaded again; saved ones are left alone."""
    job = _own_job(db, teacher, job_id)
    if job.status in ("PENDING", "IN_PROGRESS"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload is still running. Wait for it to finish.")
    failed = {r.admission_number for r in job.records if r.status == "FAILED"}
    if not failed:
        raise HTTPException(status.HTTP_409_CONFLICT, "No student in this upload failed to save, so there is nothing to retry.")
    path = _upload_path(teacher, job.original_filename)
    if not path.exists() or (job.file_hash and hashlib.sha256(path.read_bytes()).hexdigest() != job.file_hash):
        raise HTTPException(status.HTTP_409_CONFLICT, "The uploaded file has changed (or was removed) since this upload. "
                            "Upload the file again instead.")
    from backend.services import audit
    audit.record(f"teacher:{teacher.id}", "retry_failed", "upload_job", job.id, None, {"students": sorted(failed)})
    return _start_job(teacher, db, background_tasks, job.original_filename, path, only=failed)


@router.get("/upload/jobs", response_model=List[UploadJobResponse])
def list_jobs(teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    jobs = (db.query(UploadJob).filter(UploadJob.teacher_id == teacher.id)
            .order_by(UploadJob.created_at.desc()).limit(20).all())
    return [_job_response(j) for j in jobs]


@router.get("/upload/jobs/{job_id}/records")
def job_records(job_id: str, teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    job = _own_job(db, teacher, job_id)
    records = sorted(job.records, key=lambda r: r.row_number or 0)
    return {**_job_response(job).model_dump(), "total_records": len(records), "records": [
        {"id": r.id, "row_number": r.row_number, "admission_number": r.admission_number, "student_name": r.student_name,
         "student_key": r.student_key, "grade": r.grade, "section": r.section, "status": r.status,
         "attempt_count": r.attempt_count or 0, "verification_result": r.verification_result,
         "error_message": r.error_message, "completed_at": r.completed_at.isoformat() if r.completed_at else None}
        for r in records]}


@router.get("/upload/jobs/{job_id}/live")
def job_live(job_id: str, teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    """While a job runs: who is being saved and which step, the recent steps, and every student's status."""
    job = _own_job(db, teacher, job_id)
    records = sorted(job.records, key=lambda r: r.row_number or 0)
    return {**_job_response(job).model_dump(), **upload_jobs.live_view(job.id),
            "students": [{"student_id": r.admission_number, "student_name": r.student_name, "status": r.status,
                          "error": r.error_message} for r in records]}


def _csv_text(value):
    """A cell Excel would run as a formula (=, +, -, @ first) is kept as text: CSV formula injection."""
    return "'" + value if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.get("/upload/jobs/{job_id}/export")
def export_job(job_id: str, teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    """CSV report: one line per student with the outcome."""
    job = _own_job(db, teacher, job_id)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Workbook", "Stage", "Row", "Student ID", "Student Name", "Status", "Result", "Errors", "Finished At"])
    for r in sorted(job.records, key=lambda r: r.row_number or 0):
        w.writerow([_csv_text(v) for v in (job.original_filename, job.detected_stage, r.row_number, r.admission_number,
                    r.student_name, r.status, r.verification_result or "", r.error_message or "",
                    r.completed_at.isoformat() if r.completed_at else "")])
    return StreamingResponse(io.BytesIO(out.getvalue().encode("utf-8-sig")), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="hpc_job_{job_id[:8]}_report.csv"'})


def _job_copy(teacher: Teacher, job_id: str) -> Path:
    return inside(hpc_sessions.session_dir(KIND, teacher.id), f"job_{job_id}.xlsx")


@router.get("/upload/jobs/{job_id}/workbook")
def job_workbook(job_id: str, which: str = Query("not_saved", pattern="^(saved|not_saved)$"),
                 teacher: Teacher = Depends(require_teacher), db: Session = Depends(get_db)):
    """The synced file again with only the saved students, or only the ones not saved (with the reasons): the
    not-saved file is fixed and uploaded as it is."""
    job = _own_job(db, teacher, job_id)
    if job.status in ("PENDING", "IN_PROGRESS"):
        raise HTTPException(status.HTTP_409_CONFLICT, "This upload is still running. Wait for it to finish.")
    src = _job_copy(teacher, job.id)
    if not src.exists():                                  # an upload from before copies were kept
        src = _upload_path(teacher, job.original_filename)
        if not src.exists() or (job.file_hash and hashlib.sha256(src.read_bytes()).hexdigest() != job.file_hash):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "The file of this upload is no longer kept.")
    data = upload_jobs.result_workbook(src, job.records, which == "saved")
    stem = re.sub(r"[^A-Za-z0-9 ._()-]", "_", Path(job.original_filename).stem)[:60]   # a header is plain ASCII
    name = f"{stem} - {'saved' if which == 'saved' else 'not saved - fix and upload'}.xlsx"
    return StreamingResponse(io.BytesIO(data), headers={"Content-Disposition": f'attachment; filename="{name}"'},
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def _own_job(db: Session, teacher: Teacher, job_id: str) -> UploadJob:
    job = db.query(UploadJob).filter(UploadJob.id == job_id, UploadJob.teacher_id == teacher.id).first()
    if not job:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


def _job_response(job: UploadJob) -> UploadJobResponse:
    return UploadJobResponse(
        job_id=job.id, status=job.status, total_students=job.total_students or 0,
        success_count=job.success_count or 0, failed_count=job.failed_count or 0, unverified_count=0,
        reconciliation_count=0, file_hash=job.file_hash, detected_stage=job.detected_stage,
        created_at=job.created_at or datetime.utcnow(), completed_at=job.completed_at)
