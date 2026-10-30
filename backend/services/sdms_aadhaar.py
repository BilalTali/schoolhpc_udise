"""
AADHAAR verification and APAAR IDs, as SDMS's own pages do them (its AADHAAR MBU module and APAAR module):

  verify again      GET  api/v2/students/uuid-validate/{student}/1    after the parent's consent for demographic
                                                                     authentication (SDMS asks for it first)
  correct details   POST api/cy/students/{student}                   the General Information save, with the AADHAAR
                                                                     number and the name as in it (uuidUpdateYN 1,
                                                                     the number encrypted as SDMS's page does)
  APAAR status      POST api/apaar/students/{school}/{class}         (a read: SDMS's list, body {})
  generate APAAR    POST api/apaar/generate                          the parent's physical consent: relation, name,
                                                                     ID proof type and number, place, date
Who can get an APAAR ID (SDMS's rule): a PEN, and the AADHAAR verified. Statuses in the student record:
uuidStatus 1 verified, 0 not verified (UIDAI's error - verify again), 2 failed (details do not match the AADHAAR).
Nothing here runs without the person's go-ahead; consents are what the person says the parent gave.
"""
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.services import udise_sessions
from backend.services.sdms_data import load as load_students, _save as save_students
from backend.udise import client, sdms_write
from backend.udise.sdms import Sdms, SessionEnded, encrypt

JOBS: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
RELATIONS = {1: "Father", 2: "Mother", 3: "Legal Guardian"}
APAAR_FIELDS = ("apaarId", "apaarIdStatus", "apaarRemarksMessage", "isApaarGenAllowed", "apaarIdGenDate", "apaarIdReqDate",
                "mbuStatusDesc")
ID_TYPES = {1: "AADHAAR", 2: "PAN", 3: "EPIC/Voter ID", 4: "Driving License", 5: "Passport"}
NAME = re.compile(r"^[a-zA-Z.']+( [a-zA-Z.']+)*$")


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def group_of(g: Dict[str, Any]) -> str:
    """What a student needs: verified, retry (UIDAI's own error: just verify again), mismatch (correct the details
    to match the AADHAAR card, then verify), or no_aadhaar."""
    if g.get("isUuidAvailable") not in (1, "1"):
        return "no_aadhaar"
    status = str(g.get("uuidStatus"))
    if status == "1":
        return "verified"
    if status == "2":
        return "mismatch"
    return "retry"


def overview(school_id: str) -> Optional[Dict[str, Any]]:
    """Every student's AADHAAR and APAAR position, grouped, with SDMS's reason - from the last fetch."""
    data = load_students(school_id)
    if not data:
        return None
    rows = []
    for s in data["students"]:
        g, a = s["general"], s.get("apaar") or {}
        group = group_of(g)
        apaar_id = a.get("apaarId") or a.get("apaarIdDesc") or None
        allowed = a.get("isApaarGenAllowed") if "isApaarGenAllowed" in a else None
        rows.append({"student_id": g.get("studentId"), "name": g.get("studentName"), "class": g.get("classDesc"),
                     "section": g.get("sectionDesc"), "pen": g.get("studentCodeNat"), "gender": g.get("gender"),
                     "dob": g.get("dob"), "name_as_aadhaar": g.get("nameAsUuid"), "aadhaar": g.get("uuid"),
                     "group": group, "status": g.get("uuidStatusDesc"), "reason": g.get("uuidValidateRemarks"),
                     "checked_on": g.get("uuidValidateDate"), "mbu": a.get("mbuStatusDesc"),
                     "apaar_id": apaar_id if apaar_id not in ("NA", "") else None,
                     "apaar_status": a.get("apaarRemarksMessage") or a.get("apaarIdStatusValue"), "apaar_date": a.get("apaarIdGenDate"),
                     # SDMS's own flag when read; else its rule (a PEN and a verified AADHAAR, no APAAR ID yet)
                     # SDMS's rule: a PEN and a verified AADHAAR, no APAAR ID yet - and its own flag, once read
                     "apaar_ready": not (apaar_id and apaar_id != "NA") and group == "verified" and bool(g.get("studentCodeNat"))
                                    and (allowed is None or allowed in (1, "1", True)),
                     "apaar_blocked": None if (apaar_id and apaar_id != "NA") or group == "verified"
                                      else "verify the AADHAAR first"})
    rows.sort(key=lambda r: (str(r["class"] or ""), str(r["section"] or ""), str(r["name"] or "")))
    counts = {k: sum(1 for r in rows if r["group"] == k) for k in ("verified", "retry", "mismatch", "no_aadhaar")}
    counts["apaar_ready"] = sum(1 for r in rows if r["apaar_ready"])
    counts["apaar_done"] = sum(1 for r in rows if r["apaar_id"])
    counts["apaar_waiting"] = sum(1 for r in rows if not r["apaar_id"] and r["apaar_blocked"])     # AADHAAR to fix first
    return {"fetched_at": data["fetched_at"], "counts": counts, "students": rows, "apaar_read": any("apaar" in s for s in data["students"])}


def progress(school_id: str) -> Dict[str, Any]:
    with _lock:
        return {"job": dict(JOBS.get(school_id) or {}) or None}


def _session(school_id: str) -> Dict[str, Any]:
    session = udise_sessions._load(school_id)
    if not (session.get("services", {}).get("sdms") or {}).get("connected"):
        raise client.UdiseError("SDMS is not connected. Press 'Connect UDISE+' first.")
    return session


def _keep(school_id: str, student_id: int, general: Optional[Dict[str, Any]] = None, apaar: Optional[Dict[str, Any]] = None) -> None:
    """The kept copy shows what SDMS answered."""
    data = load_students(school_id)
    if not data:
        return
    for s in data["students"]:
        if s["general"].get("studentId") == student_id:
            if general:
                s["general"].update({k: v for k, v in general.items() if v is not None})
            if apaar:
                s["apaar"] = {**(s.get("apaar") or {}), **apaar}
    save_students(school_id, data)


# ---------------------------------------------------------------------------
# Verify again (a background job: one UIDAI check per student)
# ---------------------------------------------------------------------------

def start_verify(school_id: str, student_ids: List[int]) -> Dict[str, Any]:
    if not student_ids:
        return {"started": False, "error": "Choose the students to verify."}
    try:
        session = _session(school_id)
    except client.UdiseError as exc:
        return {"started": False, "error": str(exc)}
    with _lock:
        if (JOBS.get(school_id) or {}).get("status") == "RUNNING":
            return {"started": False, "error": "A verification is already running."}
        JOBS[school_id] = {"kind": "verify", "status": "RUNNING", "done": 0, "total": len(student_ids), "results": [],
                           "started_at": _now(), "finished_at": None, "error": None}
    threading.Thread(target=_verify_run, args=(school_id, session, list(student_ids)), daemon=True).start()
    return {"started": True, "students": len(student_ids)}


def verify_one(sdms: Sdms, student_id: int) -> Dict[str, Any]:
    """One UIDAI check, as SDMS's 'AADHAAR Validate' sends it. SDMS's answer: the new status and its reason."""
    answer = sdms.get_answer(f"api/v2/students/uuid-validate/{student_id}/1")
    data = answer.get("data") or ((answer.get("error") or {}).get("data") if isinstance(answer.get("error"), dict) else None) or {}
    message = (answer.get("error") or {}).get("message") if isinstance(answer.get("error"), dict) else answer.get("message")
    return {"verified": answer.get("status") is True and str(data.get("uuidStatus")) == "1",
            "status": data.get("uuidStatusDesc") or message, "reason": data.get("uuidValidateRemarks") or message,
            "general": {k: data.get(k) for k in ("uuidStatus", "uuidStatusDesc", "uuidValidateRemarks", "uuidValidateDate")}}


def _verify_run(school_id: str, session: Dict[str, Any], student_ids: List[int]) -> None:
    from backend.services import audit
    sdms = Sdms(session)
    try:
        for sid in student_ids:
            result = {"student_id": sid, "verified": False, "status": None, "reason": None, "error": None}
            try:
                found = verify_one(sdms, sid)
                result.update({k: found[k] for k in ("verified", "status", "reason")})
                _keep(school_id, sid, general=found["general"])
            except SessionEnded:
                raise
            except client.UdiseError as exc:
                result["error"] = str(exc)
            audit.record(f"school_admin:{school_id}", "sdms_aadhaar_verify", "student", str(sid), None,
                         {"verified": result["verified"], "consent": "given (confirmed by the school)"})
            with _lock:
                JOBS[school_id]["results"].append(result)
                JOBS[school_id]["done"] += 1
        with _lock:
            JOBS[school_id].update(status="COMPLETED", finished_at=_now())
    except SessionEnded as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=str(exc), finished_at=_now())
    except Exception as exc:
        with _lock:
            JOBS[school_id].update(status="FAILED", error=f"Unexpected error: {exc}", finished_at=_now())


# ---------------------------------------------------------------------------
# Correct the details to match the AADHAAR card, then verify (one student, right away)
# ---------------------------------------------------------------------------

def correct(school_id: str, student_id: int, aadhaar: str, name_as_aadhaar: str, gender: Optional[int],
            dob: Optional[str]) -> Dict[str, Any]:
    """The General Information save with the AADHAAR number and the name exactly as on the card (and gender / date of
    birth when they differ), then one UIDAI check. Returns SDMS's answers."""
    aadhaar = (aadhaar or "").replace(" ", "")
    problems = []
    if not (aadhaar.isdigit() and len(aadhaar) == 12 and aadhaar[0] not in "01"):
        problems.append("AADHAAR number: 12 digits as on the card (not starting with 0 or 1)")
    if not (NAME.match((name_as_aadhaar or "").strip()) and len(name_as_aadhaar.strip()) <= 100):
        problems.append("Name as on the AADHAAR card: letters, spaces, . and ' only")
    if gender not in (None, 1, 2, 3):
        problems.append("Gender: Male, Female or Transgender")
    if dob and not re.match(r"^\d{2}/\d{2}/\d{4}$", dob):
        problems.append("Date of birth: DD/MM/YYYY")
    if problems:
        return {"ok": False, "error": "; ".join(problems)}
    try:
        sdms = Sdms(_session(school_id))
        now = sdms.student(student_id)
        if not now:
            return {"ok": False, "error": "SDMS did not find this student."}
        body = sdms_write.general_body({**now, **({"gender": gender} if gender else {}), **({"dob": dob} if dob else {})})
        body.update(uuidUpdateYN=1, uuid=encrypt(aadhaar, sdms.key()), nameAsUuid=name_as_aadhaar.strip())
        sdms.post(f"api/cy/students/{student_id}", body)
        found = verify_one(sdms, student_id)
        fresh = sdms.student(student_id)
        _keep(school_id, student_id, general={**{k: fresh.get(k) for k in ("nameAsUuid", "uuid", "gender", "dob")}, **found["general"]})
    except client.UdiseError as exc:
        return {"ok": False, "error": str(exc)}
    from backend.services import audit
    audit.record(f"school_admin:{school_id}", "sdms_aadhaar_correct", "student", str(student_id), None,
                 {"fields": ["uuid", "nameAsUuid"] + (["gender"] if gender else []) + (["dob"] if dob else []),
                  "verified": found["verified"]})
    return {"ok": True, "verified": found["verified"], "status": found["status"], "reason": found["reason"]}


# ---------------------------------------------------------------------------
# APAAR: SDMS's list (read) and generation (one student, with the parent's consent)
# ---------------------------------------------------------------------------

def read_apaar(school_id: str) -> Dict[str, Any]:
    """SDMS's APAAR list for every class (POST with an empty body - a read), kept with each student."""
    data = load_students(school_id)
    if not data:
        return {"ok": False, "error": "Fetch the students first."}
    try:
        sdms = Sdms(_session(school_id))
        school = sdms.school_id()
        found = {}
        for c in data["classes"]:
            answer = sdms.post_answer(f"api/apaar/students/{school}/{c.get('classId')}", {})
            for row in (answer.get("data") or []) if isinstance(answer.get("data"), list) else []:
                if row.get("studentId") is not None:
                    # SDMS's APAAR list: apaarId, apaarIdStatus, apaarRemarksMessage, isApaarGenAllowed, apaarIdGenDate
                    found[row["studentId"]] = {k: row.get(k) for k in APAAR_FIELDS}
    except client.UdiseError as exc:
        return {"ok": False, "error": str(exc)}
    for s in data["students"]:
        if s["general"].get("studentId") in found:
            s["apaar"] = found[s["general"]["studentId"]]
    save_students(school_id, data)
    return {"ok": True, "students": len(found)}


def generate_apaar(school_id: str, student_id: int, consent: Dict[str, Any]) -> Dict[str, Any]:
    """APAAR ID for one student, as SDMS's APAAR preview sends it: the AADHAAR as SDMS holds it (not changed), and
    the parent's physical consent. Only for a student with a PEN and a verified AADHAAR."""
    data = load_students(school_id) or {"students": []}
    s = next((x for x in data["students"] if x["general"].get("studentId") == student_id), None)
    if s is None:
        return {"ok": False, "error": "Not one of this school's students (fetch again)."}
    g = s["general"]
    if group_of(g) != "verified" or not g.get("studentCodeNat"):
        return {"ok": False, "error": "SDMS generates an APAAR ID only with a PEN and a verified AADHAAR."}
    problems = []
    relation, id_type = consent.get("relation"), consent.get("id_type")
    if relation not in RELATIONS:
        problems.append("who gave the consent: Father, Mother or Legal Guardian")
    if not NAME.match(str(consent.get("name") or "").strip()):
        problems.append("the consenter's name: letters only")
    if id_type not in ID_TYPES:
        problems.append("ID proof type")
    if not str(consent.get("id_no") or "").strip():
        problems.append("ID proof number")
    if not str(consent.get("place") or "").strip():
        problems.append("place of the physical consent")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(consent.get("date") or "")):
        problems.append("date of the physical consent")
    if problems:
        return {"ok": False, "error": "Fill in: " + "; ".join(problems)}
    y, m, d = consent["date"].split("-")
    try:
        sdms = Sdms(_session(school_id))
        body = {"studentId": int(student_id), "uuid": encrypt(str(g.get("uuid") or ""), sdms.key()), "uuidUpdateYN": 0,
                "nameAsUuid": g.get("nameAsUuid"), "consenterRelation": int(relation), "consenterName": consent["name"].strip(),
                "idType": int(id_type), "idNo": str(consent["id_no"]).strip(), "place": consent["place"].strip(),
                "date": f"{d}/{m}/{y}"}
        answer = sdms.post_answer("api/apaar/generate", body)
    except client.UdiseError as exc:
        return {"ok": False, "error": str(exc)}
    from backend.services import audit
    apaar_id = (answer.get("data") or {}).get("apaarId") if isinstance(answer.get("data"), dict) else None
    audit.record(f"school_admin:{school_id}", "sdms_apaar_generate", "student", str(student_id), None,
                 {"ok": bool(apaar_id), "relation": RELATIONS[relation], "id_type": ID_TYPES[id_type]})
    if not apaar_id:
        error = answer.get("error") if isinstance(answer.get("error"), dict) else {}
        return {"ok": False, "error": f"SDMS did not generate it: {error.get('message') or answer.get('message') or 'no APAAR ID in the answer'}"}
    _keep(school_id, student_id, apaar={"apaarId": apaar_id, "apaarIdStatus": 1, "isApaarGenAllowed": 2,
                                        "apaarRemarksMessage": answer.get("message") or "Generated"})
    return {"ok": True, "apaar_id": apaar_id, "message": answer.get("message")}
