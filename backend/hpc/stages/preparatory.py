"""
Preparatory stage (Grades 3-5): parts A1, A2, A3, B, C, D (HPC Credit).

Templates, field positions, limits and checks mirror the portal's own page code
(/en/hpc/preparatory-stage/<id>/part-...), as of 2026-10-25.
"""
from typing import List

from backend.hpc import notes
from backend.hpc.suggestions import stock
from backend.hpc.fields import Field
from backend.hpc.stages.activity import filled, make_finish_b, rubric_ok
from backend.hpc.stages.activity_grid import GridSpec
from backend.hpc.stages.common import Lookups, Part, record_age, record_name, required
from backend.hpc.stages.shared import LIMITS, make_part_a1, make_part_c, make_part_d

LIM = LIMITS["preparatory"]

# Subjects in the portal's order (Part B/C domain keys).
DOMAINS = ["PSLS1", "PSLS2", "PSLS3", "PSLS4", "PSLS5", "PSLS6", "PSLS7"]
SUBJECTS = ["Language 1 (R1)", "Language 2 (R2)", "Mathematics", "The World Around Us",
            "Art Education", "Physical Education", "Other Learning Activities"]
FEEL = {"Yes": "1", "Sometimes": "2", "No": "3", "Not sure": "4"}


# ---------------------------------------------------------------------------
# Part A2 - All about me (filled by the student)
# ---------------------------------------------------------------------------

def blank_a2():
    return {"gen": ["", "", ""], "things_about_me": [""] * 5, "favorites": [""] * 3,
            "grow_up": [""], "thing_learn": [""] * 3, "idol": [""]}


# A7: the hand drawing's fingers, thumb first (PARAKH's img_pre_hand_things_about_me: things_about_me[0..4])
HAND = ["I am good at", "I am not so good at", "I would like to improve my skill of", "I like to", "I don't like to"]


def finish_a2(fd, ctx):
    """A1: name and age always as PARAKH's record has them."""
    lim = LIM["a2"]
    fd["gen"][0] = record_name(ctx.stu, lim["name"]) or fd["gen"][0]
    fd["gen"][1] = record_age(ctx.stu) or fd["gen"][1]
    return {}, []


def fields_a2(lk: Lookups) -> List[Field]:
    lim = LIM["a2"]
    return [
        Field("a2_name", "My name is", ("gen", 0), max_len=lim["name"]),
        Field("a2_age", "I am ... years old", ("gen", 1), max_len=lim["age"]),
        *[Field(f"a2_about_{i + 1}", f"Things about me: {finger}", ("things_about_me", i), max_len=lim[f"hands_{i}"])
          for i, finger in enumerate(HAND)],
        Field("a2_fav_food", "My favourite food", ("favorites", 0), max_len=lim["favorites"]),
        Field("a2_fav_games", "My favourite games", ("favorites", 1), max_len=lim["favorites"]),
        Field("a2_fav_festival", "My favourite festival", ("favorites", 2), max_len=lim["favorites"]),
        Field("a2_grow_up", "When I grow up I want to be", ("grow_up", 0), max_len=lim["growUp"]),
        *[Field(f"a2_learn_{i + 1}", f"Thing I want to learn {i + 1}", ("thing_learn", i), max_len=lim["friends"])
          for i in range(3)],
        Field("a2_idol", "One person who inspires me", ("idol", 0), max_len=lim["myIdol"]),
    ]


# ---------------------------------------------------------------------------
# Part A3 - How I feel (student), peer feedback, parent feedback
# ---------------------------------------------------------------------------

FEEL_QUESTIONS = ["I can talk about how I feel", "I can calm myself", "I understand how my friends feel",
                  "I respect others' views", "I help friends make up after a fight",
                  "I can make a sad friend feel better", "I do well at school"]
PEER_QUESTIONS = ["Friend talks about feelings", "Friend calms self", "Friend understands others",
                  "Friend respects views", "Friend helps others make up", "Friend makes sad people feel better"]
PARENT_QUESTIONS = ["Finds school welcoming and safe", "Participates in activities", "Finds curriculum difficult",
                    "Making good progress", "Gets needed support from school", "Talks about feelings",
                    "Calms self", "Understands friends' feelings", "Respects others' views",
                    "Helps friends make up", "Makes sad people feel better"]
RESOURCES = {"Books/Magazines": 1, "Newspaper": 2, "Toys/Games/Sports": 3, "Phone/Computer": 4,
             "Internet": 5, "Radio": 6, "Broadcast": 7, "TV": 8, "Resources for CWD": 9}
SUPPORT = {"Oral communication": 1, "Interest in reading": 2, "Numbers and Math": 3, "Self-confidence": 4,
           "Working with children": 5, "Working independently": 6, "Other subject area": 7}


def blank_a3():
    return {"feel": [""] * 7, "pr1": [""] * 8, "pr2": [""] * 8, "mtr": [], "mtr_oth": "",
            "better": [""] * 11, "supp": [], "supp_oth": ""}


def fields_a3(lk: Lookups) -> List[Field]:
    lim = LIM["a3"]
    out = [Field(f"a3_feel_{i + 1}", f"How I feel: {q}", ("feel", i), "choice", FEEL, required=True)
           for i, q in enumerate(FEEL_QUESTIONS)]
    for n in (1, 2):
        out += [Field(f"a3_peer{n}_name", f"Peer {n}: my name", (f"pr{n}", 0), max_len=lim["myName"]),
                Field(f"a3_peer{n}_friend", f"Peer {n}: friend's name", (f"pr{n}", 1), max_len=lim["myFriendName"])]
        out += [Field(f"a3_peer{n}_{i + 1}", f"Peer {n}: {q}", (f"pr{n}", i + 2), "choice", FEEL)
                for i, q in enumerate(PEER_QUESTIONS)]
    out += [Field("a3_resources", "Resources at home (comma separated)", ("mtr",), "multi", RESOURCES),
            Field("a3_resources_other", "Other resources", ("mtr_oth",), max_len=lim["childMatters"])]
    out += [Field(f"a3_parent_{i + 1}", f"Parent: {q}", ("better", i), "choice", FEEL)
            for i, q in enumerate(PARENT_QUESTIONS)]
    out += [Field("a3_support", "Child needs support with (comma separated)", ("supp",), "multi", SUPPORT),
            Field("a3_support_other", "Support: other subject area", ("supp_oth",), max_len=lim["otherSubjectArea"])]
    return out


def finish_a3(fd, ctx):
    """A8: on each peer sheet "My Friend's Name" is the student the sheet is about (PARAKH's record); "My Name" is
    the classmate's and stays as typed. 'Other subject area' needs its own words."""
    errors = []
    for i, q in enumerate(FEEL_QUESTIONS):
        required(errors, fd["feel"][i], f"How I feel: {q}")
    for sheet in ("pr1", "pr2"):
        if any(str(v or "").strip() for v in fd[sheet][2:]):            # a sheet that was filled in
            fd[sheet][1] = record_name(ctx.stu, LIM["a3"]["myFriendName"]) or fd[sheet][1]
    if SUPPORT["Other subject area"] in (fd.get("supp") or []) and not str(fd.get("supp_oth") or "").strip():
        errors.append("'Other subject area' is ticked: write which one in 'Support: other subject area'")
    return {}, errors


# ---------------------------------------------------------------------------
# Part B - one activity from the Activity Bank, with rubric levels and self-assessment
# ---------------------------------------------------------------------------

SELF_ASSESS = {"Yes": 1, "No": 2, "Not sure": 3}
SELF_QUESTIONS = ["I followed my teacher's directions", "I liked doing this work", "I asked for help",
                  "I tried my best", "I am proud of my work", "I want to do this task again",
                  "I liked working with classmates", "Classmates helped me"]


def blank_activity():
    return {"domain": [], "gl": [], "cpt": [], "desc": ["", ""], "img": [""] * 4, "awr": [""] * 4,
            "sen": [""] * 4, "cre": [""] * 4, "tf": [""] * 3, "tfob": "", "lp": ["", ""], "sa": [0] * 8,
            "act_bank_id": None}


def fields_b(lk: Lookups) -> List[Field]:
    """The student's own answers. The activity and levels per subject come from the dashboard grid."""
    lim = LIM["b"]
    return [
        Field("b_observation", "Observational notes", (0, "dt", "tfob"), max_len=lim["observational_notes"]),
        Field("b_challenges", "What challenges did the learner face?", (0, "dt", "lp", 0), max_len=lim["learner_performed"]),
        Field("b_overcome", "How were the challenges overcome?", (0, "dt", "lp", 1), max_len=lim["learner_performed"]),
        *[Field(f"b_self_{i + 1}", f"Self-assessment: {q}", (0, "dt", "sa", i), "choice", SELF_ASSESS,
                required=True, blank=0) for i, q in enumerate(SELF_QUESTIONS)],
    ]


def activity_complete(dt) -> bool:
    """The page's own 'finished activity' rule."""
    return (bool(dt.get("domain")) and bool(dt.get("gl")) and bool(dt.get("cpt"))
            and filled(dt["desc"][0]) and filled(dt["desc"][1])
            and all(rubric_ok(dt[k]) for k in ("awr", "sen", "cre"))
            and all(int(v or 0) != 0 for v in dt["sa"]))


finish_b = make_finish_b(DOMAINS, blank_activity, ["domain", "awr", "sen", "cre", "tf", "tfob", "lp", "sa"],
                         from_bank=lambda content: {}, complete=activity_complete)


def feedback_from_levels(dt) -> None:
    """Teacher feedback (1-3) follows the rubric levels chosen in the grid."""
    to_tf = {"beginner": "1", "proficient": "2", "advance": "3"}
    dt["tf"] = [to_tf.get(str(dt[k][3]).strip(), "") for k in ("awr", "sen", "cre")]


def write_teacher(dt, name) -> None:
    """B4: an activity's own observation from its levels; challenges and how they were overcome are left for the
    teacher (nothing to work them out from)."""
    dt["tfob"] = notes.activity_observation(dt, name, LIM["b"]["observational_notes"])
    dt["lp"] = ["", ""]


ACTIVITY_GRID = GridSpec(blank=blank_activity, shared=("tfob", "lp", "sa"), derive=feedback_from_levels,
                         teacher=("tfob", "lp"), write_teacher=write_teacher,
                         typed_by_teacher=lambda dt: not (stock("b_observation", dt.get("tfob"))
                                                          and stock("b_challenges", (dt.get("lp") or ["", ""])[0])
                                                          and stock("b_overcome", (list(dt.get("lp") or []) + ["", ""])[1])))


PARTS = [
    make_part_a1("preparatory"),
    Part("A2", "part_a2", "Part A2 - All About Me", blank_a2, fields_a2, finish_a2),
    Part("A3", "part_a3", "Part A3 - Feelings, Peer & Parent", blank_a3, fields_a3, finish_a3),
    Part("B", "part_b", "Part B - Activity", lambda: [{"nm": "", "dt": blank_activity()}], fields_b, finish_b,
         as_json_string=False),
    make_part_c("preparatory", DOMAINS, SUBJECTS),
    make_part_d("preparatory", DOMAINS),
]
