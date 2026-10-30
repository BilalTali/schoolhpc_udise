"""
The SDMS student form (new session, current year) as the school sees it: the same tabs, the same questions and
order (labels from SDMS's own English text), and the answers in words, decoded the way SDMS's pages do (their
display pipes and lists). For Jammu & Kashmir the form has three tabs; Vocational (classes IX-XII) and
State-specific fields (other states only) are not shown for this school's students.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

# SDMS's display pipes (main.js), copied as they are
GENDER = {1: "Male", 2: "Female", 3: "Transgender"}
MINORITY = {1: "Muslim", 2: "Christian", 3: "Sikh", 4: "Buddhist", 5: "Parsi", 6: "Jain", 7: "NA"}
SOCIAL = {1: "General", 2: "SC", 3: "ST", 4: "OBC"}
ENTRY = {6: "Completed", 0: "Not Started"}                       # else In-Progress
AADHAAR = {1: "AADHAAR not available", 2: "Pending", 3: "Validation Failed", 4: "Verified"}
STATUS_PY = {1: "Studied at Current/Same School", 2: "Studied at Other School", 3: "Anganwadi/ ECCE Centre",
             4: "None/Not Studying", 5: "Studying in Unrecognized/Open School"}
EXAM_RESULT = {1: "Promoted/Passed", 2: "Promoted/Passed with grace", 3: "Not Promoted/Not Passed/Repeater",
               4: "Promoted/Passed without Examination", 5: "Discontinued before Examination", 6: "Repeater by Choice",
               7: "Compartment/Provisionally Passed"}
ENROLLED_UNDER = {0: "None", 1: "Section 12 of the RTE", 2: "EWS", 3: "Persons with Disabilities (PwD)",
                  4: "Disadvantaged Group", 5: "Others"}
DISTANCE = {1: "1 - Less than 1 km", 2: "2 - Between 1-3 Kms", 3: "3 - Between 3-5 Kms", 4: "4 - More than 5 Kms"}
PARENT_EDUCATION = {1: "1 - Primary", 2: "2 - Upper Primary", 3: "3 - Secondary or Equivalent",
                    4: "4 - Higher Secondary or Equivalent", 5: "5 - More than Higher Secondary",
                    6: "6 - No Schooling Experience"}
YES_NO = {1: "Yes", 2: "No", 9: "Not applicable"}
CLASSES = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII"}


def _code(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pick(table: Dict[int, str]) -> Callable[[Any, Dict[str, Any]], str]:
    def decode(value: Any, _m: Dict[str, Any]) -> str:
        code = _code(value)
        return "" if value in (None, "") else table.get(code, str(value)) if code is not None else str(value)
    return decode


def plain(value: Any, _m: Dict[str, Any]) -> Any:
    return "" if value is None else value


def from_list(name: str) -> Callable[[Any, Dict[str, Any]], str]:
    """A code from one of the school's SDMS lists (mother tongue, medium ...): {code: words}."""
    def decode(value: Any, masters: Dict[str, Any]) -> str:
        if value in (None, "", 0):
            return ""
        return (masters.get(name) or {}).get(str(value), str(value))
    return decode


def many(name: str) -> Callable[[Any, Dict[str, Any]], str]:
    """A list of codes (facilities given ...) as their names, comma separated."""
    def decode(value: Any, masters: Dict[str, Any]) -> str:
        if not value:
            return ""
        names = masters.get(name) or {}
        return ", ".join(names.get(str(v), str(v)) for v in value)
    return decode


def class_name(value: Any, masters: Dict[str, Any]) -> str:
    code = _code(value)
    if code is None:
        return ""
    if code < 0:
        return (masters.get("pre_primary") or {}).get(str(code), str(code))
    return CLASSES.get(code, str(code))


def entry(value: Any, _m: Dict[str, Any]) -> str:
    return "" if value is None else ENTRY.get(_code(value), "In-Progress")


Field = Tuple[str, str, str, Callable[[Any, Dict[str, Any]], Any]]   # (label, part, key, decode)

# label, the record it is in (general / enrolment / facility), its key, how it is shown
FORM: List[Tuple[str, List[Field]]] = [
    ("Student", [
        ("Class", "general", "classDesc", plain),
        ("Section", "general", "sectionDesc", plain),
        ("PEN (Student code)", "general", "studentCodeNat", plain),
        ("Form status", "general", "formStatus", entry),
    ]),
    ("1. General Information", [
        ("Student's Name (as per School record/School Admission Register)", "general", "studentName", plain),
        ("Gender (as per School record/School Admission Register)", "general", "gender", pick(GENDER)),
        ("Date of Birth (as per School record/School Admission Register)", "general", "dob", plain),
        ("Mother's Name", "general", "motherName", plain),
        ("Father's Name", "general", "fatherName", plain),
        ("Guardian's Name", "general", "guardianName", plain),
        ("AADHAAR Number of Student", "general", "uuid", plain),
        ("Name of Student as per/in AADHAAR Card", "general", "nameAsUuid", plain),
        ("AADHAAR validation status", "general", "uuidStatus", pick(AADHAAR)),
        ("Address", "general", "address", plain),
        ("Pincode", "general", "pincode", plain),
        ("Mobile Number (of Student/ Parent/ Guardian)", "general", "primaryMobile", plain),
        ("Alternate Mobile Number (of Student/ Parent/ Guardian)", "general", "secondaryMobile", plain),
        ("Contact email-id (of Student/Parent/Guardian)", "general", "email", plain),
        ("Mother Tongue of the Student", "general", "motherTongue", from_list("mother_tongue")),
        ("Social Category", "general", "socCatId", pick(SOCIAL)),
        ("Minority Group", "general", "minorityId", pick(MINORITY)),
        ("Whether BPL beneficiary?", "general", "isBplYN", pick(YES_NO)),
        ("Whether Antyodaya Anna Yojana (AAY) beneficiary?", "general", "aayBplYN", pick(YES_NO)),
        ("Whether belongs to EWS / Disadvantaged Group?", "general", "ewsYN", pick(YES_NO)),
        ("Whether CWSN?", "general", "cwsnYN", pick(YES_NO)),
        ("If Yes, Type of impairment (code)", "general", "impairmentType", plain),
        ("Disability Percentage (in %)", "general", "impairmentPercent", plain),
        ("Whether the Student is Indian National?", "general", "natIndYN", pick(YES_NO)),
        ("Is this Student identified as Out-of-School-Child in current or previous years?", "general", "ooscYN", pick(YES_NO)),
        ("When the student is mainstreamed?", "general", "ooscMainstreamedYN", pick(YES_NO)),
        ("Repeater", "general", "isRepeater", pick(YES_NO)),
    ]),
    ("2. Enrolment Details", [
        ("Admission Number in Present School", "enrolment", "admnNumber", plain),
        ("Admission Date (DD/MM/YYYY) in Present School", "enrolment", "admnStartDate", plain),
        ("Class/Section Roll Number", "enrolment", "rollNumber", plain),
        ("Medium of Instruction", "enrolment", "moiId", from_list("moi")),
        ("Status of student in Previous Academic Year of Schooling", "enrolment", "enrStatusPY", pick(STATUS_PY)),
        ("Grade/Class Studied in the Previous/Last Academic Year", "enrolment", "classPY", class_name),
        ("Admitted / Enrolled Under (Only for Pvt. Unaided)", "enrolment", "enrUnder", pick(ENROLLED_UNDER)),
        ("In the previous class studied - Result of the examination", "enrolment", "examResultPy", pick(EXAM_RESULT)),
        ("In the previous class studied - Marks obtained (in Percentage)", "enrolment", "examMarksPy", plain),
        ("No. of days Student attended school (in the previous academic year)", "enrolment", "attendancePy", plain),
        ("Subjects (SDMS subject codes)", "enrolment", "mandatorySubjectGroup", lambda v, m: ", ".join(map(str, v or []))),
        ("Other subjects (SDMS subject codes)", "enrolment", "curricularSubGroup", lambda v, m: ", ".join(map(str, v or []))),
        ("RTE entitlement claimed", "enrolment", "isRteAvailable", pick(YES_NO)),
        ("RTE amount", "enrolment", "rteAmount", plain),
    ]),
    ("3. Other Details", [
        ("Whether Facilities provided to the Student (for the year of filling data)", "facility", "facilityYn", pick(YES_NO)),
        ("Facilities provided", "facility", "facProvided", many("facilities")),
        ("Central Scholarship", "facility", "centralScholarshipYn", pick(YES_NO)),
        ("Code & Name of Scholarship", "facility", "centralScholarshipId", plain),
        ("State Scholarship", "facility", "stateScholarshipYn", pick(YES_NO)),
        ("Other Scholarship", "facility", "otherScholarshipYn", pick(YES_NO)),
        ("Scholarship Amount (per annum)", "facility", "scholarshipAmount", plain),
        ("Facilities provided to Student in case of CWSN (for the year of filling data)", "facility", "facProvidedCwsnYn", pick(YES_NO)),
        ("CWSN facilities provided", "facility", "facProvidedCwsn", many("cwsn_facilities")),
        ("Has the Student been identified as a Gifted / Talented", "facility", "giftedChildrenYn", pick(YES_NO)),
        ("Gifted / Talented in", "facility", "giftedChildren", lambda v, m: ", ".join(map(str, v or [])) if isinstance(v, list) else plain(v, m)),
        ("Whether provided mentors?", "facility", "mentorProvided", pick(YES_NO)),
        ("Nurturance camps - State Level", "facility", "nurturanceCmpsState", pick(YES_NO)),
        ("Nurturance camps - National Level", "facility", "nurturanceCmpsNational", pick(YES_NO)),
        ("Appeared in State/National level Competitions/Olympiads?", "facility", "olympdsNlc", pick(YES_NO)),
        ("NCC", "facility", "nccYn", pick(YES_NO)),
        ("NSS", "facility", "nssYn", pick(YES_NO)),
        ("Scouts and Guides", "facility", "scoutsYn", pick(YES_NO)),
        ("Whether student is capable of handling digital devices including the internet?", "facility", "digitalCapableYn", pick(YES_NO)),
        ("Student's Height (in CMs)", "facility", "heightInCm", plain),
        ("Student's Weight (in KGs)", "facility", "weightInKg", plain),
        ("Approximate Distance of student's residence to school", "facility", "distanceFrmSchool", pick(DISTANCE)),
        ("Completed Highest Education Level of Mother/Father/Legal Guardian", "facility", "parentEducation", pick(PARENT_EDUCATION)),
    ]),
]


def masters_from(school: Dict[str, Any], mother_tongue: list, moi: list) -> Dict[str, Dict[str, str]]:
    """The school's own SDMS lists, as {code: words}, for decoding."""
    def table(rows, key="id", text="description"):
        return {str(r.get(key)): str(r.get(text)) for r in rows or [] if isinstance(r, dict)}
    return {"mother_tongue": table(mother_tongue), "moi": table(moi),
            "facilities": table(school.get("isFacilityAvailable"), text="fieldName"),
            "cwsn_facilities": table(school.get("isCwsnAvailable"), text="fieldName"),
            "pre_primary": {str(k): str(v) for k, v in (school.get("prePrimaryClasses") or {}).items()}}


def _cell(value: Any) -> Any:
    """One answer as a single value: a list of choices (SDMS keeps some as [5]) comma separated, a group as text."""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return value


def as_form(student: Dict[str, Any], masters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[{"section": "1. General Information", "fields": [{"label", "value"}]}] for one student."""
    out = []
    for section, fields in FORM:
        rows = []
        for label, part, key, decode in fields:
            record = student.get(part) or {}
            rows.append({"label": label, "value": _cell(decode(record.get(key), masters))})
        out.append({"section": section, "fields": rows})
    return out


# ---------------------------------------------------------------------------
# What SDMS requires before a student's form counts as complete (its own form rules, read from its web app):
# the fields each tab marks required, the ones required only in some cases, and the formats it checks.
# Not here: Blood Group and "other country" - required in the code, but not enforced for this state (127 forms
# are complete without them) / only for students who are not Indian nationals.
# ---------------------------------------------------------------------------

import re as _re

NAME = _re.compile(r"^[a-zA-Z.']+( [a-zA-Z.']+)*$")
ADDRESS = _re.compile(r"^[a-zA-Z0-9,-._/()]+( [a-zA-Z0-9,-._/()]+)*$")
ADMISSION_NO = _re.compile(r"^[a-zA-Z0-9/-]+$")


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, dict)) and not value)


def _name_rule(value: Any) -> Optional[str]:
    text = str(value).strip()
    return None if NAME.match(text) and len(text) <= 100 else "letters, spaces, . and ' only (up to 100)"


def _digits(n_min: int, n_max: Optional[int] = None):
    def rule(value: Any) -> Optional[str]:
        text = str(value).strip()
        ok = text.isdigit() and len(text) >= n_min and (n_max is None or len(text) <= n_max)
        return None if ok else (f"{n_min} digits" if n_max == n_min else f"at least {n_min} digits")
    return rule


def _aadhaar_rule(value: Any) -> Optional[str]:
    """12 characters, digits or * (SDMS sends and keeps the number masked, e.g. ********1234)."""
    text = str(value).strip()
    return None if len(text) == 12 and all(ch.isdigit() or ch == "*" for ch in text) else "12 digits"


def _address_rule(value: Any) -> Optional[str]:
    text = str(value).strip()
    if not 10 <= len(text) <= 150:
        return "10 to 150 characters"
    return None if ADDRESS.match(text) else "letters, numbers, spaces and , - . _ / ( ) only"


def _admission_rule(value: Any) -> Optional[str]:
    text = str(value).strip()
    return None if ADMISSION_NO.match(text) and len(text) <= 25 else "letters, numbers, / and - only (up to 25)"


def _known(value: Any) -> Optional[str]:
    """A choice field: 0 means nothing was chosen."""
    return "not chosen" if str(value).strip() in ("0", "") else None


def _studied_last_year(s: Dict[str, Any]) -> bool:
    return _code((s.get("enrolment") or {}).get("enrStatusPY")) in (1, 2)


def _cwsn(s: Dict[str, Any]) -> bool:
    return _code((s.get("general") or {}).get("cwsnYN")) == 1


def _facilities_yes(s: Dict[str, Any]) -> bool:
    return _code((s.get("facility") or {}).get("facilityYn")) == 1


# (tab, label, part, key, decode, required-when (None: always), format rule)
Required = Tuple[str, str, str, str, Callable, Optional[Callable], Optional[Callable]]
REQUIRED: List[Required] = [
    ("General", "Gender", "general", "gender", pick(GENDER), None, _known),
    ("General", "Date of Birth", "general", "dob", plain, None, None),
    ("General", "Mother's Name", "general", "motherName", plain, None, _name_rule),
    ("General", "Father's Name", "general", "fatherName", plain, None, _name_rule),
    ("General", "AADHAAR Number of Student", "general", "uuid", plain, None, _aadhaar_rule),
    ("General", "Name of Student as per AADHAAR", "general", "nameAsUuid", plain, None, _name_rule),
    ("General", "Address", "general", "address", plain, None, _address_rule),
    ("General", "Pincode", "general", "pincode", plain, None, _digits(6, 6)),
    ("General", "Mobile Number", "general", "primaryMobile", plain, None, _digits(10, 10)),
    ("General", "Mother Tongue", "general", "motherTongue", from_list("mother_tongue"), None, _known),
    ("General", "Social Category", "general", "socCatId", pick(SOCIAL), None, _known),
    ("General", "Minority Group", "general", "minorityId", pick(MINORITY), None, _known),
    ("General", "BPL beneficiary?", "general", "isBplYN", pick(YES_NO), None, _known),
    ("General", "AAY beneficiary?", "general", "aayBplYN", pick(YES_NO), None, _known),
    ("General", "EWS / Disadvantaged Group?", "general", "ewsYN", pick(YES_NO), None, _known),
    ("General", "CWSN?", "general", "cwsnYN", pick(YES_NO), None, _known),
    ("General", "Type of impairment (if CWSN)", "general", "impairmentType", plain, _cwsn, None),
    ("General", "Disability Percentage (if CWSN)", "general", "impairmentPercent", plain, _cwsn, None),
    ("General", "Indian National?", "general", "natIndYN", pick(YES_NO), None, _known),
    ("General", "Out-of-School-Child?", "general", "ooscYN", pick(YES_NO), None, _known),
    ("General", "Mainstreamed?", "general", "ooscMainstreamedYN", pick(YES_NO), None, _known),
    ("Enrolment", "Admission Number in Present School", "enrolment", "admnNumber", plain, None, _admission_rule),
    ("Enrolment", "Admission Date in Present School", "enrolment", "admnStartDate", plain, None, None),
    ("Enrolment", "Status in Previous Academic Year", "enrolment", "enrStatusPY", pick(STATUS_PY), None, _known),
    ("Enrolment", "Class Studied in Previous Year", "enrolment", "classPY", class_name, _studied_last_year, None),
    ("Enrolment", "Previous Class - Result", "enrolment", "examResultPy", pick(EXAM_RESULT), _studied_last_year, _known),
    ("Enrolment", "Previous Class - Marks (%)", "enrolment", "examMarksPy", plain, _studied_last_year, None),
    ("Enrolment", "Days Attended (previous year)", "enrolment", "attendancePy", plain, _studied_last_year, None),
    ("Enrolment", "Medium of Instruction", "enrolment", "moiId", from_list("moi"), None, _known),
    ("Enrolment", "Subjects (SDMS codes)", "enrolment", "mandatorySubjectGroup", plain, None, None),
    ("Other", "Facilities provided?", "facility", "facilityYn", pick(YES_NO), None, _known),
    ("Other", "Which facilities", "facility", "facProvided", many("facilities"), _facilities_yes, None),
    ("Other", "CWSN facilities provided? (if CWSN)", "facility", "facProvidedCwsnYn", pick(YES_NO), _cwsn, None),
    ("Other", "Olympiads / Competitions?", "facility", "olympdsNlc", pick(YES_NO), None, _known),
    ("Other", "NCC", "facility", "nccYn", pick(YES_NO), None, _known),
    ("Other", "NSS", "facility", "nssYn", pick(YES_NO), None, _known),
    ("Other", "Scouts and Guides", "facility", "scoutsYn", pick(YES_NO), None, _known),
    ("Other", "Height (cm)", "facility", "heightInCm", plain, None, _digits(2, 3)),
    ("Other", "Weight (kg)", "facility", "weightInKg", plain, None, _digits(1, 3)),
    ("Other", "Distance to School", "facility", "distanceFrmSchool", pick(DISTANCE), None, _known),
    ("Other", "Parents' Highest Education", "facility", "parentEducation", pick(PARENT_EDUCATION), None, _known),
]


def completion(student: Dict[str, Any], masters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every required field for this student: its answer in words, and what is missing or wrong ("" when fine).
    A field required only in some cases (CWSN, studied last year ...) is "not needed" otherwise."""
    out = []
    for tab, label, part, key, decode, when, rule in REQUIRED:
        raw = (student.get(part) or {}).get(key)
        needed = when is None or when(student)
        shown = _cell(decode(raw, masters))
        if not needed:
            issue = ""
            shown = shown if not _blank(raw) else "not needed"
        elif _blank(raw):
            issue = "empty"
        else:
            issue = (rule(raw) or "") if rule else ""
        out.append({"tab": tab, "label": label, "value": shown, "issue": issue})
    return out


# ---------------------------------------------------------------------------
# A new admission (SDMS: a class's "Add Student", current session - api/new-admission/AY): the fields of its
# form (basicDetailsForm), then the rest SDMS requires before the new student's form is complete.
# (label, required, kind) - kind: "text", "date", "digits", or a list name for a drop-down.
# ---------------------------------------------------------------------------

ADD_STUDENT: List[Tuple[str, bool, str]] = [
    ("Class", True, "classes"),
    ("Section", True, "text"),
    ("Student's Name (as per School Admission Register)", True, "text"),
    ("Gender", True, "gender"),
    ("Date of Birth (DD/MM/YYYY)", True, "date"),
    ("Mother's Name", True, "text"),
    ("Father's Name", True, "text"),
    ("Guardian's Name", False, "text"),
    ("AADHAAR Number of Student (12 digits)", True, "digits"),
    ("Name of Student as per AADHAAR", True, "text"),
    ("Admission Date in Present School (DD/MM/YYYY)", True, "date"),
    ("State Student Code", False, "text"),
    ("Mobile Number (10 digits)", True, "digits"),
    ("Alternate Mobile Number", False, "digits"),
    ("Whether CWSN?", True, "yes_no"),
]
REST_OF_FORM: List[Tuple[str, bool, str]] = [
    ("Address (10 to 150 characters)", True, "text"),
    ("Pincode (6 digits)", True, "digits"),
    ("Mother Tongue", True, "mother_tongue"),
    ("Social Category", True, "social"),
    ("Minority Group", True, "minority"),
    ("Whether BPL beneficiary?", True, "yes_no"),
    ("Whether AAY beneficiary?", True, "yes_no_na"),
    ("Whether EWS / Disadvantaged Group?", True, "yes_no"),
    ("Type of impairment (if CWSN)", False, "text"),
    ("Disability Percentage (if CWSN)", False, "digits"),
    ("Whether Indian National?", True, "yes_no"),
    ("Out-of-School-Child?", True, "yes_no"),
    ("Mainstreamed?", True, "yes_no_na"),
    ("Admission Number in Present School", True, "text"),
    ("Status in Previous Academic Year", True, "status_py"),
    ("Class Studied in Previous Year (if studied)", False, "classes"),
    ("Previous Class - Result (if studied)", False, "exam_result"),
    ("Previous Class - Marks % (if studied)", False, "digits"),
    ("Days Attended last year (if studied)", False, "digits"),
    ("Medium of Instruction", True, "moi"),
    ("Facilities provided?", True, "yes_no"),
    ("Which facilities (comma separated)", False, "text"),
    ("Olympiads / Competitions?", True, "yes_no_na"),
    ("NCC", True, "yes_no_na"),
    ("NSS", True, "yes_no_na"),
    ("Scouts and Guides", True, "yes_no_na"),
    ("Height (cm)", True, "digits"),
    ("Weight (kg)", True, "digits"),
    ("Distance to School", True, "distance"),
    ("Parents' Highest Education", True, "parent_education"),
]


def admission_lists(masters: Dict[str, Any], classes: List[str]) -> Dict[str, List[str]]:
    """The drop-down choices, in SDMS's words."""
    return {"classes": classes, "gender": list(GENDER.values()), "yes_no": ["Yes", "No"],
            "yes_no_na": ["Yes", "No", "Not applicable"], "social": list(SOCIAL.values()),
            "minority": list(MINORITY.values()), "status_py": list(STATUS_PY.values()),
            "exam_result": list(EXAM_RESULT.values()), "distance": list(DISTANCE.values()),
            "parent_education": list(PARENT_EDUCATION.values()),
            "mother_tongue": sorted((masters.get("mother_tongue") or {}).values()),
            "moi": sorted((masters.get("moi") or {}).values())}
