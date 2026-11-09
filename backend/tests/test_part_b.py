"""Part B (P2): codes PARAKH cannot print go into the activity text (B1, B2), Middle's approach from the activity
(B3), the teacher's notes per activity instead of one copy everywhere (B4), help that follows the level and the
barriers, no random barriers (B7), and the duplicate detector."""
import copy

from backend.hpc import activity_texts, checks, notes, sync
from backend.hpc.stages import get_stage
from backend.hpc.suggestions import SUGGESTIONS, multi_mix
from backend.tests.conftest import blank_student, filled_row, make_lookups
from backend.tests.test_activity_grid import SUBJ, grid_row, lookups_with

MIDDLE = get_stage("MIDDLE")


# --- B1, B2: codes PARAKH has no list for --------------------------------------------------------------------

def test_b2_codes_parakh_cannot_print_are_written_into_the_activity_text():
    content = {"gl": ["R3CG1"], "cpt": ["R3C1.1"], "desc": ["Text for Activity: role-play.", "Q1"]}
    out = activity_texts.for_card("Middle", content, ["SL3"], known={"MCG2", "MC2.2"})
    assert out["desc"][0] == "Curricular Goal: R3CG1 | Competency: R3C1.1\nText for Activity: role-play."
    assert content["desc"][0] == "Text for Activity: role-play."                     # the library copy is untouched
    known = activity_texts.for_card("Middle", {"gl": ["MCG2"], "cpt": ["MC2.2"], "desc": ["x", ""]}, ["SM"],
                                    known={"MCG2", "MC2.2"})
    assert known["desc"][0] == "x"                                                    # PARAKH ticks these itself
    again = activity_texts.for_card("Middle", out, ["SL3"], known=set())
    assert again["desc"][0].count("Curricular Goal:") == 1                           # never written twice


def test_b1_b2_preparatory_pe_and_other_learning_show_their_competency():
    content = {"gl": ["PLBCG5"], "cpt": ["PLBC5.1"], "desc": ["Text for Activity: library visit.", ""]}
    out = activity_texts.for_card("Preparatory", content, ["PSLS7"], known={"P1CG3"})
    assert out["desc"][0].startswith("Curricular Goal: PLBCG5 | Competency: PLBC5.1")


def test_b1_an_activity_without_goal_or_competency_is_named_as_unfinished():
    assert activity_texts.card_problems("Middle", "Shapes", {"gl": [], "cpt": ["MC1.1"], "approaches": [1]}) == \
        ["'Shapes' has no curricular goal - add it in the Activity Library"]


# --- B3: approach ---------------------------------------------------------------------------------------------

def test_b3_codes_in_any_other_are_not_an_approach():
    assert activity_texts.codes_only("R3CG 1 , R3C-1.1") and activity_texts.codes_only("MCG 2, C-2.2")
    assert not activity_texts.codes_only("Inquiry Based") and not activity_texts.codes_only("Model Making")
    lang = activity_texts.for_card("Middle", {"approaches": [5], "any-other": "R3CG 1 , R3C-1.1", "gl": ["R3CG1"],
                                              "cpt": ["R3C1.1"], "desc": ["", ""]}, ["SL3"], known=set())
    assert lang["approaches"] == [5] and lang["any-other"] == "Activity-Based Learning"   # a real approach, not codes
    art = activity_texts.for_card("Middle", {"approaches": [5], "any-other": "DMCG 1 , DMC-1.1"}, ["SAE"], known=set())
    pe = activity_texts.for_card("Middle", {"approaches": [5], "any-other": "PECG1,C-1.5"}, ["SPE"], known=set())
    assert art["approaches"] == [1] and pe["approaches"] == [2]
    real = activity_texts.for_card("Middle", {"approaches": [5], "any-other": "Inquiry Based"}, ["SSC"], known=set())
    assert real["approaches"] == [5] and real["any-other"] == "Inquiry Based"
    parakh = activity_texts.for_card("Middle", {"approaches": [5], "any-other": "MCG 2 , C-2.2"}, ["SM"], known=set(),
                                     school_made=False)
    assert parakh["approaches"] == [5]                                                 # NCERT's own content stays


def test_b3_a_middle_activity_without_approach_says_so():
    lk = make_lookups("MIDDLE")
    lk.activities = copy.deepcopy(lk.activities)                 # the bank content is shared with other tests
    for entry in lk.activities.values():
        entry["content"]["dt"]["approaches"] = []
        entry["content"]["dt"]["any-other"] = ""
    _, errors = sync.build_payloads("MIDDLE", blank_student("MIDDLE"), filled_row("MIDDLE"), lk)
    assert any("no approach ticked - set it in the Activity Library" in e for e in errors), errors


# --- B4: the teacher's notes per activity ---------------------------------------------------------------------

def _prep_activities(row, lk):
    payloads, errors = sync.build_payloads("PREPARATORY", blank_student("PREPARATORY"), row, lk)
    return next(p for p in payloads if p["hpc_col"] == "part_b")["formdata"], errors


def _each_subject_own_activity():
    return grid_row(**{s: (f"P{85 + i}", "Beginner", "Proficient", "Advanced") for i, s in enumerate(SUBJ)})


def test_b4_a_typed_observation_stays_on_one_activity_the_others_get_their_own():
    row = _each_subject_own_activity()
    row["b_observation"] = "Asked good questions about the plants in the school garden."
    acts, _ = _prep_activities(row, lookups_with(*range(86, 92)))
    texts = [a["dt"]["tfob"] for a in acts]
    assert texts.count(row["b_observation"]) == 1 and len(acts) == 7
    others = [t for t in texts if t != row["b_observation"]]
    assert all(t.startswith("In '") for t in others) and len(set(others)) == 6       # each from its own activity
    assert all(a["dt"]["lp"] == ["", ""] for a in acts if a["dt"]["tfob"] != row["b_observation"])


def test_b4_stock_phrases_are_not_copied_anywhere():
    row = _each_subject_own_activity()
    row["b_observation"] = SUGGESTIONS["b_observation"][0]                           # "Took part actively ..."
    row["b_challenges"] = SUGGESTIONS["b_challenges"][1]                             # "Needed help to put ideas ..."
    acts, _ = _prep_activities(row, lookups_with(*range(86, 92)))
    assert not any(a["dt"]["tfob"] == row["b_observation"] for a in acts)
    assert not any(row["b_challenges"] in a["dt"]["lp"] for a in acts)
    assert all("strongest in creativity (Advanced)" in a["dt"]["tfob"] for a in acts)
    assert checks.part_b_warnings(acts) == []                                        # nothing repeated 3+ times


# --- B7: help that follows the level and the barriers -----------------------------------------------------------

def _dt(domain, a, s, c, bar=()):
    return {"domain": [domain], "awr": ["", "", "", a], "sen": ["", "", "", s], "cre": ["", "", "", c], "bar": list(bar)}


def test_b7_help_for_a_beginner_is_guided_practice_in_the_subjects_own_words():
    text = notes.help_progress(_dt("SAE", "beginner", "beginner", "beginner", bar=[1]))
    assert text.startswith("Give step-by-step guided practice in") and "art" in text
    assert "problem-solving" not in text and "challenging" not in text and "keep tasks short" in text
    assert "challenging" in notes.help_progress(_dt("SM", "advance", "advance", "advance"))
    assert notes.help_progress(_dt("SM", "", "advance", "advance")) == ""


def test_b7_barriers_mix_only_none_or_a_mild_habit_and_praise_in_a_barrier_is_flagged():
    options = next(p for p in MIDDLE.PARTS if p.code == "B").fields(None)
    barriers = next(f for f in options if f.key == "b_barriers")
    pool, pick = multi_mix("b_barriers", barriers.options)
    assert pick == 1 and "None" in pool and "Lack of Attention" in pool
    assert not {"Peer Pressure", "Domestic Issues", "Inappropriate behavior in classroom", "Severe illness or injury",
                "Any Other"} & set(pool)
    acts = [{"nm": "Sewing", "dt": {"any_other": ["", "", "helpful"]}}]
    assert checks.part_b_warnings(acts) == ["'Sewing': the barrier 'Any Other' says 'helpful' - that is not a barrier"]


# --- duplicate detector (section 6.3) ---------------------------------------------------------------------------

def test_the_same_free_text_in_three_activities_is_reported():
    same = "Learned key scientific principles and multidisciplinary connections."
    acts = [{"nm": f"A{i}", "dt": {"ml": [same, "", "", ""]}} for i in range(3)]
    assert checks.part_b_warnings(acts) == [f"'By doing this activity, I learnt' is the same in 3 activities (\"{same[:60]}...\")"]
    assert checks.part_b_warnings(acts[:2]) == []
