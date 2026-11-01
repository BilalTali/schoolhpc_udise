"""
UDISE+ (SDMS) against PARAKH (HPC): which students are on one and not the other, from what the app already holds -
SDMS's students as last fetched, and the classes the school's teachers fetched from PARAKH (with the parent's name
from the kept cards' Part A1). Nothing is read from either site here.

A pair is the same student when, in this order: the APAAR ID is the same; or the admission number; or the name and
date of birth; or the name and the parent's name. Names are compared in letters only, without case or spaces.
Only SDMS's classes up to the highest PARAKH covers are compared (PARAKH has no Classes IX-XII).
"""
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from backend.hpc.fields import get_path
from backend.services import hpc_sessions
from backend.services.card_store import CARDS_DIR
from backend.services.sdms_data import FORM_STATUS, load as load_students

PARAKH_GRADES = {"Balvatika 1": -3, "Balvatika 2": -2, "Balvatika 3": -1, **{f"Grade {n}": n for n in range(1, 9)}}
GUARDIAN_PATH = ("gen", 24)                 # Part A1 "Mother/Father/Guardian Name" (backend/hpc/stages/shared.py)


def _letters(text: Any) -> str:
    return re.sub(r"[^A-Z]", "", str(text or "").upper())


def _adm(text: Any) -> str:
    t = re.sub(r"[^A-Z0-9]", "", str(text or "").upper()).lstrip("0")
    return t


def _dob(text: Any) -> str:
    """DD/MM/YYYY from SDMS's DD/MM/YYYY or PARAKH's YYYY-MM-DD."""
    t = str(text or "").strip()[:10]
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else t


def _guardians(teacher_ids: Iterable[str]) -> Dict[str, str]:
    """PARAKH student id -> the parent's name from the kept cards' Part A1."""
    out: Dict[str, str] = {}
    for tid in teacher_ids:
        for path in (CARDS_DIR / f"teacher_{tid}").glob("*/*/*.json"):
            try:
                part = json.loads(path.read_text(encoding="utf-8"))["parts"].get("part_a1")
                name = get_path(json.loads(part) if isinstance(part, str) else part, GUARDIAN_PATH)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError):
                continue
            if name:
                out[path.stem] = str(name).strip()
    return out


def parakh_students(teacher_ids: Iterable[str]) -> List[Dict[str, Any]]:
    teacher_ids = list(teacher_ids)
    guardians = _guardians(teacher_ids)
    seen: Dict[str, Dict[str, Any]] = {}
    for tid in teacher_ids:
        for path in hpc_sessions.session_dir("teacher", tid).glob("roster_*.json"):
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            for s in (body.get("students") if isinstance(body, dict) else body) or []:
                if isinstance(s, dict) and s.get("student_id") and str(s["student_id"]) not in seen:
                    seen[str(s["student_id"])] = {
                        "name": s.get("student_name"), "parent": guardians.get(str(s["student_id"]), ""),
                        "adm_no": s.get("admission_number") or "", "class": f"{s.get('grade') or ''} {s.get('section') or ''}".strip(),
                        "class_id": PARAKH_GRADES.get(s.get("grade")), "dob": _dob(s.get("dob")), "gender": s.get("gender") or "",
                        "apaar": s.get("apaar_id") or "", "status": "HPC " + str(s.get("status") or "PENDING").replace("_", " ").lower()}
    return list(seen.values())


GENDER = {"MALE": "Male", "FEMALE": "Female", "TRANSGENDER": "Transgender", "OTHER": "Transgender"}


def register_students(school_id: str) -> List[Dict[str, Any]]:
    """The School Register's students (every student PARAKH lists for the school, fetched with the school's login),
    with the father's name the school entered and where each card stands. [] before the school fetched it."""
    from backend.services import register_data, school_register
    reg = school_register.students(school_id)["students"]
    try:
        session = register_data.session_of(school_id)
        entered = register_data.entered(school_id, session)
    except register_data.Problem:
        entered = {}
    out = []
    for r in reg:
        if r["missing_on_parakh"]:
            continue
        father = (entered.get(r["id"]) or {}).get("father") or ""
        out.append({"name": r["student_name"], "parent": father, "father": father, "adm_no": r["admission_number"] or "",
                    "class": f"{r['grade'] or ''} {r['section'] or ''}".strip(), "class_id": PARAKH_GRADES.get(r["grade"]),
                    "section": str(r["section"] or "").strip(), "dob": _dob(r["dob"]),
                    "gender": GENDER.get(str(r["gender"] or "").upper(), r["gender"] or ""), "apaar": r["apaar_id"] or "",
                    "status": "Card: " + ((r.get("card") or {}).get("status") or "—"), "teachers": r["teachers"],
                    "parakh_id": r["student_id"]})
    return out


def udise_students(school_id: str) -> Optional[List[Dict[str, Any]]]:
    data = load_students(school_id)
    if not data:
        return None
    out = []
    for s in data["students"]:
        g, e, a = s["general"], s.get("enrolment") or {}, s.get("apaar") or {}
        apaar = a.get("apaarId") if a.get("apaarId") not in (None, "", "NA") else ""
        out.append({"name": g.get("studentName"), "parent": g.get("fatherName") or g.get("motherName") or "",
                    "father": g.get("fatherName") or "", "section": str(g.get("sectionDesc") or "").strip(),
                    "adm_no": e.get("admnNumber") or "", "class": f"{g.get('classDesc') or ''} {g.get('sectionDesc') or ''}".strip(),
                    "class_id": g.get("classId"), "dob": _dob(g.get("dob")), "gender": {1: "Male", 2: "Female", 3: "Transgender"}.get(g.get("gender"), ""),
                    "apaar": apaar, "pen": g.get("studentCodeNat") or "",
                    "status": "Form " + FORM_STATUS.get(g.get("formStatus"), "In progress").lower()})
    return out


KEYS = [("APAAR ID", lambda s: s["apaar"]),
        ("admission number", lambda s: _adm(s["adm_no"])),
        ("name and date of birth", lambda s: _letters(s["name"]) + "|" + s["dob"] if s["name"] and s["dob"] else ""),
        ("name and parent", lambda s: _letters(s["name"]) + "|" + _letters(s["parent"]) if s["name"] and s["parent"] else "")]


def compare(school_id: str, teacher_ids: Iterable[str]) -> Dict[str, Any]:
    """UDISE+ against PARAKH: the School Register when the school has fetched it (the whole school), else the classes
    the teachers fetched (as before)."""
    udise = udise_students(school_id)
    parakh = register_students(school_id)
    source = "School Register" if parakh else "teachers' classes"
    parakh = parakh or parakh_students(teacher_ids)
    if udise is None:
        return {"ok": False, "error": "Fetch the students from SDMS first (Students (SDMS) page)."}
    if not parakh:
        return {"ok": False, "error": "No class fetched from PARAKH yet: the teachers open their class on PARAKH first."}
    top = max((p["class_id"] for p in parakh if p["class_id"] is not None), default=8)
    left_out = sum(1 for u in udise if u["class_id"] is not None and u["class_id"] > top)
    udise = [u for u in udise if u["class_id"] is None or u["class_id"] <= top]
    free_u, free_p = set(range(len(udise))), set(range(len(parakh)))
    matched = []
    for label, key in KEYS:                    # strongest key first; a student pairs once
        index: Dict[str, List[int]] = {}
        for i in free_u:
            k = key(udise[i])
            if k:
                index.setdefault(k, []).append(i)
        for j in sorted(free_p):
            k = key(parakh[j])
            hits = [i for i in index.get(k, []) if i in free_u] if k else []
            if len(hits) == 1:                 # an ambiguous key (two students share it) pairs nobody
                i = hits[0]
                free_u.discard(i)
                free_p.discard(j)
                u, p = udise[i], parakh[j]
                differs = [f for f, a, b in (("name", _letters(u["name"]), _letters(p["name"])), ("date of birth", u["dob"], p["dob"]),
                                             ("admission no", _adm(u["adm_no"]), _adm(p["adm_no"])), ("gender", u["gender"], p["gender"]),
                                             ("APAAR ID", u["apaar"], p["apaar"]),
                                             ("father's name", _letters(u.get("father")), _letters(p.get("father"))),
                                             ("class", u["class_id"], p["class_id"]),
                                             ("section", str(u.get("section") or "").upper(), str(p.get("section") or "").upper()))
                           if a not in (None, "") and b not in (None, "") and a != b]
                matched.append({"by": label, "udise": u, "parakh": p, "differs": differs})
    order = lambda s: (s["class_id"] if s["class_id"] is not None else 99, s["class"], str(s["name"] or ""))
    only_udise = sorted((udise[i] for i in free_u), key=order)
    only_parakh = sorted((parakh[j] for j in free_p), key=order)
    matched.sort(key=lambda m: order(m["udise"]))
    apaar = {"missing_both": sum(1 for m in matched if not m["udise"]["apaar"] and not m["parakh"]["apaar"]),
             "only_udise": sum(1 for m in matched if m["udise"]["apaar"] and not m["parakh"]["apaar"]),
             "only_parakh": sum(1 for m in matched if m["parakh"]["apaar"] and not m["udise"]["apaar"]),
             "differ": sum(1 for m in matched if "APAAR ID" in m["differs"]),
             "unmatched_without": sum(1 for x in only_udise + only_parakh if not x["apaar"])}
    return {"ok": True, "source": source,
            "counts": {"udise": len(udise), "parakh": len(parakh), "matched": len(matched),
                       "only_udise": len(only_udise), "only_parakh": len(only_parakh),
                       "differ": sum(1 for m in matched if m["differs"]), "udise_higher_classes": left_out},
            "apaar": apaar, "only_udise": only_udise, "only_parakh": only_parakh, "matched": matched}
