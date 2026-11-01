"""
Data completeness report (section 6.2): for one student's card, per section (A1-A4, each Part B activity, Part C,
HPC Credit), the fields that are

  empty         required by PARAKH or meant to be filled, and blank
  defaulted     still one of the app's ready phrases (a stock sentence, not something written for this student)
  duplicated    the same free text in 3 or more activities, the same note under several subjects
  inconsistent  what the checks find (notes vs levels, Part C vs Part B, cut-off text, name vs gender, totals ...)

APAAR ID, UDID, BRC and CRC are optional: listed under "optional_blank", never as a problem. Works offline on the
app's stored copy of a card (data/cards) or on parts read just now; nothing is sent anywhere.
"""
from typing import Any, Dict, List, Optional

from backend.hpc import checks, credit, notes, part_a_checks, suggestions
from backend.hpc.stages import get_stage

OPTIONAL = {"a1_udid", "a1_other_interest", "a1_low_attendance"}     # only needed in some cases
KINDS = ("empty", "defaulted", "duplicated", "inconsistent")
# the app's ready sentences (not short factual answers like a language or a flower, which a student may truly give)
STOCK = {p.strip().lower() for v in suggestions.SUGGESTIONS.values() for p in v if " " in p.strip() and len(p) >= 25} \
    | checks.STOCK


class OfflineLookups:
    """Enough of Lookups to read a stored card without PARAKH: A1's three lists are not known offline (their
    answers are reported from the raw codes)."""
    medium: List[Dict[str, Any]] = []
    location: List[Dict[str, Any]] = []
    interests: List[Dict[str, Any]] = []
    grades: List[Dict[str, Any]] = []

    def options(self, rows) -> Dict[str, Any]:
        return {}

    def section_name(self, section_id) -> str:
        return ""


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, (list, dict)) and not value) or str(value).strip() in ("", "[]")


def report(stage: str, raw_parts: Dict[str, Any], record: Optional[Dict[str, Any]] = None,
           draft: Optional[Dict[str, Any]] = None, lookups: Any = None) -> Dict[str, Any]:
    st = get_stage(stage)
    lk = lookups or OfflineLookups()
    record = record or {}
    sections: Dict[str, Dict[str, List[str]]] = {}

    def add(section: str, kind: str, text: str) -> None:
        sections.setdefault(section, {k: [] for k in KINDS})[kind].append(text)

    loaded = {p.col: p.load((raw_parts or {}).get(p.col)) for p in st.PARTS}
    row: Dict[str, Any] = {}
    fields = []
    for p in st.PARTS:
        if p.code == "B":
            continue
        for f in p.fields(lk):
            fields.append(f)
            try:
                row[f.key] = f.read(loaded[p.col])
            except Exception:                              # a list not known offline
                row[f.key] = ""
    row.update(draft or {})

    # Part A, C, D fields
    part_of = {f.key: p.code for p in st.PARTS if p.code != "B" for f in p.fields(lk)}
    for f in fields:
        section, value = part_of[f.key], row.get(f.key)
        if f.key in OPTIONAL or (f.key.startswith("a1_") and f.kind in ("choice", "multi") and not f.options):
            continue
        if _blank(value):
            if f.required or (f.kind == "text" and not f.key.endswith(("_other", "_oth"))):
                add(section, "empty", f.label)
        elif f.kind == "text" and str(value).strip().lower() in STOCK:
            add(section, "defaulted", f"{f.label}: '{str(value).strip()}'")

    # A1 facts from PARAKH's record: optional ones are listed, never flagged
    a1 = loaded.get("part_a1") or {}
    basic = (list(a1.get("basic") or []) + [""] * 11)[:11]
    optional = [label for label, value in (("APAAR ID", basic[1]), ("BRC", basic[5]), ("CRC", basic[6]),
                                           ("UDID", row.get("a1_udid"))) if _blank(value)]
    gen = (list(a1.get("gen") or []) + [""] * 26)[:26]
    stu = {**(record.get("stu_info") or {})}
    stu.setdefault("student_name", basic[0])
    stu.setdefault("gender", gen[25])

    for section, warnings in part_a_checks.part_a_warnings(stage, row, fields, stu).items():
        for w in warnings:
            add(section, "inconsistent", w)

    # Part B, activity by activity
    acts = loaded.get("part_b") if isinstance(loaded.get("part_b"), list) else []
    real = [a for a in acts if (a or {}).get("dt") and ((a["dt"].get("domain")) or a["dt"].get("act_bank_id"))]
    for n, act in enumerate(real, start=1):
        dt, name = act["dt"], act.get("nm") or f"Activity {n}"
        section = f"B{n} {name}"
        for label, ok in (("Curricular goal", dt.get("gl")), ("Competency", dt.get("cpt"))):
            if not ok:
                add(section, "empty", label)
        if "activity" in dt and not dt.get("activity"):
            add(section, "empty", "Approach of the activity")
        for key, index, label in checks.FREE_TEXT:
            if key not in dt:
                continue
            text = checks._at(dt, key, index)
            if not text:
                add(section, "empty", label)
            elif text.lower() in STOCK:
                add(section, "defaulted", f"{label}: '{text}'")
        if "pf" in dt and not any(str(v or "").strip() for v in (dt.get("pf") or [])[:2]):
            add(section, "empty", "Peer feedback (no peer names: not collected)")
    for w in checks.part_b_warnings(real):
        add("B", "duplicated" if "the same in" in w else "inconsistent", w)

    # Part C
    for w in checks.part_c_warnings(stage, st.DOMAINS, st.SUBJECTS, row):
        add("C", "duplicated" if "same note is under" in w else "inconsistent", w)
    for w in checks.part_b_vs_c(st.DOMAINS, st.SUBJECTS, row, real):
        add("C", "inconsistent", w)
    for domain, name in zip(st.DOMAINS, st.SUBJECTS):
        if not checks.note_of(row, domain) and all(notes.levels_from_row(row, domain).values()):
            add("C", "empty", f"{name}: note (its levels are ticked - 'Write from levels' fills it)")

    # HPC Credit
    d = loaded.get("hpc_credit") or {}
    key = stage.lower()
    if key in ("preparatory", "middle") and d.get("table3"):
        grade = (record.get("cond_class") or gen[2] or "")
        for w in credit.verify_tables(key, d, grade):
            add("D", "inconsistent", w)
        skill = next((r for r in d["table3"] if r and r[0] == "Vocational/Skill Education"), None)
        if skill and not credit.SKILL_KEY_FIX and str(skill[3]) in ("0", "0.0"):
            add("D", "inconsistent", "Vocational/Skill Education earns 0 credits: PARAKH's own page has no credit table "
                                     "under the key it uses (a PARAKH bug - raise it with NCERT)")
    return {"student": basic[0] or stu.get("student_name", ""), "stage": stage,
            "optional_blank": optional, "sections": sections}


def as_text(rep: Dict[str, Any]) -> str:
    lines = [f"{rep['student']} ({rep['stage']})"]
    if rep["optional_blank"]:
        lines.append(f"  optional, blank (fine): {', '.join(rep['optional_blank'])}")
    for section, kinds in rep["sections"].items():
        found = [(k, v) for k, v in kinds.items() if v]
        if not found:
            continue
        lines.append(f"  [{section}]")
        for kind, items in found:
            for item in items:
                lines.append(f"    {kind:<12} {item}")
    return "\n".join(lines)
