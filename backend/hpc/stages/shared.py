"""
Parts that work the same way in the Preparatory and Middle stages:
A1 (general info + attendance), C (subject assessment) and D (HPC Credit).
"""
import copy
import json
from pathlib import Path
from typing import Any, Dict, List

from backend.hpc import credit
from backend.hpc.credit import _round2, js_num
from backend.hpc.fields import Field, series
from backend.hpc.stages.common import GUARDIAN, MONTHS, RATING_1_3, Lookups, Part, StudentContext, clean, required

LIMITS = json.loads((Path(__file__).parent.parent / "reference" / "field_limits.json").read_text())


# ---------------------------------------------------------------------------
# Part A1 - General information, attendance, interests (filled by the teacher)
# ---------------------------------------------------------------------------

def blank_a1():
    return {"basic": [""] * 11, "gen": [""] * 26,
            "attn": {"1": [""] * 13, "2": [""] * 13, "3": [""] * 13, "4": ""}, "ints": [], "spec": ""}


def make_part_a1(stage_key: str) -> Part:
    """Foundational stores blank attendance as 0; the other stages keep blanks (see finish_a1)."""
    lim = LIMITS[stage_key]["a1"]
    zero_blanks = stage_key == "foundational"

    def fields(lk: Lookups) -> List[Field]:
        return [
            Field("a1_mother_tongue", "Mother Tongue", ("gen", 16), max_len=lim["mother_tongue"], required=True),
            Field("a1_medium", "Medium of Instruction", ("gen", 17), "choice", lk.options(lk.medium), required=True),
            Field("a1_rural_urban", "Rural/Urban", ("gen", 18), "choice", lk.options(lk.location), required=True),
            Field("a1_guardian_relation", "Mother/Father/Guardian", ("gen", 23), "choice", GUARDIAN, required=True),
            Field("a1_guardian_name", "Mother/Father/Guardian Name", ("gen", 24), max_len=lim["guardian_name"], required=True),
            Field("a1_udid", "UDID (if any)", ("gen", 21), max_len=lim["udid"]),
            *series("a1_working", "Working days", ("attn", "1"), MONTHS, kind="int"),
            *series("a1_present", "Days present", ("attn", "2"), MONTHS, kind="int"),
            Field("a1_low_attendance", "If attendance is low, reasons", ("attn", "4"), max_len=lim["low_attend"]),
            Field("a1_interests", "Interests (comma separated)", ("ints",), "multi", lk.options(lk.interests)),
            Field("a1_other_interest", "Other interest (specify)", ("spec",), max_len=lim["other_interest"]),
        ]

    return Part("A1", "part_a1", "Part A1 - General Info & Attendance", blank_a1, fields,
                lambda fd, ctx: finish_a1(fd, ctx, zero_blanks))


def finish_a1(fd: Dict[str, Any], ctx: StudentContext, zero_blanks: bool = False):
    """What the A1 page does on Continue: fill portal-owned values, compute attendance, check required fields."""
    stu, sch, lk = ctx.stu, ctx.record.get("sch_info") or {}, ctx.lookups
    fd["basic"] = [stu.get("student_name", ""), stu.get("std_apaar_id", ""), stu.get("teacher_code", ""),
                   sch.get("school_name", ""), sch.get("school_city", ""), sch.get("school_brc", ""),
                   sch.get("school_crc", ""), sch.get("state_name", ""), sch.get("school_pincode", ""),
                   sch.get("school_udise", ""), sch.get("district_name", "")]
    gen = fd["gen"]
    gen[1] = ctx.record.get("std_reg_id", "")
    gen[2] = ctx.grade_code
    gen[3] = lk.section_name(stu.get("section_id")) or gen[3]
    gen[4] = stu.get("dob", "")
    gen[22] = stu.get("school_admission_number", "")
    gen[25] = stu.get("gender", "")
    gen[16], gen[24] = clean(gen[16]), clean(gen[24])
    gen[23] = gen[23] or "FATHER"                 # the page pre-selects Father

    errors: List[str] = []
    att = fd["attn"]
    worked = [_whole(v, zero_blanks) for v in att["1"][:12]]
    present = [_whole(v, zero_blanks) for v in att["2"][:12]]
    month_percent = _month_percent_foundational if zero_blanks else _month_percent
    for month, w, p in zip(MONTHS, worked, present):
        if w != "" and p != "" and p > w:
            errors.append(f"Attendance {month}: days present ({p}) is more than working days ({w})")
    total_w = sum(v for v in worked if v != "")
    total_p = sum(v for v in present if v != "")
    att["1"] = worked + [total_w]
    att["2"] = present + [total_p]
    att["3"] = [month_percent(w, p) for w, p in zip(worked, present)] + \
               [js_num(_round2(total_p / total_w * 100)) if total_w else 0]
    gen[19] = "" if total_w == 0 and total_p == 0 else str(max(total_w - total_p, 0))   # days absent

    for label, value in (("Grade", gen[2]), ("HPC Login ID", gen[1]), ("Mother Tongue", gen[16]),
                         ("Medium of Instruction", gen[17]), ("Rural/Urban", gen[18]),
                         ("Mother/Father/Guardian", gen[23]), ("Mother/Father/Guardian Name", gen[24])):
        required(errors, value, label)

    medium_id = next((m["id"] for m in lk.medium if m["catg_item_code"] == gen[17]), None)
    location_id = next((l["id"] for l in lk.location if l["catg_item_code"] == gen[18]), None)
    return {"cond_class": gen[2], "hpc_id": str(ctx.record.get("hpc_id")),
            "med_inst": medium_id, "location_id": location_id}, errors


def _whole(value: Any, zero_blanks: bool = False):
    text = str(value if value is not None else "").strip()
    return int(float(text)) if text else (0 if zero_blanks else "")


def _month_percent_foundational(worked, present):
    """The Foundational page's rule: no working days means 0%."""
    return 0 if worked == 0 else js_num(_round2(present / worked * 100))


def _month_percent(worked, present):
    """Same rule as the page's monthly attendance % cell."""
    if worked == 0 and present == 0:
        return 0
    if worked == "" or present == "":
        return ""
    if present == 0:
        return 0
    return js_num(_round2(present / worked * 100)) if worked else ""


# ---------------------------------------------------------------------------
# Part C - per subject: Awareness / Sensitivity / Creativity (1-3) + remark
# ---------------------------------------------------------------------------

def make_part_c(stage_key: str, domains: List[str], subjects: List[str]) -> Part:
    remark_limit = LIMITS[stage_key]["c"]["notes"]

    def blank():
        out = {d: ["", "", "", ""] for d in domains}
        out["overall"] = ["", "", "", ""]
        return out

    def fields(lk: Lookups) -> List[Field]:
        out = []
        for d, name in zip(domains, subjects):
            out += [Field(f"c_{d}_awareness", f"{name}: Awareness", (d, 0), "choice", RATING_1_3, required=True),
                    Field(f"c_{d}_sensitivity", f"{name}: Sensitivity", (d, 1), "choice", RATING_1_3, required=True),
                    Field(f"c_{d}_creativity", f"{name}: Creativity", (d, 2), "choice", RATING_1_3, required=True),
                    Field(f"c_{d}_remark", f"{name}: Remark", (d, 3), max_len=remark_limit, required=True)]
        return out

    def finish(fd, ctx: StudentContext):
        return {"state_code_internal": ctx.lookups.portal.state}, []

    return Part("C", "part_c", "Part C - Subject Assessment", blank, fields, finish)


# ---------------------------------------------------------------------------
# Part D - HPC Credit: summative marks + declaration; credit tables are calculated
# ---------------------------------------------------------------------------

def make_part_d(stage_key: str, domains: List[str]) -> Part:
    subjects = credit.subjects(stage_key)

    def blank():
        return {"basic": copy.deepcopy(credit.TABLES[stage_key]["display_rows"]),
                "credit": [["", ""] for _ in subjects], "declaration": False}

    def fields(lk: Lookups) -> List[Field]:
        out = []
        for i, s in enumerate(subjects):
            if credit.sa_applicable(stage_key, i):
                name = credit.SUBJECT_LABELS[s["key"]]
                out += [Field(f"d_{i + 1}_max", f"{name}: summative max marks", ("credit", i, 0), required=True),
                        Field(f"d_{i + 1}_obtained", f"{name}: summative marks obtained", ("credit", i, 1), required=True)]
        out.append(Field("d_declaration", "Declaration accepted (Yes/No)", ("declaration",), "choice",
                         {"Yes": True, "No": False}, required=True, blank=False))
        return out

    def finish(fd, ctx: StudentContext):
        errors = []
        fd["basic"] = copy.deepcopy(credit.TABLES[stage_key]["display_rows"])
        for i, s in enumerate(subjects):
            if not credit.sa_applicable(stage_key, i):
                fd["credit"][i] = ["", ""]
                continue
            mx, got = (str(v).strip() for v in fd["credit"][i])
            name = credit.SUBJECT_LABELS[s["key"]]
            try:
                mx_f, got_f = float(mx), float(got)
            except ValueError:
                errors.append(f"{name}: summative marks must be numbers")
                continue
            if mx_f <= 0 or got_f < 0:
                errors.append(f"{name}: summative marks must be positive")
            elif got_f > mx_f:
                errors.append(f"{name}: marks obtained ({got}) are more than max marks ({mx})")
        if fd.get("declaration") is not True:
            errors.append("the declaration must be accepted (Yes)")
        fd.update(credit.build_tables(stage_key, ctx.parts.get("part_c") or {}, domains, fd["credit"], ctx.grade_code))
        return {}, errors

    return Part("D", "hpc_credit", "HPC Credit", blank, fields, finish)
