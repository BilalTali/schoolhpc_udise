"""
Part A warnings (never blocking a save) for answers PARAKH accepts but that read wrong:

  A2   text that stops exactly at PARAKH's limit in the middle of a word (cut off before it reached the app)
  A4   the template's own options left in an answer ("Completing assignment(sometimes, most times, all the time)")
  A5   Middle's "I ... very well" left empty
  A6   Middle's ambition reading like a teacher's remark; "I will take guidance from" naming no person
  A10  nearly every interest ticked
  A12  a first name and the gender on PARAKH that look inconsistent (only a warning: PARAKH's record is the school's)

`row`: a card's values as the card editor keeps them; `fields`: the stage's Field objects (for labels and limits).
"""
import re
from typing import Any, Dict, Iterable, List

TEMPLATE_OPTIONS = re.compile(r"\s*\(\s*sometimes\s*,\s*most times\s*,\s*all the time\s*\)\s*", re.I)
REMARK = re.compile(r"^(shows|demonstrates|is a|takes part|needs|has shown)\b|\battendance\b|\bparticipation\b", re.I)
PERSON = re.compile(r"\b(teachers?|parents?|mother|father|brother|sister|uncle|aunt|grand\w*|elders?|coach|doctor|"
                    r"mentor|family|principal|guardian|cousin|friends?|sir|madam|mr|mrs|ms|dr)\b", re.I)
# first names that are clearly a boy's or a girl's in this region (a warning only, never a change)
BOYS = {"mustafa", "mohammad", "muhammad", "mohd", "ahmad", "ali", "bilal", "tariq", "showket", "shabir", "imran",
        "irfan", "faisal", "zubair", "umar", "omar", "danish", "adil", "aamir", "arif", "javid", "rafiq", "sajad",
        "suhail", "tanveer", "yasir", "zahid", "aarav", "rahul", "rohit", "amit", "vikas", "arjun", "ravi"}
GIRLS = {"fatima", "insha", "pakeeza", "pakeezah", "zoya", "aamina", "amina", "rabiya", "hizhat", "toiba", "mehvish",
         "saima", "shazia", "rukhsana", "nazia", "iqra", "sana", "mehak", "khushboo", "priya", "anjali", "pooja",
         "neha", "kajal", "sakina", "zainab", "ayesha", "aisha", "maryam", "hafsa", "nusrat"}


def strip_template_options(text: Any) -> Any:
    """A4: 'Completing assignment(sometimes, most times, all the time)' -> 'Completing assignment'."""
    if not isinstance(text, str):
        return text
    return TEMPLATE_OPTIONS.sub(" ", text).strip()


def looks_cut_off(text: str, max_len: Any) -> bool:
    """A2: exactly at the limit and ending inside a word ('learning new co')."""
    return bool(max_len) and len(text) == int(max_len) and int(max_len) < 120 and text[-1:].isalnum() \
        and " " in text and not text.endswith((".", "!", "?"))


def name_gender_mismatch(name: str, gender: str) -> str:
    first = (str(name or "").strip().split() or [""])[0].lower()
    g = str(gender or "").strip().lower()
    if first in BOYS and g.startswith("f"):
        return f"'{first.title()}' is usually a boy's name but PARAKH has the gender as Female"
    if first in GIRLS and g.startswith("m"):
        return f"'{first.title()}' is usually a girl's name but PARAKH has the gender as Male"
    return ""


def part_a_warnings(stage: str, row: Dict[str, Any], fields: Iterable[Any], student: Dict[str, Any]) -> Dict[str, List[str]]:
    """{part code: warnings} for A1 to A4."""
    out: Dict[str, List[str]] = {}
    middle = stage.lower().startswith("mid")
    for f in fields:
        value = row.get(f.key)
        part = f.key.split("_", 1)[0].upper()
        if f.kind == "text" and isinstance(value, str) and value.strip():
            if looks_cut_off(value.strip(), f.max_len):
                out.setdefault(part, []).append(f"{f.label}: '{value.strip()}' looks cut off at PARAKH's {f.max_len}-character "
                                                "limit - write it shorter")
            if TEMPLATE_OPTIONS.search(value):
                out.setdefault(part, []).append(f"{f.label}: the template's options '(sometimes, most times, all the time)' "
                                                "are in the answer - they are taken out when it is saved")
        if f.kind == "multi" and f.key == "a1_interests":
            ticked = value if isinstance(value, list) else [v for v in str(value or "").split(",") if v.strip()]
            if f.options and len(ticked) >= max(4, round(len(f.options) * 0.75)):
                out.setdefault("A1", []).append(f"Interests: {len(ticked)} of {len(f.options)} are ticked - tick only "
                                                "the ones the student has")
    if middle:
        if not str(row.get("a2_about_4") or "").strip():
            out.setdefault("A2", []).append("'I ... very well' is empty")
        ambition = str(row.get("a3_myAmbition") or "").strip()
        if ambition and REMARK.search(ambition):
            out.setdefault("A3", []).append(f"'My ambition is' reads like a teacher's remark ('{ambition[:50]}') - it is "
                                            "the student's own ambition")
        guide = str(row.get("a3_guidanceFrom") or "").strip()
        if guide and not PERSON.search(guide):
            out.setdefault("A3", []).append(f"'I will take guidance from' names no person ('{guide[:50]}') - the form asks "
                                            "for a person (a teacher, a parent ...)")
    clash = name_gender_mismatch(student.get("student_name", ""), student.get("gender", ""))
    if clash:
        out.setdefault("A1", []).append(f"Gender: {clash}. Please check the school record (it is not changed here).")
    return out
