"""
Middle stage (Grades 6-8): parts A1, A2, A3, A4, B, C, D (HPC Credit).

Templates, field positions, limits and checks mirror the portal's own page code
(/en/hpc/middle-stage/<id>/part-...), as of 2026-10-25.
"""
from typing import List

from backend.hpc import notes
from backend.hpc.suggestions import stock
from backend.hpc.fields import Field
from backend.hpc.stages.activity import filled, make_finish_b, rubric_ok
from backend.hpc.stages.activity_grid import GridSpec
from backend.hpc.stages.common import Lookups, Part
from backend.hpc.stages.shared import LIMITS, make_part_a1, make_part_c, make_part_d

LIM = LIMITS["middle"]

DOMAINS = ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"]
SUBJECTS = ["Language 1 (R1)", "Language 2 (R2)", "Language 3 (R3)", "Mathematics", "Science",
            "Social Science", "Art Education", "Physical Education", "Skill Education",
            "Other Learning Activities", "Bagless Days"]
YES_NO = {"Yes": "1", "Sometimes": "2", "No": "3", "Not sure": "4"}


# ---------------------------------------------------------------------------
# Part A2 - All about me, goals, learnings (filled by the student)
# ---------------------------------------------------------------------------

def blank_a2():
    return {"allAboutMe": [""] * 10, "academicGoal": [""] * 4, "personalGoal": [""] * 4,
            "learningAtSchool": [""] * 3, "learningOutsideSchool": [""] * 3, "teacher": ["", ""]}


def fields_a2(lk: Lookups) -> List[Field]:
    lim = LIM["a2"]
    about = [("I live with my", "liveWith"), ("We stay at", "stayAt"), ("I spend my free time doing", "freeTime"),
             ("I can do ... very well", "veryWell"), ("I am responsible", "responsible"),
             ("I could do better when it comes to", "doBetter"), ("I care about others. I show it by", "care"),
             ("I feel proud of myself when", "feelProud"), ("Name", "name"), ("Age", "age")]
    out = [Field(f"a2_about_{i + 1}", label, ("allAboutMe", i), max_len=lim[key]) for i, (label, key) in enumerate(about)]
    for goal, title in (("academicGoal", "Academic goal"), ("personalGoal", "Personal goal")):
        out += [Field(f"a2_{goal}_goal", f"{title}", (goal, 0), max_len=lim["goal"]),
                Field(f"a2_{goal}_reason", f"{title}: important because", (goal, 1), max_len=lim["reason"]),
                Field(f"a2_{goal}_step1", f"{title}: step 1", (goal, 2), max_len=lim["goalStep"]),
                Field(f"a2_{goal}_step2", f"{title}: step 2", (goal, 3), max_len=lim["goalStep"])]
    for key, title in (("learningAtSchool", "New thing learnt at school"),
                       ("learningOutsideSchool", "New thing learnt outside school")):
        out += [Field(f"a2_{key}_{i + 1}", f"{title} {i + 1}", (key, i), max_len=lim["language"]) for i in range(3)]
    out += [Field("a2_teacher_help", "I would like my teacher to help me with", ("teacher", 0), max_len=lim["teacher"]),
            Field("a2_teacher_know", "I would like my teacher to know", ("teacher", 1), max_len=lim["teacher"])]
    return out


# ---------------------------------------------------------------------------
# Part A3 - My ambition card (filled by the student)
# ---------------------------------------------------------------------------

def blank_a3():
    return {"basic": [""] * 6, "det": [""] * 5}


def fields_a3(lk: Lookups) -> List[Field]:
    lim = LIM["a3"]
    rows = [("basic", 1, "My ambition is", "myAmbition"), ("basic", 2, "I will achieve my ambition by", "ambitionAchieveBy"),
            ("basic", 3, "5 skills I need", "skillsNeeded"), ("basic", 4, "Subjects I need to focus on", "subjects"),
            ("basic", 5, "My habits need to be", "habits"), ("det", 0, "I will take guidance from", "guidanceFrom"),
            ("det", 1, "This person will help me by", "helpingPerson"), ("det", 2, "I will learn new", "newLearning"),
            ("det", 3, "I will feel", "myFeeling"), ("det", 4, "My parents will feel", "parentsFeeling")]
    return [Field(f"a3_{key}", label, (arr, i), max_len=lim[key]) for arr, i, label, key in rows]


def finish_a3(fd, ctx):
    fd["basic"][0] = ctx.stu.get("student_name", "")      # the page fills the student's name
    return {"hpc_id": str(ctx.record.get("hpc_id"))}, []


# ---------------------------------------------------------------------------
# Part A4 - Parent-teacher partnership (filled by the parent)
# ---------------------------------------------------------------------------

RESOURCES = {"Books/Magazines": 1, "Newspaper": 2, "Toys/Games/Sports": 3, "Phone/Computer": 4, "Internet": 5,
             "Radio": 6, "Broadcast": 7, "TV": 8, "Resources for CWD": 9}
UNDERSTAND = ["Motivated to learn new concepts", "Follows a schedule at home",
              "Finds curriculum difficult, needs support", "Making good progress"]
SUPPORT = {"Languages (R1/R2/R3)": 1, "Maths": 2, "Science": 3, "Social Science": 4,
           "Self-belief and self-reliance": 5, "Social skills and conflict resolution": 6,
           "Managing difficult emotions": 7, "Study skills / time management": 8,
           "Skill guidance / digital literacy": 9, "Any other": 10}


def blank_a4():
    return {"mtr": [], "mtr_oth": "", "understand": [""] * 4, "supp": [], "supp_oth": "", "supp_child": ""}


def fields_a4(lk: Lookups) -> List[Field]:
    lim = LIM["a4"]
    return [
        Field("a4_resources", "Resources at home (comma separated)", ("mtr",), "multi", RESOURCES),
        Field("a4_resources_other", "Other resources", ("mtr_oth",), max_len=lim["childMatters"]),
        *[Field(f"a4_understand_{i + 1}", f"Parent: {q}", ("understand", i), "choice", YES_NO)
          for i, q in enumerate(UNDERSTAND)],
        Field("a4_support", "At school my child needs support with (comma separated)", ("supp",), "multi", SUPPORT),
        Field("a4_support_other", "Support: any other", ("supp_oth",), max_len=lim["otherSubjectArea"]),
        Field("a4_home_support", "I will support my child at home by", ("supp_child",), max_len=lim["supp_child"]),
    ]


# ---------------------------------------------------------------------------
# Part B - one activity from the Activity Bank, with reflections and teacher assessment
# ---------------------------------------------------------------------------

APPROACHES = {"Art-Integrated": 1, "Sports-Integrated": 2, "Toy-Based": 3, "Technology-Integrated": 4, "Any Other": 5}
REFLECT = {"Yes": "1", "To an extent": "2", "No": "3", "Not sure": "4"}
GRID = {
    "mpa": {"Learnt something new": 1, "Attentive to detail": 2, "Understood the activity": 3,
            "Focused and engaged": 4, "Followed instructions": 5, "Found purpose and meaning": 6},
    "mps": {"Understood and expressed emotions": 1, "Motivated self and peers": 2, "Understood others' emotions": 3,
            "Sought and used support": 4, "Contributed individually or in group": 5, "Helped others": 6},
    "mpc": {"Curious to explore": 1, "Out of the box solutions": 2, "New ways to do the activity": 3,
            "Expressed creativity": 4, "Generated innovative ideas": 5, "Took calculated risks": 6},
}
STRENGTHS = {"Follow Instructions": 1, "Collaboration": 2, "Independent Work": 3, "Responsible": 4,
             "Communication": 5, "Creative": 6, "Solution-Focused Thinking": 7, "Concentration": 8,
             "Empathy": 9, "Organization & Prioritization": 10, "Any Other": 11}
BARRIERS = {"Lack of Attention": 1, "Peer Pressure": 2, "Lack of Motivation": 3, "Undefined Goals": 4,
            "Lack of Preparation": 5, "Domestic Issues": 6, "Inappropriate behavior in classroom": 7,
            "Severe illness or injury": 8, "None": 9, "Any Other": 10}
TEACHER_KEYS = ["domain", "activity", "awr", "sen", "cre", "slr", "mpa", "mps", "mpc", "ml", "pf",
                "ppa", "pps", "ppc", "ast", "bar", "spt", "any_other"]


def blank_activity():
    return {"domain": [], "gl": [], "cpt": [], "activity": [], "desc": ["", ""], "img": [""] * 4,
            "awr": [""] * 4, "sen": [""] * 4, "cre": [""] * 4, "slr": [""] * 3, "mpa": [], "mps": [], "mpc": [],
            "ml": [""] * 4, "pf": [""] * 6, "ppa": [], "pps": [], "ppc": [], "tf": [""] * 3, "ast": [], "bar": [],
            "spt": ["", ""], "any_other": ["", "", ""], "act_bank_id": None}


def fields_b(lk: Lookups) -> List[Field]:
    """The student's own answers. The activity and levels per subject come from the dashboard grid;
    the approach comes from the chosen activity."""
    lim = LIM["b"]
    dt = lambda *p: (0, "dt", *p)
    return [
        Field("b_reflect_awareness", "Self reflection: Awareness", dt("slr", 0), "choice", REFLECT, required=True),
        Field("b_reflect_sensitivity", "Self reflection: Sensitivity", dt("slr", 1), "choice", REFLECT, required=True),
        Field("b_reflect_creativity", "Self reflection: Creativity", dt("slr", 2), "choice", REFLECT, required=True),
        Field("b_grid_awareness", "Progress grid: Awareness (comma separated)", dt("mpa"), "multi", GRID["mpa"], required=True),
        Field("b_grid_sensitivity", "Progress grid: Sensitivity (comma separated)", dt("mps"), "multi", GRID["mps"], required=True),
        Field("b_grid_creativity", "Progress grid: Creativity (comma separated)", dt("mpc"), "multi", GRID["mpc"], required=True),
        Field("b_learnt", "By doing this activity, I learnt", dt("ml", 0), max_len=lim["learn"], required=True),
        Field("b_interesting", "The most interesting thing was", dt("ml", 1), max_len=lim["interesting_activity"], required=True),
        Field("b_need_practice", "I need practice on", dt("ml", 2), max_len=lim["practice"], required=True),
        Field("b_need_help", "I need help with", dt("ml", 3), max_len=lim["help"], required=True),
        Field("b_strengths", "Areas of strength (comma separated)", dt("ast"), "multi", STRENGTHS, required=True),
        Field("b_strengths_other", "Strength: any other", dt("any_other", 1), max_len=lim["other_text"]),
        Field("b_barriers", "Barriers to success (comma separated)", dt("bar"), "multi", BARRIERS, required=True),
        Field("b_barriers_other", "Barrier: any other", dt("any_other", 2), max_len=lim["other_text"]),
        Field("b_help_progress", "How I can help the student progress further", dt("spt", 0),
              max_len=lim["student_prog"], required=True),
        Field("b_observations", "Teacher's observations and recommendations", dt("spt", 1),
              max_len=lim["teacher_observation"]),
    ]


def prepare_activity(dt) -> None:
    """The page derives teacher feedback (tf) from the three rubric levels - note the inverted scale."""
    to_tf = {"beginner": "3", "proficient": "2", "advance": "1"}
    dt["tf"] = [to_tf.get(str(dt[k][3]).strip(), "") for k in ("awr", "sen", "cre")]


def activity_complete(dt) -> bool:
    """The page's own 'finished activity' rule (function iu in middle part-B)."""
    if not (dt.get("domain") and dt.get("gl") and dt.get("cpt")):
        return False
    if not all(dt.get(k) for k in ("activity", "ast", "bar")):
        return False
    other = dt.get("any_other") or ["", "", ""]
    if (5 in dt["activity"] and not filled(other[0])) or (11 in dt["ast"] and not filled(other[1])) \
            or (10 in dt["bar"] and not filled(other[2])):
        return False
    if not (all(filled(v) for v in dt["tf"]) and len(dt["tf"]) >= 3 and all(filled(v) for v in dt["desc"][:2])
            and filled(dt["spt"][0])):
        return False
    if not all(rubric_ok(dt[k]) for k in ("awr", "sen", "cre")):
        return False
    return (len(dt["slr"]) >= 3 and all(filled(v) for v in dt["slr"]) and len(dt["ml"]) >= 4
            and all(filled(v) for v in dt["ml"]) and all(dt.get(k) for k in ("mpa", "mps", "mpc")))


def from_bank(content) -> dict:
    """Extra fields the middle page copies from a bank activity."""
    return {"activity": list(content.get("approaches") or []), "any_other": [content.get("any-other") or "", "", ""]}


finish_b = make_finish_b(DOMAINS, blank_activity, TEACHER_KEYS, from_bank=from_bank,
                         complete=activity_complete, prepare=prepare_activity)

def write_teacher(dt, name) -> None:
    """B4, B7: "How I can help" from the activity's weakest ability, its level and the barriers ticked; the
    observation from its levels."""
    lim = LIM["b"]
    dt["spt"] = [notes.help_progress(dt, lim["student_prog"]), notes.activity_observation(dt, name, lim["teacher_observation"])]


ACTIVITY_GRID = GridSpec(blank=blank_activity, from_bank=from_bank, shared_any_other=(1, 2),
                shared=("slr", "mpa", "mps", "mpc", "ml", "pf", "ppa", "pps", "ppc", "ast", "bar", "spt"),
                teacher=("spt",), write_teacher=write_teacher,
                typed_by_teacher=lambda dt: not (stock("b_help_progress", (list(dt.get("spt") or []) + ["", ""])[0])
                                                 and stock("b_observations", (list(dt.get("spt") or []) + ["", ""])[1])))


PARTS = [
    make_part_a1("middle"),
    Part("A2", "part_a2", "Part A2 - All About Me & Goals", blank_a2, fields_a2,
         lambda fd, ctx: ({"state_code_internal": ctx.lookups.portal.state}, [])),
    Part("A3", "part_a3", "Part A3 - My Ambition", blank_a3, fields_a3, finish_a3),
    Part("A4", "part_a4", "Part A4 - Parent-Teacher Partnership", blank_a4, fields_a4),
    Part("B", "part_b", "Part B - Activity", lambda: [{"nm": "", "dt": blank_activity()}], fields_b, finish_b,
         as_json_string=False),
    make_part_c("middle", DOMAINS, SUBJECTS),
    make_part_d("middle", DOMAINS),
]
