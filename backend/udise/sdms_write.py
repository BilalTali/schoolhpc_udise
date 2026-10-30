"""
Updating a student's SDMS form, exactly as SDMS's own pages save it (read from its web app):

  General Information   POST api/cy/students/{student}          the form's values (see general_body)
  Enrolment Details     POST api/v2/students/enrolment/{student}  (see enrolment_body)
  Other Details         POST api/v2/AY/students/facility/{student} (see facility_body)

No captcha is asked for these saves. AADHAAR is never changed here: the body says "not updating the AADHAAR"
(uuidUpdateYN 2, uuid and the name as in it empty), as SDMS's page sends it when that box is not ticked.
Each body starts from what SDMS holds now (read just before) and only the teacher's changes are put in.
"""
from typing import Any, Dict, List, Optional, Tuple

from backend.udise import sdms_form

# ---------------------------------------------------------------------------
# From the sheet's words back to SDMS's codes
# ---------------------------------------------------------------------------

KEEP = object()        # the cell means "leave as it is" (empty, or "not needed")


def _invert(table: Dict[int, str]) -> Dict[str, int]:
    return {v.strip().lower(): k for k, v in table.items()}


CHOICES = {
    "gender": _invert(sdms_form.GENDER), "social": _invert(sdms_form.SOCIAL), "minority": _invert(sdms_form.MINORITY),
    "yes_no": _invert(sdms_form.YES_NO), "status_py": _invert(sdms_form.STATUS_PY),
    "exam_result": _invert(sdms_form.EXAM_RESULT), "distance": _invert(sdms_form.DISTANCE),
    "parent_education": _invert(sdms_form.PARENT_EDUCATION),
}

# the completion sheet's columns: label -> (tab, key in SDMS's record, how the words become the value)
# kinds: text, date, int, number, choice:<list>, list:<master>, class, codes (comma separated numbers),
#        facilities (names -> ids), skip (not changed from here)
COLUMNS: Dict[str, Tuple[str, str, str]] = {
    "Gender": ("general", "gender", "choice:gender"),
    "Date of Birth": ("general", "dob", "date"),
    "Mother's Name": ("general", "motherName", "text"),
    "Father's Name": ("general", "fatherName", "text"),
    "AADHAAR Number of Student": ("general", "uuid", "skip"),
    "Name of Student as per AADHAAR": ("general", "nameAsUuid", "skip"),
    "Address": ("general", "address", "text"),
    "Pincode": ("general", "pincode", "int"),
    "Mobile Number": ("general", "primaryMobile", "text"),
    "Mother Tongue": ("general", "motherTongue", "list:mother_tongue"),
    "Social Category": ("general", "socCatId", "choice:social"),
    "Minority Group": ("general", "minorityId", "choice:minority"),
    "BPL beneficiary?": ("general", "isBplYN", "choice:yes_no"),
    "AAY beneficiary?": ("general", "aayBplYN", "choice:yes_no"),
    "EWS / Disadvantaged Group?": ("general", "ewsYN", "choice:yes_no"),
    "CWSN?": ("general", "cwsnYN", "choice:yes_no"),
    "Type of impairment (if CWSN)": ("general", "impairmentType", "codes"),
    "Disability Percentage (if CWSN)": ("general", "impairmentPercent", "number"),
    "Indian National?": ("general", "natIndYN", "choice:yes_no"),
    "Out-of-School-Child?": ("general", "ooscYN", "choice:yes_no"),
    "Mainstreamed?": ("general", "ooscMainstreamedYN", "choice:yes_no"),
    "Admission Number in Present School": ("enrolment", "admnNumber", "text"),
    "Admission Date in Present School": ("enrolment", "admnStartDate", "date"),
    "Status in Previous Academic Year": ("enrolment", "enrStatusPY", "choice:status_py"),
    "Class Studied in Previous Year": ("enrolment", "classPY", "class"),
    "Previous Class - Result": ("enrolment", "examResultPy", "choice:exam_result"),
    "Previous Class - Marks (%)": ("enrolment", "examMarksPy", "number"),
    "Days Attended (previous year)": ("enrolment", "attendancePy", "int"),
    "Medium of Instruction": ("enrolment", "moiId", "list:moi"),
    "Subjects (SDMS codes)": ("enrolment", "mandatorySubjectGroup", "codes"),
    "Facilities provided?": ("facility", "facilityYn", "choice:yes_no"),
    "Which facilities": ("facility", "facProvided", "facilities"),
    "CWSN facilities provided? (if CWSN)": ("facility", "facProvidedCwsnYn", "choice:yes_no"),
    "Olympiads / Competitions?": ("facility", "olympdsNlc", "choice:yes_no"),
    "NCC": ("facility", "nccYn", "choice:yes_no"),
    "NSS": ("facility", "nssYn", "choice:yes_no"),
    "Scouts and Guides": ("facility", "scoutsYn", "choice:yes_no"),
    "Height (cm)": ("facility", "heightInCm", "int"),
    "Weight (kg)": ("facility", "weightInKg", "int"),
    "Distance to School": ("facility", "distanceFrmSchool", "choice:distance"),
    "Parents' Highest Education": ("facility", "parentEducation", "choice:parent_education"),
}


def to_value(kind: str, cell: Any, masters: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
    """(SDMS value, problem): the words of a sheet cell as SDMS stores them. KEEP for an empty or 'not needed' cell."""
    text = "" if cell is None else str(cell).strip()
    if not text or text.lower() in ("not needed", "—", "-"):
        return KEEP, None
    if kind == "skip":
        return KEEP, None
    if kind == "text":
        return text, None
    if kind == "date":
        if hasattr(cell, "strftime"):
            return cell.strftime("%d/%m/%Y"), None
        parts = text.replace("-", "/").replace(".", "/").split("/")
        if len(parts) == 3 and all(p.isdigit() for p in parts) and len(parts[2]) == 4:
            return f"{int(parts[0]):02d}/{int(parts[1]):02d}/{parts[2]}", None
        return KEEP, "a date as DD/MM/YYYY"
    if kind in ("int", "number"):
        try:
            number = float(text)
        except ValueError:
            return KEEP, "a number"
        return (int(number) if kind == "int" or number.is_integer() else number), None
    if kind.startswith("choice:"):
        table = CHOICES[kind.split(":", 1)[1]]
        found = table.get(text.lower())
        if found is None and text.split(" - ")[0].isdigit():     # "1 - Less than 1 km" or just "1"
            found = int(text.split(" - ")[0]) if int(text.split(" - ")[0]) in table.values() else None
        return (found, None) if found is not None else (KEEP, "one of: " + ", ".join(sorted({k.title() for k in table})))
    if kind.startswith("list:"):
        names = masters.get(kind.split(":", 1)[1]) or {}
        found = next((int(code) for code, words in names.items() if words.strip().lower() == text.lower()), None)
        return (found, None) if found is not None else (KEEP, "a choice from SDMS's list (use the drop-down)")
    if kind == "class":
        for code, words in {**{int(k): v for k, v in (masters.get("pre_primary") or {}).items()}, **sdms_form.CLASSES}.items():
            if words.strip().lower() == text.lower():
                return code, None
        return KEEP, "a class such as I, II ... or UKG/KG2/PP1"
    if kind == "codes":
        try:
            return [int(float(p)) for p in text.replace(";", ",").split(",") if p.strip()], None
        except ValueError:
            return KEEP, "numbers separated by commas"
    if kind == "facilities":
        names = {words.strip().lower(): int(code) for code, words in (masters.get("facilities") or {}).items()}
        wanted = [p.strip().lower() for p in text.split(",") if p.strip()]
        unknown = [w for w in wanted if w not in names]
        return ([names[w] for w in wanted], None) if not unknown else (KEEP, "facility names from SDMS's list")
    return KEEP, None


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return sorted(map(str, a or [])) == sorted(map(str, b or []))
    return str("" if a is None else a).strip().lower() == str("" if b is None else b).strip().lower()


def changes_from_row(student: Dict[str, Any], row: Dict[str, Any], masters: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """({tab: {key: new value}}, problems): what a sheet row changes for this student - only real changes."""
    changes: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    for label, (tab, key, kind) in COLUMNS.items():
        if label not in row:
            continue
        value, problem = to_value(kind, row[label], masters)
        if problem:
            problems.append(f"{label}: {problem}")
            continue
        if value is KEEP:
            continue
        if not _same((student.get(tab) or {}).get(key), value):
            changes.setdefault(tab, {})[key] = value
    return changes, problems


def merged(student: Dict[str, Any], changes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {tab: {**(student.get(tab) or {}), **changes.get(tab, {})} for tab in ("general", "enrolment", "facility")}


# ---------------------------------------------------------------------------
# The bodies SDMS's pages send
# ---------------------------------------------------------------------------

def _or(value: Any, default: Any) -> Any:
    return default if value in (None, "") else value


def general_body(g: Dict[str, Any]) -> Dict[str, Any]:
    """editStudentBasicDetailsForm's raw value, as its save sends it without changing the AADHAAR."""
    oosc = _or(g.get("ooscYN"), "")
    return {
        "classId": g.get("classId"), "sectionId": g.get("sectionId"), "studentId": g.get("studentId"),
        "schoolId": g.get("schoolId"), "uuidUpdateYN": 2, "uuid": "", "nameAsUuid": "",
        "gender": g.get("gender"), "dob": g.get("dob"), "motherName": g.get("motherName"),
        "fatherName": g.get("fatherName"), "guardianName": _or(g.get("guardianName"), ""),
        "address": g.get("address"), "pincode": g.get("pincode"), "primaryMobile": g.get("primaryMobile"),
        "secondaryMobile": _or(g.get("secondaryMobile"), ""), "email": _or(g.get("email"), ""),
        "motherTongue": g.get("motherTongue"), "socCatId": g.get("socCatId"), "minorityId": g.get("minorityId"),
        "isBplYN": g.get("isBplYN"), "aayBplYN": _or(g.get("aayBplYN"), 9), "ewsYN": g.get("ewsYN"),
        "cwsnYN": g.get("cwsnYN"), "natIndYN": g.get("natIndYN"),
        "impairmentType": g.get("impairmentType") if g.get("cwsnYN") in (1, "1") else None,
        "impairmentPercent": g.get("impairmentPercent") if g.get("cwsnYN") in (1, "1") else "",
        "disabilityCerti": _or(g.get("disabilityCerti"), ""),
        "ooscMainstreamedYN": 9 if oosc in ("", 2, "2") else _or(g.get("ooscMainstreamedYN"), 9),
        "ooscYN": oosc, "studentCodeState": _or(g.get("studentCodeState"), ""),
        "bloodGroup": _or(g.get("bloodGroup"), ""), "natOtherCountry": _or(g.get("natOtherCountry"), ""),
        "certifiedCheckCount": 0, "ageCheckSkipped": 2,
    }


def enrolment_body(e: Dict[str, Any], g: Dict[str, Any]) -> Dict[str, Any]:
    """The body SDMS's Enrolment page builds (an elementary class: subjects as lists of ids)."""
    result = _or(e.get("examResultPy"), 0)
    return {
        "academicStream": _or(e.get("academicStream"), 0), "admnNumber": e.get("admnNumber"),
        "admnStartDate": e.get("admnStartDate"), "rollNumber": _or(e.get("rollNumber"), ""),
        "attendancePy": _or(e.get("attendancePy"), 0), "classPY": _or(e.get("classPY"), 99),
        "enrStatusPY": _or(e.get("enrStatusPY"), 0),
        "examMarksPy": 0 if str(result) == "4" else _or(e.get("examMarksPy"), 999), "examResultPy": result,
        "schoolId": _or(e.get("schoolId"), g.get("schoolId")), "studentId": _or(e.get("studentId"), g.get("studentId")),
        "moiId": e.get("moiId"), "academicCourse": _or(e.get("academicCourse"), 0),
        "languageGroup": e.get("languageGroup"),
        "optionalSubject": sorted(e.get("optionalSubGroup") or []), "foreignSubject": e.get("foreignSubGroup") or [],
        "mandatorySubject": sorted(e.get("mandatorySubjectGroup") or []),
        "languageSubGroup": sorted(e.get("languageSubGroup") or []),
        "coCurricularSubject": sorted(e.get("curricularSubGroup") or []),
        "certifiedCheckCount": 0,
        "isRteAvailable": _or(e.get("isRteAvailable"), 9), "rteAmount": _or(e.get("rteAmount"), 0),
    }


def facility_body(f: Dict[str, Any], g: Dict[str, Any]) -> Dict[str, Any]:
    """The body SDMS's Other Details page builds."""
    return {
        "schoolId": int(_or(f.get("schoolId"), g.get("schoolId"))), "facilityYn": _or(f.get("facilityYn"), 9),
        "facProvided": f.get("facProvided") or [], "facProvidedCwsnYn": _or(f.get("facProvidedCwsnYn"), 9),
        "facProvidedCwsn": f.get("facProvidedCwsn") or [], "olympdsNlc": int(_or(f.get("olympdsNlc"), 9)),
        "nccYn": int(_or(f.get("nccYn"), 9)), "nssYn": int(_or(f.get("nssYn"), 9)), "scoutsYn": int(_or(f.get("scoutsYn"), 9)),
        "weightInKg": f.get("weightInKg"), "heightInCm": f.get("heightInCm"),
        "distanceFrmSchool": f.get("distanceFrmSchool"), "parentEducation": f.get("parentEducation"),
    }


SAVE = {"general": ("api/cy/students/{id}", general_body), "enrolment": ("api/v2/students/enrolment/{id}", enrolment_body),
        "facility": ("api/v2/AY/students/facility/{id}", facility_body)}
TAB_NAME = {"general": "General Information", "enrolment": "Enrolment Details", "facility": "Other Details"}
