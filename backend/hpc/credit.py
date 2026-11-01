"""
HPC Credit (Part D) tables, calculated exactly like the portal's hpc-credit page.

The portal's browser code - not its server - builds table2/table3 from the Part C
ratings and the summative marks before saving, so we must reproduce that maths
(including JavaScript rounding) or the saved card would show wrong numbers.
Constants come from reference/credit_tables.json, extracted from that page.
"""
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List

TABLES = json.loads((Path(__file__).parent / "reference" / "credit_tables.json").read_text(encoding="utf-8"))

# Display names used by the portal (its English translations).
SUBJECT_LABELS = {
    "Language-education-r1": "Language 1 (R1)", "Language-education-r2": "Language 2 (R2)",
    "mathematics": "Mathematics", "the-world-around": "The World Around Us",
    "art-education": "Art Education", "physical-education": "Physical Education and Well-being",
    "other-learning-activities": "Other Learning Activities (Participation in Cultural, Sports, Reading and other activities)",
    "language-r1": "Language 1 (R1)", "language-r2": "Language 2 (R2)", "language-r3": "Language 3 (R3)",
    "mathematics-middle": "Mathematics", "science-middle": "Science", "social-science-middle": "Social Science",
    "art-education-middle": "Art Education", "physical-education-middle": "Physical Education and Well-being",
    "vocational-skill-education": "Vocational/Skill Education",
    "bagless-days-vocational-experience": "Bagless days for vocational Experience",
    "physical-development": "Physical Development", "social-development": "Social Development",
    "cognitive-development": "Cognitive Development", "language-literacy-development": "Language and Literacy Development",
    "aesthetic-cultural-development": "Aesthetic and Cultural Development",
    "positive-learning-habits": "Positive Learning Habits",
}
RATING_NAMES = {1: "Beginner", 2: "Proficient", 3: "Advance"}

# C2: PARAKH's page looks Vocational/Skill Education up under "vocational-skill-education", but its credit table has
# the subject as "skill-education-middle" - so on PARAKH the subject earns 0 credits and 0 marks whatever its levels.
# False: the app saves what PARAKH's own page would (0). True: the app uses the subject's real credit table.
SKILL_KEY_FIX = False
CREDIT_ALIASES = {"vocational-skill-education": "skill-education-middle"}


def credit_row(stage: str, key: str) -> Dict[str, Any]:
    """A subject's credit constants ({} when PARAKH has none for its key)."""
    table = TABLES[stage]["credits"]
    if key not in table and SKILL_KEY_FIX and CREDIT_ALIASES.get(key) in table:
        return table[CREDIT_ALIASES[key]]
    return table.get(key, {})
RATING_LABELS = {"Beginner": "Beginner", "Proficient": "Proficient", "Advance": "Advanced"}


def _round2(x: float) -> float:
    """JS parseFloat(x.toFixed(2))."""
    return float(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _js_round(x: float) -> int:
    """JS Math.round (halves round up)."""
    return math.floor(x + 0.5)


def js_num(x: float):
    """Whole numbers as int, like JSON.stringify does for JS numbers (0 not 0.0)."""
    return int(x) if float(x).is_integer() else x


def js_str(x: float) -> str:
    """JS number-to-string, e.g. 198.0 -> '198', 15.84 -> '15.84'."""
    return str(int(x)) if float(x).is_integer() else repr(float(x))


def _number(value: Any) -> float:
    try:
        return float(str(value).strip())
    except ValueError:
        return float("nan")


def subjects(stage: str) -> List[Dict[str, Any]]:
    return TABLES[stage]["subjects"]


def sa_applicable(stage: str, index: int) -> bool:
    """Whether a subject has summative-assessment marks (otherwise its mark cells stay blank)."""
    subject = subjects(stage)[index]
    sa_credits = credit_row(stage, subject["key"]).get("saCredits", 0)
    return subject.get("saApplicable", True) and sa_credits > 0


def summative_subjects(stage: str) -> List[tuple]:
    """(number used in the workbook keys d_<n>_max / d_<n>_obtained, subject name) for subjects with marks."""
    key = stage.lower()
    if key not in TABLES or key == "foundational":
        return []
    return [(str(i + 1), SUBJECT_LABELS[s["key"]]) for i, s in enumerate(subjects(key)) if sa_applicable(key, i)]


def build_tables(stage: str, part_c: Dict[str, Any], domains: List[str],
                 marks: List[List[str]], grade_code: str) -> Dict[str, Any]:
    """
    stage      'preparatory' | 'middle'
    part_c     Part C formdata ({domain: [awareness, sensitivity, creativity, remark], ...})
    domains    Part C domain keys in subject order (e.g. PSLS1..PSLS7)
    marks      [[max, obtained], ...] per subject, as entered on the credit page
    grade_code e.g. 'grd5'
    Returns {"table2": [...], "table3": [...]} as the portal stores them.
    """
    level = next((g["nationalCreditLevel"] for g in TABLES[stage]["grades"] if grade_code in g["classCodes"]), 0)
    subs = subjects(stage)

    def formative(i):
        key = subs[i]["key"]
        ratings = part_c.get(domains[i], []) if i < len(domains) else []
        names = [RATING_NAMES.get(int(_number(r)) if _number(r) == _number(r) else 0, "")
                 for r in (list(ratings) + ["", "", ""])[:3]]
        per = credit_row(stage, key).get("formativeCreditsPerCompetency", {})
        parts = [_round2(float(per.get(n, 0) or 0)) if n else 0 for n in names]
        total = _round2(sum(parts))
        return names, total

    def summative(i):
        if not sa_applicable(stage, i):
            return 0
        mx, got = (_number(v) for v in (marks[i] + ["", ""])[:2])
        if not (math.isfinite(mx) and math.isfinite(got)) or mx <= 0 or got < 0:
            return 0
        return _round2(min(1, max(0, got / mx)) * credit_row(stage, subs[i]["key"])["saCredits"])

    def percent(key, earned):
        c = credit_row(stage, key)
        out_of = c.get("hpcMaxCredits", 0) + c.get("saCredits", 0)
        return _js_round(earned / out_of * 100) if out_of > 0 and math.isfinite(earned) else 0

    table2, table3 = [], []
    max_total = obt_total = 0.0
    sums = {"f": 0, "sa": 0, "earned": 0, "points": 0}
    marks_total = 0
    for i, sub in enumerate(subs):
        key = sub["key"]
        names, total = formative(i)
        sa = summative(i)
        earned = _round2(total + sa)
        points = _round2(earned * level)
        pct = percent(key, earned)

        applicable = sa_applicable(stage, i)
        mx, got = ((marks[i] + ["", ""])[:2] if applicable else ("", ""))
        if applicable:
            if _number(mx) > 0:
                max_total += _number(mx)
            if _number(got) >= 0:
                obt_total += _number(got)
        table2.append([SUBJECT_LABELS[key], *(RATING_LABELS[n] if n else "" for n in names), str(mx), str(got)])
        table3.append([SUBJECT_LABELS[key], *(js_num(v) for v in (total, sa, earned, points)), pct])

        for name, v in (("f", total), ("sa", sa), ("earned", earned), ("points", points)):
            sums[name] += _js_round(v * 100)
        marks_total += pct

    table2.append(["Total", "", "", "", js_str(_round2(max_total)), js_str(_round2(obt_total))])
    table3.append(["Total", js_str(sums["f"] / 100), js_str(sums["sa"] / 100), js_str(sums["earned"] / 100),
                   js_str(sums["points"] / 100), str(marks_total)])
    return {"table2": table2, "table3": table3}


# ---------------------------------------------------------------------------
# The rule, as PARAKH's hpc-credit page applies it (Preparatory, Middle), per subject row:
#   HPC credit      = sum over Awareness, Sensitivity, Creativity of formativeCreditsPerCompetency[level]
#                     (each subject's own table; the NCF hours are already in these numbers - hpcMaxCredits is
#                     the subject's share of the year's hours - so nothing is weighted by hours again)
#   summative (SA)  = marks obtained / max marks x saCredits (0 when the subject has no SA)
#   total credit    = HPC credit + SA credit
#   credit points   = total credit x the grade's nationalCreditLevel (Grade 3/4/5: 0.6/0.8/1.0,
#                     Grade 6/7/8: 1.33/1.67/2.0)
#   marks           = round(total credit / (hpcMaxCredits + saCredits) x 100)
# and the Total row is the sum of the rows (credit points too: rounded per row, then added, as PARAKH does - so it
# can differ by 0.01 from total credit x the factor). Example (Middle, Bagless days, Beginner/Proficient/Beginner):
# 0.59 + 1.18 + 0.59 = 2.36 credits, 2.36 / 5.33 = 44 marks.
# PARAKH's own page lists Vocational/Skill Education under the key "vocational-skill-education" but keeps its credits
# under "skill-education-middle", so the subject earns 0 there; SKILL_KEY_FIX (above) decides whether the app follows it.
# ---------------------------------------------------------------------------

def verify_tables(stage: str, tables: Dict[str, Any], grade_code: str) -> List[str]:
    """Problems with a built table3 (Preparatory, Middle): each row's total and points, and the Total row against the
    sum of the rows. [] when it all adds up."""
    level = next((g["nationalCreditLevel"] for g in TABLES[stage]["grades"] if grade_code in g["classCodes"]), 0)
    rows = [r for r in tables.get("table3") or [] if r and r[0] != "Total"]
    total = next((r for r in tables.get("table3") or [] if r and r[0] == "Total"), None)
    out = []
    for name, hpc, sa, earned, points, _marks in rows:
        if abs(_round2(float(hpc) + float(sa)) - float(earned)) > 0.005:
            out.append(f"{name}: total credit {earned} is not HPC {hpc} + SA {sa}")
        if abs(_round2(float(earned) * level) - float(points)) > 0.005:
            out.append(f"{name}: credit points {points} are not {earned} x {level}")
    if total is not None:
        for col, label in ((1, "HPC credit"), (2, "SA credit"), (3, "total credit"), (4, "credit points"), (5, "marks")):
            summed = sum(_js_round(float(r[col]) * 100) for r in rows) / 100
            if abs(summed - float(total[col])) > 0.005:
                out.append(f"Total {label} {total[col]} is not the sum of the rows ({js_str(summed)})")
    return out


# ---------------------------------------------------------------------------
# Foundational stage: credits come only from the Part C levels (no summative marks)
# ---------------------------------------------------------------------------

LEVELS = ["Advance", "Proficient", "Beginner"]     # index in Part C awr/sen/cre lists


def js_fixed2(x: float) -> str:
    """JS x.toFixed(2)."""
    return str(Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _jsx_label(text: str, strong: Any) -> Dict[str, Any]:
    """How the page's <>{label}/<strong>{n}</strong></> cell comes out after JSON.stringify."""
    return {"key": None, "ref": None, "props": {"children": [text, "/", {"type": "strong", "key": None, "ref": None,
                                                                          "props": {"children": strong}}]}}


def build_foundational(part_c: Dict[str, Any], grade_code: str, stored: Dict[str, Any]) -> Dict[str, Any]:
    """basic, credit and table2 exactly as the Foundational hpc-credit page saves them."""
    t = TABLES["foundational"]
    per_level = t["credit_per_level"]
    max_credit = _round2(3 * per_level["Advance"])
    level = next((g["nationalCreditLevel"] for g in t["grades"] if grade_code in g["classCodes"]), 0)

    def ability_level(lists: Any, domain: str) -> str:
        for i, entry in enumerate((lists or [])[:3]):
            if domain in {x.strip() for x in str(entry or "").split(",") if x.strip()}:
                return LEVELS[i]
        return ""

    rows, table2 = [], []
    for subject, domain in zip(t["subjects"], t["domains"]):
        a, r, c = (ability_level(part_c.get(k), domain) for k in ("awr", "sen", "cre"))
        earned = _round2(sum(per_level.get(x, 0) for x in (a, r, c) if x))
        points = _round2(earned * level)
        marks = _js_round(earned / max_credit * 100) if max_credit > 0 else 0
        rows.append((earned, points, marks))
        table2.append([SUBJECT_LABELS[subject["key"]], *(RATING_LABELS[x] if x else "" for x in (a, r, c)),
                       js_fixed2(earned), js_fixed2(points), marks])
    total = lambda i: sum(_js_round(row[i] * 100) for row in rows) / 100
    table2.append(["Total", "", "", "", js_fixed2(total(0)), js_fixed2(total(1)), sum(row[2] for row in rows)])

    old = stored.get("credit") if isinstance(stored.get("credit"), list) else None
    credit = []
    for i, subject in enumerate(t["subjects"]):
        base = subject["defaultCredits"]
        extra = ""
        if old and i < len(old):
            old_level = _number(old[i][1]) if len(old[i]) > 1 else 0
            old_level = old_level if old_level == old_level else 0
            value = _number(old[i][3]) if len(old[i]) > 3 else 0
            value = value if value == value else 0
            if old_level != level and old_level > 0:
                value = value / old_level * level
            extra = js_str(_round2(value)) if value else ""
        credit.append([js_num(base), js_num(level), js_str(_round2(base * level)), extra])

    basic = [[_jsx_label(g["label"], g["schoolPassed"]), js_num(g["nationalCreditLevel"]), g["creditPoints"],
              js_num(max_credit)] for g in t["grades"]]
    return {"basic": basic, "credit": credit, "table2": table2}
