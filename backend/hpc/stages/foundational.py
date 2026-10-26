"""
Foundational stage (Balvatika 1-3, Grades 1-2): parts A1, A2, B, C, D (HPC Credit).

Templates, field positions, limits and checks mirror the portal's own page code
(/en/hpc/foundational-stage/<id>/part-...), as of 2026-10-25. This stage differs most:
Part C rates six developmental domains by placing each domain at a level per ability,
and HPC Credit is calculated from those levels only (no summative marks).
"""
import copy
from typing import List

from backend.hpc import credit
from backend.hpc.fields import Field
from backend.hpc.stages.activity import filled, make_finish_b, rubric_ok
from backend.hpc.stages.activity_grid import GridSpec
from backend.hpc.stages.common import Lookups, Part, StudentContext
from backend.hpc.stages.shared import LIMITS, make_part_a1

LIM = LIMITS["foundational"]

DOMAINS = ["FSDOM1", "FSDOM2", "FSDOM3", "FSDOM4", "FSDOM5", "FSDOM51"]
SUBJECTS = ["Physical Development", "Socio-emotional & Ethical Development", "Cognitive Development",
            "Language & Literacy Development", "Aesthetic & Cultural Development", "Positive Learning Habits"]
LEVEL_INDEX = {"Advanced": 0, "Proficient": 1, "Beginner": 2}     # Sky / Mountain / Stream


# ---------------------------------------------------------------------------
# Part A2 - All about me (filled by the student)
# ---------------------------------------------------------------------------

def blank_a2():
    return {"pa_2": [""] * 11, "myf": [""] * 6}


def fields_a2(lk: Lookups) -> List[Field]:
    lim = LIM["a2"]
    avatars = {f"avat_{i:02d}": f"avat_{i:02d}" for i in range(1, 21)}
    out = [Field("a2_age", "I am ... years old", ("pa_2", 0), max_len=lim["age"]),
           Field("a2_avatar", "My avatar (avat_01 ... avat_20)", ("pa_2", 2), "choice", avatars),
           Field("a2_live_in", "I live in", ("pa_2", 3), max_len=lim["liveIn"])]
    out += [Field(f"a2_friend_{i}", f"My friend {i}", ("pa_2", 4 + i), max_len=lim["friends"]) for i in range(1, 6)]
    out.append(Field("a2_grow_up", "When I grow up I want to be", ("pa_2", 10), max_len=lim["growUp"]))
    for i, thing in enumerate(["colour", "flower", "food", "sport", "animal", "subject"]):
        out.append(Field(f"a2_fav_{thing}", f"My favourite {thing}", ("myf", i), max_len=lim["favorites"]))
    return out


# ---------------------------------------------------------------------------
# Part B - one activity from the Activity Bank, rubric, self and peer assessment
# ---------------------------------------------------------------------------

YES_NO_DK = {"Yes": 0, "No": 1, "Don't know": 2}
NEEDED = {"Classmates": 0, "Teachers": 1, "Books": 2, "Computer": 3, "None": 4}
RESOURCES = {"Books/Magazines": 0, "Newspaper": 1, "Toys/Games/Sports": 2, "Phone/Computer": 3, "Internet": 4,
             "Radio": 5, "Broadcast": 6, "TV": 7, "Resources for CWD": 8}


def blank_activity():
    return {"domain": [], "gl": [], "cpt": [], "desc": ["", ""], "img": [""] * 4, "awr": [""] * 4,
            "sen": [""] * 4, "cre": [""] * 4, "tf": [], "tfob": "", "sa": [0] * 11, "pa": [0] * 11,
            "lt": [0] * 9 + [""], "cmt": "", "prof": ["", "", ""], "act_bank_id": None}


def fields_b(lk: Lookups) -> List[Field]:
    """The student's own answers. The activity and levels per domain come from the dashboard grid."""
    lim = LIM["b"]
    dt = lambda *p: (0, "dt", *p)
    out = [
        Field("b_observation", "Observational notes", dt("tfob"), max_len=lim["observational_notes"]),
    ]
    for who, key, required in (("Self", "sa", True), ("Peer", "pa", False)):
        subject = "I" if who == "Self" else "My friend"
        out += [
            Field(f"b_{key}_liked", f"{who}: {subject} liked doing this work", dt(key), "onehot", YES_NO_DK,
                  required=required, span=(0, 3)),
            Field(f"b_{key}_easy", f"{who}: {subject} found this work easy", dt(key), "onehot", YES_NO_DK,
                  required=required, span=(3, 3)),
            Field(f"b_{key}_needed", f"{who}: to do this work {subject.lower()} needed (comma separated)", dt(key),
                  "flags", NEEDED, span=(6, 5)),
        ]
    out += [Field("b_resources", "Learning resources used (comma separated)", dt("lt"), "flags", RESOURCES, span=(0, 9)),
            Field("b_resources_other", "Other resource", dt("lt", 9), max_len=lim["other_resource"]),
            Field("b_comments", "Comments / remarks", dt("cmt"), max_len=lim["comments"])]
    return out


def prepare_activity(dt) -> None:
    """What the page derives itself: the 'needed' None option and the teacher-feedback levels (prof)."""
    for key in ("sa", "pa"):
        slots = (list(dt.get(key) or []) + [0] * 11)[:11]
        if slots[10] == 1:                       # "None" clears the other four choices
            slots[6:10] = [None] * 4
        else:
            slots[6:10] = [0 if v is None else v for v in slots[6:10]]
            slots[10] = 0
        dt[key] = slots
    prof = ["", "", ""]
    for ability, code in (("awr", "A"), ("sen", "S"), ("cre", "C")):
        level = str(dt[ability][3]).strip()
        idx = {"advance": 0, "proficient": 1, "beginner": 2}.get(level)
        if idx is not None:
            prof[idx] = f"{prof[idx]},{code}" if prof[idx] else code
    dt["prof"] = prof


def activity_complete(dt) -> bool:
    """The page's own 'finished activity' rule for Foundational."""
    sa = dt.get("sa") or []
    if not (dt.get("domain") and dt.get("gl") and dt.get("cpt") and filled(dt["desc"][0]) and filled(dt["desc"][1])):
        return False
    if not all(rubric_ok(dt[k]) for k in ("awr", "sen", "cre")):
        return False
    if not (any(v == 1 for v in sa[0:3]) and any(v == 1 for v in sa[3:6])):
        return False
    placed = {c.strip() for entry in dt.get("prof", [])[:3] for c in str(entry or "").split(",") if c.strip()}
    return {"A", "S", "C"} <= placed


finish_b = make_finish_b(DOMAINS, blank_activity, ["domain", "awr", "sen", "cre", "tfob", "sa", "pa", "lt", "cmt"],
                         from_bank=lambda content: {}, complete=activity_complete, prepare=prepare_activity)

ACTIVITY_GRID = GridSpec(blank=blank_activity, shared=("tfob", "sa", "pa", "lt", "cmt"))


# ---------------------------------------------------------------------------
# Part C - per domain: a level for each ability, plus a key performance descriptor
# ---------------------------------------------------------------------------

def blank_c():
    return {"desc": [""] * 6, "awr": ["", "", ""], "sen": ["", "", ""], "cre": ["", "", ""]}


def fields_c(lk: Lookups) -> List[Field]:
    out = []
    for i, (domain, name) in enumerate(zip(DOMAINS, SUBJECTS)):
        for ability, label in (("awr", "Awareness"), ("sen", "Sensitivity"), ("cre", "Creativity")):
            out.append(Field(f"c_{domain}_{ability}", f"{name}: {label} level", (ability,), "inlist", LEVEL_INDEX,
                             required=True, member=domain))
        out.append(Field(f"c_{domain}_descriptor", f"{name}: key performance descriptor", ("desc", i),
                         max_len=LIM["c"]["performance_descriptors"], required=True))
    return out


# ---------------------------------------------------------------------------
# Part D - HPC Credit: only the declaration is entered; everything else is calculated
# ---------------------------------------------------------------------------

def blank_d():
    return {"basic": [], "credit": [], "table2": [], "declaration": False}


def fields_d(lk: Lookups) -> List[Field]:
    return [Field("d_declaration", "Declaration accepted (Yes/No)", ("declaration",), "choice",
                  {"Yes": True, "No": False}, required=True, blank=False)]


def finish_d(fd, ctx: StudentContext):
    stored = copy.deepcopy(fd)
    tables = credit.build_foundational(ctx.parts.get("part_c") or {}, ctx.grade_code, stored)
    declaration = fd.get("declaration") is True
    fd.clear()
    fd.update({**tables, "declaration": declaration})
    return {}, ([] if declaration else ["the declaration must be accepted (Yes)"])


PARTS = [
    make_part_a1("foundational"),
    Part("A2", "part_a2", "Part A2 - All About Me", blank_a2, fields_a2),
    Part("B", "part_b", "Part B - Activity", lambda: [{"nm": "", "dt": blank_activity()}], fields_b, finish_b,
         as_json_string=False),
    Part("C", "part_c", "Part C - Domain Assessment", blank_c, fields_c),
    Part("D", "hpc_credit", "HPC Credit", blank_d, fields_d, finish_d),
]
