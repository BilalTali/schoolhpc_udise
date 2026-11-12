"""
Teacher accounts from PARAKH: the school no longer types its teachers in. PARAKH's own list of the school's teachers
(read with the school's PARAKH login) gives each teacher's name, PARAKH ID, teacher code and the classes PARAKH makes
them class teacher of. A teacher's login ID in this app IS their PARAKH ID (staff_id, e.g. T7AFCD2 - typed in any
case); the school only sets the password for this app. The teacher's own PARAKH password is never asked for here:
they type it when they connect to PARAKH to save cards.

list_teachers  PARAKH's teachers, each with its classes and this app's account (if any). Read only.
import_teachers  creates the missing accounts / updates the existing ones from PARAKH (name, code, classes); an
               existing account found by its PARAKH login gets the PARAKH ID as its login ID (the old one is reported).
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func

from backend.hpc.portal import Portal, PortalError, stage_code
from backend.models.entities import Teacher
from backend.services.auth_service import hash_password

STAGE_NAMES = {"FOUNDATIONAL": "Foundational", "PREPARATORY": "Preparatory", "MIDDLE": "Middle"}
ORDER = ["Foundational", "Preparatory", "Middle"]


def _lists(client: Portal) -> Tuple[Dict[int, Tuple[str, str]], Dict[int, str]]:
    """({grade id: (stage, grade name)}, {section id: section name}) from PARAKH."""
    grades = client._request("GET", f"/states/{client.state}/grades").get("data") or {}
    by_grade = {int(g["id"]): (STAGE_NAMES.get(code, code.title()), g["grade_caption"])
                for code, rows in grades.items() for g in rows or [] if str(g.get("id", "")).isdigit()}
    sections = client._request("GET", f"/states/{client.state}/districts/{client.district_id}/schools/"
                                      f"{client.school_id}/sections").get("data") or {}
    rows = sections.get("records") if isinstance(sections, dict) else sections
    return by_grade, {int(s["id"]): s["section_caption"] for s in rows or [] if str(s.get("id", "")).isdigit()}


def _classes(t: Dict[str, Any], grades, sections) -> List[Dict[str, Any]]:
    out = []
    for m in t.get("grade_section_mapping") or []:
        g, s = m.get("grd", m.get("grade_id")), m.get("sec", m.get("section_id"))
        if not str(g).isdigit() or not str(s).isdigit():
            continue
        stage, grade = grades.get(int(g), ("", f"Grade id {g}"))
        out.append({"stage": stage, "grade": grade, "grade_id": int(g), "section": sections.get(int(s), str(s)),
                    "section_id": int(s), "class_teacher": str(m.get("ct", 1)) != "0"})
    out.sort(key=lambda c: (not c["class_teacher"], c["grade_id"], c["section"]))
    return out


def parakh_id(t: Dict[str, Any]) -> str:
    """The teacher's PARAKH login ID (staff_id, e.g. T7AFCD2)."""
    return str(t.get("staff_id") or "").strip()


def _account(db, school_id: str, pid: str) -> Optional[Teacher]:
    low = pid.lower()
    for t in db.query(Teacher).filter(Teacher.school_id == school_id):
        if (t.hpc_login_id or "").strip().lower() == low or (t.username or "").lower() == low:
            return t
    return None


def read(client: Portal) -> List[Dict[str, Any]]:
    try:
        teachers = client.school_teachers()
        grades, sections = _lists(client)
    except PortalError as exc:
        raise ValueError(f"PARAKH did not give the school's teachers: {exc}")
    out = []
    for t in teachers:
        pid = parakh_id(t)
        if not pid:
            continue
        name = " ".join(f"{t.get('staff_fname') or ''} {t.get('staff_lname') or ''}".split()) or pid
        out.append({"parakh_id": pid, "name": name, "teacher_code": t.get("teacher_code") or "",
                    "registered": not t.get("reg_in_progress"), "classes": _classes(t, grades, sections)})
    out.sort(key=lambda x: x["name"].lower())
    return out


def list_teachers(db, school_id: str, client: Portal) -> List[Dict[str, Any]]:
    out = []
    for t in read(client):
        acc = _account(db, school_id, t["parakh_id"])
        out.append({**t, "account": None if acc is None else {
            "id": acc.id, "username": acc.username, "is_active": acc.is_active,
            "login_matches": (acc.username or "").lower() == t["parakh_id"].lower(),
            "has_parakh_login": bool(acc.hpc_login_id and acc.hpc_password_encrypted),
            "parakh_login_id": acc.hpc_login_id}})
    return out


def _assignment(classes: List[Dict[str, Any]]) -> Tuple[str, str, str]:
    """(stages, grades, sections) as this app's teacher record keeps them: the classes they are class teacher of."""
    own = [c for c in classes if c["class_teacher"] and c["stage"]]
    stages = [s for s in ORDER if any(c["stage"] == s for c in own)]
    grades = list(dict.fromkeys(c["grade"] for c in own))
    sections = list(dict.fromkeys(c["section"] for c in own))
    return ", ".join(stages), ", ".join(grades), ", ".join(sections)


def import_teachers(db, school_id: str, client: Portal, wanted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """wanted: [{"parakh_id", "password" (8+ characters; needed for a new account, optional otherwise)}]."""
    from backend.services.auth_service import end_all_sessions
    by_id = {t["parakh_id"].lower(): t for t in read(client)}
    results = []
    for w in wanted:
        pid = str(w.get("parakh_id") or "").strip()
        password = str(w.get("password") or "")
        t = by_id.get(pid.lower())
        if t is None:
            results.append({"parakh_id": pid, "status": "error", "message": "Not one of the school's teachers on PARAKH."})
            continue
        if password and len(password) < 8:
            results.append({"parakh_id": pid, "status": "error", "message": "The password needs at least 8 characters."})
            continue
        stages, grades, sections = _assignment(t["classes"])
        login = t["parakh_id"]                             # the PARAKH ID as PARAKH writes it (capitals stay)
        acc = _account(db, school_id, t["parakh_id"])
        taken = db.query(Teacher).filter(func.lower(Teacher.username) == login.lower(),
                                         *( [Teacher.id != acc.id] if acc else [])).first()
        if taken:
            results.append({"parakh_id": pid, "status": "error",
                            "message": f"The login ID {t['parakh_id']} is already used by another account."})
            continue
        if acc is None:
            if not password:
                results.append({"parakh_id": pid, "status": "error", "message": "Set a password for the new account."})
                continue
            acc = Teacher(school_id=school_id, teacher_name=t["name"], employee_code=t["teacher_code"] or None,
                          username=login, hashed_password=hash_password(password), hpc_login_id=t["parakh_id"],
                          assigned_stage=stages or "Preparatory", assigned_grade=grades, assigned_section=sections,
                          is_active=True)
            db.add(acc)
            results.append({"parakh_id": pid, "status": "created", "message": f"Login ID {t['parakh_id']}"})
        else:
            old = acc.username
            acc.teacher_name, acc.employee_code, acc.hpc_login_id = t["name"], t["teacher_code"] or acc.employee_code, t["parakh_id"]
            acc.username = login
            if stages:
                acc.assigned_stage, acc.assigned_grade, acc.assigned_section = stages, grades, sections
            note = [f"login ID is now {t['parakh_id']} (was {old})"] if old != login else []
            if password:
                acc.hashed_password = hash_password(password)
                end_all_sessions(db, acc)
                note.append("password set")
            results.append({"parakh_id": pid, "status": "updated", "message": "; ".join(note) or "Up to date with PARAKH"})
        db.flush()
    db.commit()
    return results
