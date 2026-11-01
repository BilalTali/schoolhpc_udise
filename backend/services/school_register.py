"""
School Register (docs/school_register_plan.md), phase 1: the school's fetch from PARAKH and who teaches whom.

fetch       (school login, background) for each stage: PARAKH's school list (every student, assigned or not), then
            each student's record once (gender, date of birth, admission number), upserted by (school, stage,
            PARAKH id) - a second fetch changes rows, never adds copies; a student PARAKH stops listing is marked
            missing_since, never deleted. Then PARAKH's teachers and the grades/sections each is mapped to.
            If PARAKH refuses the school list, the older path (the school login's own list) is used and noted.
students    the register with each student's teacher(s); school only.
for_teacher the students of the classes PARAKH maps to that teacher (from the school's fetch; else the mapping the
            teacher's own PARAKH sign-in carried; else the grade/section set on the teacher in this app).
Nothing here writes to PARAKH.
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from backend.database import SessionLocal
from backend.hpc.portal import Portal, PortalError, stage_code
from backend.hpc.stages.common import Lookups
from backend.models.entities import Teacher
from backend.models.register import RegisterStudent, RegisterTeacherClass

STAGES = ["Foundational", "Preparatory", "Middle"]
JOBS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _name(row: Dict[str, Any]) -> str:
    return str(row.get("full_name") or f"{row.get('std_fname') or ''} {row.get('std_lname') or ''}").strip() \
        or str((row.get("stu_info") or {}).get("student_name") or "").strip()


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Fetch (school login, background)
# ---------------------------------------------------------------------------

def progress(school_id: str) -> Dict[str, Any]:
    with _lock:
        job = dict(JOBS.get(school_id) or {})
    return {"job": job or None}


def start(school_id: str, client: Portal, stages: Optional[List[str]] = None) -> Dict[str, Any]:
    stages = [s for s in (stages or STAGES) if s in STAGES]
    with _lock:
        if (JOBS.get(school_id) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "A fetch is already running."}
        JOBS[school_id] = {"status": "RUNNING", "step": "Starting", "done": 0, "total": 0, "stages": {},
                           "notes": [], "error": None, "started_at": _now(), "finished_at": None}
    threading.Thread(target=_run, args=(school_id, client, stages), daemon=True, name=f"register-{school_id[:8]}").start()
    return {"started": True}


def _set(school_id: str, **kw) -> None:
    with _lock:
        JOBS[school_id].update(kw)


def _run(school_id: str, client: Portal, stages: List[str]) -> None:
    from backend.services import audit
    try:
        counts = {}
        for stage in stages:
            _set(school_id, step=f"{stage}: reading PARAKH's list")
            rows, note = school_list(client, stage)
            if note:
                with _lock:
                    JOBS[school_id]["notes"].append(note)
            lookups = Lookups(client, stage_code(stage))
            with _lock:
                JOBS[school_id]["total"] += len(rows)
            _set(school_id, step=f"{stage}: reading {len(rows)} students' details")

            def record(row):
                try:
                    return client.student(stage, str(row.get("id")))
                except PortalError:
                    return {}
                finally:
                    with _lock:
                        JOBS[school_id]["done"] += 1
            with ThreadPoolExecutor(max_workers=4) as pool:
                records = list(pool.map(record, rows))
            counts[stage] = upsert(school_id, stage, rows, records, lookups)
            with _lock:
                JOBS[school_id]["stages"][stage] = counts[stage]
        _set(school_id, step="Reading PARAKH's teachers and their classes")
        teachers = fetch_teacher_classes(school_id, client)
        _set(school_id, status="COMPLETED", step="Done", finished_at=_now(), teachers=teachers)
        audit.record(f"school_admin:{school_id}", "register_fetch", "register", school_id, None,
                     {"stages": counts, "teachers": teachers})
    except Exception as exc:                          # the session ended, PARAKH down ...
        _set(school_id, status="FAILED", error=str(exc), finished_at=_now())


def school_list(client: Portal, stage: str) -> Tuple[List[Dict[str, Any]], str]:
    """(PARAKH's rows for every student of the school in the stage, a note when the older path had to be used)."""
    try:
        rows = client.school_roster(stage)
        if rows:
            return rows, ""
        fallback, why = client.roster(stage), "PARAKH's school list was empty"
    except PortalError as exc:
        fallback, why = client.roster(stage), f"PARAKH refused the school list ({exc})"
    return fallback, (f"{stage}: {why}; the school login's own list was used ({len(fallback)} students)." if fallback
                      else "")


def upsert(school_id: str, stage: str, rows: List[Dict[str, Any]], records: List[Dict[str, Any]], lookups) -> Dict[str, int]:
    """Adds or updates the stage's students; marks those PARAKH no longer lists. {"added", "updated", "missing"}."""
    now = datetime.utcnow()
    grades = {g["id"]: g["grade_caption"] for g in getattr(lookups, "grades", []) or []}
    seen: Set[str] = set()
    added = updated = 0
    with SessionLocal() as db:
        existing = {r.parakh_student_id: r for r in db.query(RegisterStudent).filter_by(school_id=school_id, stage=stage)}
        for row, record in zip(rows, records):
            sid = str(row.get("id") or record.get("hpc_id") or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            info = (record or {}).get("stu_info") or {}
            grade_id = _int(row.get("grade_id") if row.get("grade_id") is not None else info.get("grade_id"))
            section_id = _int(row.get("section_id") if row.get("section_id") is not None else info.get("section_id"))
            values = {
                "hpc_login_id": row.get("std_reg_id") or (record or {}).get("std_reg_id") or None,
                "student_name": _name(row) or str(info.get("student_name") or "").strip() or "(no name on PARAKH)",
                "apaar_id": row.get("std_apaar_id") or info.get("std_apaar_id") or None,
                "grade_id": grade_id, "grade": grades.get(grade_id) or row.get("grade") or None,
                "section_id": section_id, "section": lookups.section_name(section_id) if section_id is not None else None,
                "gender": info.get("gender") or None, "dob": info.get("dob") or None,
                "admission_number": info.get("school_admission_number") or None,
                "hpc_status": row.get("hpc_status") or (record or {}).get("hpc_status") or None,
                "source": {"list": row, "stu_info": info}, "last_seen_at": now, "missing_since": None,
            }
            r = existing.get(sid)
            if r is None:
                db.add(RegisterStudent(school_id=school_id, stage=stage, parakh_student_id=sid, first_seen_at=now, **values))
                added += 1
            else:
                for k, v in values.items():
                    setattr(r, k, v)
                updated += 1
        missing = 0
        for sid, r in existing.items():
            if sid not in seen and r.missing_since is None:
                r.missing_since = now
                missing += 1
        db.commit()
    return {"added": added, "updated": updated, "missing": missing, "listed": len(seen)}


def _pairs(mapping: Iterable[Dict[str, Any]]) -> Set[Tuple[int, int]]:
    """(grade id, section id) the teacher is CLASS teacher of: PARAKH's mapping marks it ct 1 (ct 0: a subject
    teacher of that class, which does not make the class theirs)."""
    out = set()
    for m in mapping or []:
        if str(m.get("ct", 1)) == "0":
            continue
        g = _int(m.get("grd", m.get("grade_id")))
        s = _int(m.get("sec", m.get("section_id")))
        if g is not None and s is not None:
            out.add((g, s))
    return out


def _hints(record: Dict[str, Any]) -> List[str]:
    return sorted({str(v).strip().lower() for k, v in record.items()
                   if isinstance(v, (str, int)) and str(v).strip() and k not in ("grade_section_mapping",)})


def fetch_teacher_classes(school_id: str, client: Portal) -> int:
    """PARAKH's teachers and their classes, matched to this app's teachers by their PARAKH login. Replaces the
    school's earlier fetch of them (a teacher's own sign-in mapping is kept apart). Returns how many teachers."""
    try:
        teachers = client.school_teachers()
    except PortalError:
        return 0
    with SessionLocal() as db:
        app = {(t.hpc_login_id or "").strip().lower(): t.id for t in db.query(Teacher).filter_by(school_id=school_id)
               if (t.hpc_login_id or "").strip()}
        db.query(RegisterTeacherClass).filter_by(school_id=school_id, source="parakh_school").delete()
        count = 0
        for t in teachers:
            tid = t.get("id") or t.get("staff_id")
            if tid is None:
                continue
            mapping = t.get("grade_section_mapping")
            if not mapping:
                try:
                    mapping = client.teacher_grade_sections(tid)
                except PortalError:
                    mapping = []
            hints = _hints(t)
            app_id = next((app[h] for h in hints if h in app), None)
            name = t.get("name") or t.get("staff_name") or t.get("teacher_name") or \
                f"{t.get('staff_fname') or ''} {t.get('staff_lname') or ''}".strip()
            for g, s in _pairs(mapping):
                db.add(RegisterTeacherClass(school_id=school_id, parakh_teacher_id=str(tid), teacher_name=name,
                                            login_hints=hints, app_teacher_id=app_id, grade_id=g, section_id=s,
                                            source="parakh_school"))
            count += 1
        db.commit()
    return count


def remember_teacher_mapping(teacher: Teacher, staff: Dict[str, Any]) -> None:
    """A teacher's own PARAKH sign-in carries the classes PARAKH maps them to: kept as a second source."""
    pairs = _pairs(staff.get("grade_section_mapping") or [])
    if not pairs:
        return
    with SessionLocal() as db:
        db.query(RegisterTeacherClass).filter_by(school_id=teacher.school_id, app_teacher_id=teacher.id,
                                                 source="teacher_session").delete()
        for g, s in pairs:
            db.add(RegisterTeacherClass(school_id=teacher.school_id, parakh_teacher_id=str(staff.get("staff_id") or ""),
                                        teacher_name=teacher.teacher_name, login_hints=[], app_teacher_id=teacher.id,
                                        grade_id=g, section_id=s, source="teacher_session"))
        db.commit()


# ---------------------------------------------------------------------------
# Reading the register
# ---------------------------------------------------------------------------

def _view(r: RegisterStudent, teachers: List[str]) -> Dict[str, Any]:
    return {"id": r.id, "stage": r.stage, "student_id": r.parakh_student_id, "student_name": r.student_name,
            "hpc_login_id": r.hpc_login_id, "apaar_id": r.apaar_id, "grade": r.grade, "grade_id": r.grade_id,
            "section": r.section, "section_id": r.section_id, "gender": r.gender, "dob": r.dob,
            "admission_number": r.admission_number, "hpc_status": r.hpc_status, "teachers": teachers,
            "missing_on_parakh": r.missing_since is not None,
            "last_seen_at": r.last_seen_at.isoformat(timespec="seconds") + "Z" if r.last_seen_at else None}


def _classes(db, school_id: str) -> Dict[Tuple[int, int], List[str]]:
    """(grade id, section id) -> teacher names (PARAKH's mapping; the app's name when the teacher is matched)."""
    names = {t.id: t.teacher_name for t in db.query(Teacher).filter_by(school_id=school_id)}
    out: Dict[Tuple[int, int], List[str]] = {}
    for c in db.query(RegisterTeacherClass).filter_by(school_id=school_id):
        name = names.get(c.app_teacher_id) or c.teacher_name or f"PARAKH teacher {c.parakh_teacher_id}"
        if name not in out.setdefault((c.grade_id, c.section_id), []):
            out[(c.grade_id, c.section_id)].append(name)
    return out


def students(school_id: str, stage: Optional[str] = None) -> Dict[str, Any]:
    """The whole register (school only), with each student's teachers and counts per stage."""
    with SessionLocal() as db:
        q = db.query(RegisterStudent).filter_by(school_id=school_id)
        if stage:
            q = q.filter_by(stage=stage)
        classes = _classes(db, school_id)
        rows = [_view(r, classes.get((r.grade_id, r.section_id), [])) for r in q]
    rows.sort(key=lambda r: (STAGES.index(r["stage"]) if r["stage"] in STAGES else 9, r["grade_id"] or 0,
                             str(r["section"] or ""), r["student_name"]))
    summary: Dict[str, Dict[str, int]] = {}
    for r in rows:
        s = summary.setdefault(r["stage"], {"students": 0, "assigned": 0, "unassigned": 0, "missing_on_parakh": 0})
        s["students"] += 1
        s["assigned" if r["teachers"] else "unassigned"] += 1
        s["missing_on_parakh"] += r["missing_on_parakh"]
    return {"students": rows, "summary": summary}


def teacher_classes(teacher: Teacher) -> Set[Tuple[int, int]]:
    """The (grade id, section id) pairs PARAKH maps the teacher to: the school's fetch first, else the teacher's own
    sign-in. Empty when neither is known yet."""
    with SessionLocal() as db:
        rows = db.query(RegisterTeacherClass).filter_by(school_id=teacher.school_id, app_teacher_id=teacher.id).all()
    school = {(c.grade_id, c.section_id) for c in rows if c.source == "parakh_school"}
    return school or {(c.grade_id, c.section_id) for c in rows if c.source == "teacher_session"}


def for_teacher(teacher: Teacher, stage: Optional[str] = None) -> List[Dict[str, Any]]:
    """Only the teacher's students (backend-enforced): the register's students of the teacher's PARAKH classes."""
    pairs = teacher_classes(teacher)
    if not pairs:
        return []
    with SessionLocal() as db:
        q = db.query(RegisterStudent).filter(RegisterStudent.school_id == teacher.school_id,
                                             RegisterStudent.missing_since.is_(None))
        if stage:
            q = q.filter(RegisterStudent.stage == stage)
        rows = [_view(r, [teacher.teacher_name]) for r in q if (r.grade_id, r.section_id) in pairs]
    rows.sort(key=lambda r: (r["grade_id"] or 0, str(r["section"] or ""), r["student_name"]))
    return rows


def may_open(teacher: Teacher, stage: str, student_id: str) -> bool:
    return any(r["student_id"] == str(student_id) for r in for_teacher(teacher, stage))
