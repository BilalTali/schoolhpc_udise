"""
UDISE+ Teacher module: the yearly staff forms (DCF section 3), field by field, from the Teacher service's own pages
(teacher.udiseplus.gov.in).

Staff types: 1 teaching, 2 non-teaching, 3 vocational (VTP), 4 special educator.
Every staff member has:
  Form 1  General profile             GET  teacher/emp-staff/form1/{school}/{staff}   POST teacher/emp-staff/form1/{school}/saveOrUpdate
  Form 2  Appointment (and teaching)  teaching:      GET teacher/emp-staff/form2/{staff}/{school}
                                                     POST teacher/emp-staff/form2/{school}/saveOrUpdate
                                      non-teaching:  GET teacher/non-teaching-staff/{staff}/{school}
                                                     POST teacher/non-teaching-staff/form2/{school}/saveOrUpdate
                                      special educ.: GET teacher/special-educator/{staff}/{school}
                                                     POST teacher/special-educator/form2/{school}/saveOrUpdate
  Form 3  Training and other details  (teaching only) GET teacher/emp-staff/form3/{staff}/{school}
                                                     POST teacher/emp-staff/form3/{school}/saveOrUpdate
A new staff member is Form 1 sent with createdFlag true, the Aadhaar number (referenceKey) and the name as per
Aadhaar; UDISE+ gives the staff id, and Forms 2 and 3 follow.

A field: (form, key, label, kind). kinds:
  "list:NAME"  a code from a list UDISE+ gives (LISTS: where it comes from)
  "yn"         1-Yes, 2-No
  "date"       DD/MM/YYYY
  "num", "year", "text", "mobile", "email"
"""
from typing import Any, Dict, List, Tuple

YN = {1: "Yes", 2: "No"}
GENDER = {1: "Male", 2: "Female", 3: "Transgender"}

STAFF_TYPES = {1: "Teaching staff", 2: "Non-teaching staff", 4: "Special educators"}

Field = Tuple[str, str, str, str]

FORM1: List[Field] = [
    ("1", "empName", "3.2.1 Name (in capital letters)", "text"),
    ("1", "gender", "3.2.3 Gender", "list:gender"),
    ("1", "dob", "3.2.4 Date of birth (DD/MM/YYYY)", "date"),
    ("1", "empCodeState", "3.2.5 Staff code of State/UT (if any)", "text"),
    ("1", "socialCat", "3.2.6 Social category", "list:socialCategory"),
    ("1", "qualAcad", "3.2.7 Highest academic qualification", "list:qualificationLevels"),
    ("1", "trade", "3.2.7 Trade / Degree", "list:degree"),
    ("1", "qualProf", "3.2.8 Highest professional qualification", "list:professionalQualifications"),
    ("1", "mathUpto", "3.2.10(a) Level up to which Mathematics was studied", "list:qualificationLevels"),
    ("1", "scienceUpto", "3.2.10(b) Level up to which Science was studied", "list:qualificationLevels"),
    ("1", "englishUpto", "3.2.10(c) Level up to which English was studied", "list:qualificationLevels"),
    ("1", "socStudyUpto", "3.2.10(d) Level up to which Social Science was studied", "list:qualificationLevels"),
    ("1", "langStudyUpto", "3.2.10(e) Level up to which a Language (Schedule VIII) was studied", "list:qualificationLevels"),
    ("1", "mobile", "3.2.11 Mobile number", "mobile"),
    ("1", "email", "3.2.12 Email", "email"),
    ("1", "disabilityType", "3.2.13 Type of disability (if any)", "list:disabilities"),
]
FORM1_NON_TEACHING = [f for f in FORM1 if f[1] not in ("mathUpto", "scienceUpto", "englishUpto", "socStudyUpto", "langStudyUpto")]
FORM1_NEW = [("1", "referenceKey", "3.2.9 Aadhaar number (12 digits)", "aadhaar"),
             ("1", "empNamePerUid", "3.2.9 Name as per Aadhaar", "text")]

FORM2_TEACHING: List[Field] = [
    ("2", "tchType", "3.2.14 Type of teacher / current post held", "list:teacherTypes"),
    ("2", "classTaught", "3.2.16 Classes taught", "list:classesTaught"),
    ("2", "appointedLevel", "3.2.17 Appointed for level (optional)", "list:appointmentsLevel"),
    ("2", "apptSub", "3.2.18 Appointed for subject", "list:subjects"),
    ("2", "subTaught1", "3.2.19(a) Main subject taught 1", "list:subjects"),
    ("2", "subTaught2", "3.2.19(b) Main subject taught 2 (optional)", "list:subjects"),
    ("2", "tchDeputation", "On deputation in this school from another school?", "yn"),
    ("2", "tchFromOtherSchool", "Also teaching at another school as guest/contractual?", "yn"),
    ("2", "natureOfAppt", "Nature of appointment", "list:natureOfAppointments"),
    ("2", "dojService", "Date of joining in service (DD/MM/YYYY)", "date"),
    ("2", "dojPs", "Date of joining in present school (DD/MM/YYYY)", "date"),
    ("2", "docPh", "Date of joining in present teacher type / post held (DD/MM/YYYY)", "date"),
]
FORM2_NON_TEACHING: List[Field] = [
    ("2", "postId", "Current post held", "list:posts"),
    ("2", "natureOfAppt", "Nature of appointment", "list:natureOfAppointments"),
    ("2", "dojService", "Date of joining in service (DD/MM/YYYY)", "date"),
    ("2", "dojPs", "Date of joining in present school (DD/MM/YYYY)", "date"),
    ("2", "docPh", "Date of joining in present post (DD/MM/YYYY)", "date"),
]
FORM2_SPECIAL: List[Field] = [
    ("2", "postId", "Current post held", "list:specialPosts"),
    ("2", "dateCurrPostHeld", "Date of joining in current post (DD/MM/YYYY)", "date"),
    ("2", "classesTaught", "Classes taught", "list:classesTaught"),
    ("2", "natureOfAppt", "Nature of appointment", "list:natureOfAppointments"),
    ("2", "dojService", "Date of joining in service (DD/MM/YYYY)", "date"),
    ("2", "dojPs", "Date of joining in present school (DD/MM/YYYY)", "date"),
]
FORM3: List[Field] = [
    ("3", "trainedCwsn", "Trained for teaching CWSN?", "yn"),
    ("3", "trainedComp", "Trained in computer for use in teaching?", "yn"),
    ("3", "trngRcvd", "Training received", "list:training"),
    ("3", "trngNeeded", "Training needs", "list:training"),
    ("3", "trgNishtha", "Received training under NISHTHA?", "yn"),
    ("3", "nontchDays", "Working days spent on non-teaching assignments (0-250)", "num"),
    ("3", "mainLang1", "Language of working knowledge 1", "list:languages"),
    ("3", "mainLang2", "Language of working knowledge 2", "list:languages"),
    ("3", "mainLang3", "Language of working knowledge 3", "list:languages"),
    ("3", "trSsaYn", "Trained in safety and security audit of school?", "yn"),
    ("3", "cyberSafetyYn", "Received training on cyber safety?", "yn"),
    ("3", "psySocAspectYn", "Received training on psycho-social aspects?", "yn"),
    ("3", "receTrainingSupportCwsnYn", "Received training in early identification and classroom support of CWSN?", "yn"),
    ("3", "isCtetStet", "CTET/STET qualified?", "yn"),
    ("3", "ctetStet", "If yes, year of qualifying CTET/STET", "year"),
    ("3", "isCapableVc", "Capable of handling digital devices and VC applications?", "yn"),
]

# fields not every staff member must fill (the page marks them optional)
OPTIONAL = {"empCodeState", "appointedLevel", "subTaught2", "mainLang2", "mainLang3", "trngNeeded"}
# "if yes" fields
WHEN = {"ctetStet": ("isCtetStet", {1})}


def columns(staff_type: int, new: bool = False) -> List[Field]:
    """The workbook columns for one staff type, in the order of the forms."""
    if staff_type == 1:
        cols = FORM1 + FORM2_TEACHING + FORM3
    elif staff_type == 2:
        cols = FORM1_NON_TEACHING + FORM2_NON_TEACHING
    else:
        cols = FORM1_NON_TEACHING + FORM2_SPECIAL
    if new:
        cols = cols[:1] + FORM1_NEW + cols[1:]
    return cols


def paths(staff_type: int, school: Any, staff: Any) -> Dict[str, Tuple[str, str]]:
    """form -> (read path, save path)."""
    out = {"1": (f"/teacher/emp-staff/form1/{school}/{staff}", f"/teacher/emp-staff/form1/{school}/saveOrUpdate")}
    if staff_type == 1:
        out["2"] = (f"/teacher/emp-staff/form2/{staff}/{school}", f"/teacher/emp-staff/form2/{school}/saveOrUpdate")
        out["3"] = (f"/teacher/emp-staff/form3/{staff}/{school}", f"/teacher/emp-staff/form3/{school}/saveOrUpdate")
    elif staff_type == 2:
        out["2"] = (f"/teacher/non-teaching-staff/{staff}/{school}", f"/teacher/non-teaching-staff/form2/{school}/saveOrUpdate")
    elif staff_type == 4:
        out["2"] = (f"/teacher/special-educator/{staff}/{school}", f"/teacher/special-educator/form2/{school}/saveOrUpdate")
    return out


def options_of(kind: str, lists: Dict[str, Dict[int, str]]) -> Dict[int, str]:
    if kind == "yn":
        return YN
    if kind == "list:gender":
        return lists.get("gender") or GENDER
    if kind.startswith("list:"):
        return lists.get(kind[5:]) or {}
    return {}


def as_options(raw: Any) -> Dict[int, str]:
    """A list from UDISE+ as code -> words, whatever its shape: [{id, name}], [{value, label}], {"1": "x"} ..."""
    out: Dict[int, str] = {}
    if isinstance(raw, dict):
        if all(str(k).lstrip("-").isdigit() for k in raw):
            return {int(k): str(v) for k, v in raw.items()}
        raw = raw.get("data") or raw.get("body") or []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        code = next((item[k] for k in item if k.lower() in ("id", "value", "code") or k.lower().endswith("id")
                     or k.lower().endswith("code")), None)
        name = next((item[k] for k in item if isinstance(item[k], str) and (
            k.lower() in ("name", "label", "desc", "description", "value_name") or k.lower().endswith("name")
            or k.lower().endswith("desc"))), None)
        try:
            out[int(code)] = str(name if name is not None else code)
        except (TypeError, ValueError):
            continue
    return out
