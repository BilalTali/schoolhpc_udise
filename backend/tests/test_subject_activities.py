"""Activities belong to their subjects: R1 activities are offered under R1, Mathematics ones under Mathematics,
and a new activity's competencies must be ones used for the subjects chosen for it. Made-up activities only."""
import json

from backend.services import activity_grid
from backend.tests.test_activity_library import (  # noqa: F401  (fixtures)
    API, bank_record, by_code, client, items, no_waiting, sync, world,
)


def record(pid, caption, subject, cpt):
    """A PARAKH bank activity for one Preparatory subject (0 = Language 1 (R1), 2 = Mathematics)."""
    r = bank_record(pid, "Preparatory", caption, subject=subject)
    data = json.loads(r["activity_data_json"])
    data["dt"]["cpt"], data["dt"]["gl"] = [cpt], [cpt.split("C")[0] + "CG1"]
    r["activity_data_json"] = json.dumps(data)
    return r


def _library(world):
    users, fake = world
    fake.records = [record(1, "Story telling", 0, "L1C1.1"), record(2, "Counting game", 2, "MC1.1")]
    sync(users["admin_a"])
    return users


def test_a_parakh_activity_belongs_to_the_subject_parakh_lists(world):
    users = _library(world)
    listing = items(users["t1"])
    assert by_code(listing, "Story telling")["subjects"] == ["PSLS1"]
    assert by_code(listing, "Counting game")["subjects"] == ["PSLS3"]
    entries = client.get(f"{API}/activity-library/dropdown/Preparatory", headers=users["t1"]).json()["entries"]
    assert {e["key"]: e["subjects"] for e in entries} == {"P1": ["PSLS1"], "P2": ["PSLS3"]}
    # the school admin can still widen it on purpose
    story = by_code(items(users["admin_a"]), "Story telling")
    widened = client.patch(f"{API}/activity-library/{story['id']}", headers=users["admin_a"],
                           json={"subjects": ["PSLS1", "PSLS2"]}).json()
    assert widened["subjects"] == ["PSLS1", "PSLS2"]


def test_competency_codes_say_which_subjects_use_them(world):
    users = _library(world)
    codes = client.get(f"{API}/activity-library/codes/Preparatory", headers=users["t1"]).json()
    assert {c["code"]: c["subjects"] for c in codes["competencies"]} == {"L1C1.1": ["PSLS1"], "MC1.1": ["PSLS3"]}
    assert {c["code"]: c["subjects"] for c in codes["goals"]} == {"L1CG1": ["PSLS1"], "MCG1": ["PSLS3"]}


def test_a_new_activity_uses_competencies_of_the_subjects_chosen_for_it(world):
    users = _library(world)
    rubric = {a: {"beginner": f"{a} b", "proficient": f"{a} p", "advanced": f"{a} a"}
              for a in ("awareness", "sensitivity", "creativity")}
    body = {"stage": "Preparatory", "title": "Read aloud", "activity_text": "Children read aloud.",
            "assessment_text": "Can you read it again?", "rubric": rubric, "subjects": ["PSLS1"],
            "goals": ["L1CG1"], "competencies": ["MC1.1"]}
    bad = client.post(f"{API}/activity-library", headers=users["t1"], json=body)
    assert bad.status_code == 422 and "MC1.1" in bad.text and "Mathematics" in bad.text
    good = client.post(f"{API}/activity-library", headers=users["t1"], json={**body, "competencies": ["L1C1.1"]})
    assert good.status_code in (200, 201), good.text
    assert good.json()["subjects"] == ["PSLS1"]
    # changing its subject later to Mathematics, with R1 competencies, is refused too
    moved = client.patch(f"{API}/activity-library/{good.json()['id']}", headers=users["t1"],
                         json={"subjects": ["PSLS3"], "version": good.json()["version"]})
    assert moved.status_code == 422 and ("L1C1.1" in moved.text or "L1CG1" in moved.text) and "Mathematics" in moved.text


def test_the_activities_grid_offers_and_accepts_only_the_subjects_activities():
    entries = [{"key": "P1", "label": "Story telling", "subjects": ["PSLS1"], "grade_id": 7},
               {"key": "P2", "label": "Counting game", "subjects": ["PSLS3"], "grade_id": 7}]
    allowed = {e["key"]: e for e in entries}
    problems = activity_grid._check_values("Preparatory", {"b_act_PSLS3": "P1", "b_act_PSLS1": "P1"}, allowed, set(), 7)
    assert "b_act_PSLS1" not in problems
    assert "Language 1 (R1)" in problems["b_act_PSLS3"] and "Mathematics" in problems["b_act_PSLS3"]
    # a choice the student already has stays allowed (nothing on PARAKH is undone by this rule)
    assert activity_grid._check_values("Preparatory", {"b_act_PSLS3": "P1"}, allowed, {"P1"}, 7) == {}
    assert activity_grid.subjects_for(["PSLS1", "PSLS3", "PSLS4"], ["PSLS3"]) == ["PSLS3"]
    assert activity_grid.subjects_for(["PSLS1"], None) == ["PSLS1"]           # no subjects known: as before


def test_each_subject_gets_its_own_activity_as_the_default(world):
    from backend.database import SessionLocal
    from backend.services import activity_library as lib
    users = _library(world)
    teacher = client.get(f"{API}/auth/me", headers=users["t1"]).json()
    actor = lib.Actor("TEACHER", teacher["id"], teacher["school_id"], "")
    with SessionLocal() as db:
        entries = lib.library_entries(db, actor, "Preparatory")
        defaults = lib.subject_defaults(db, actor, "Preparatory", entries)
    assert defaults == {"PSLS1": "P1", "PSLS3": "P2"}               # R2, Other Learning Activities ...: none of their own
    resolve = lib.resolver_for_teacher(teacher["id"], "Preparatory")
    assert resolve.defaults == defaults


def test_defaults_fill_only_empty_subjects_and_never_override_a_choice():
    from backend.hpc.stages import activity_grid as grid
    subjects = ["PSLS1", "PSLS2", "PSLS3"]
    now = grid.Current({grid.act_key("PSLS3"): "P9"}, [], False)
    draft = {grid.act_key("PSLS2"): ""}                                # the teacher cleared R2 on purpose
    values, source = grid.effective(subjects, now, draft, {}, {"PSLS1": "P1", "PSLS2": "P5", "PSLS3": "P2"})
    assert (values[grid.act_key("PSLS1")], source[grid.act_key("PSLS1")]) == ("P1", "default")
    assert (values[grid.act_key("PSLS2")], source[grid.act_key("PSLS2")]) == ("", "draft")
    assert (values[grid.act_key("PSLS3")], source[grid.act_key("PSLS3")]) == ("P9", "portal")


def test_a_subject_takes_only_its_own_activities_even_when_it_has_none():
    allowed = {"P1": {"subjects": ["PSLS1"], "grade_id": 7}, "P2": {"subjects": ["PSLS3"], "grade_id": 7}}
    assert "b_act_PSLS7" in activity_grid._check_values("Preparatory", {"b_act_PSLS7": "P1"}, allowed, set(), 7)
    assert activity_grid.subjects_for(["PSLS1", "PSLS3", "PSLS7"], ["PSLS1"]) == ["PSLS1"]


def test_an_activity_is_only_for_its_own_grade():
    allowed = {"P1": {"subjects": ["PSLS1"], "grade_id": 7}, "L9": {"subjects": ["PSLS1"], "grade_id": None},
               "P85": {"subjects": None, "grade_id": None}}           # PARAKH's own lists: nothing known, not checked
    assert activity_grid._check_values("Preparatory", {"b_act_PSLS1": "P1"}, allowed, set(), 7) == {}
    wrong = activity_grid._check_values("Preparatory", {"b_act_PSLS1": "P1"}, allowed, set(), 8)
    assert "for Grade 4, not Grade 5" in wrong["b_act_PSLS1"]
    assert "no grade yet" in activity_grid._check_values("Preparatory", {"b_act_PSLS1": "L9"}, allowed, set(), 8)["b_act_PSLS1"]
    assert activity_grid._check_values("Preparatory", {"b_act_PSLS1": "P85"}, allowed, set(), 8) == {}
    assert activity_grid._check_values("Preparatory", {"b_act_PSLS1": "P1"}, allowed, {"P1"}, 8) == {}   # already on PARAKH
    assert activity_grid.grade_id_of("Preparatory", {"grade": "Grade 5"}) == 8                      # older class lists
    assert activity_grid.grade_id_of("Preparatory", {"grade": "Grade 5", "grade_id": 8}) == 8


def test_default_activities_are_per_grade():
    from backend.hpc.stages import activity_grid as grid

    def resolve(key):
        return None
    resolve.defaults, resolve.defaults_by_grade = {"PSLS1": "P1"}, {7: {"PSLS1": "P1"}, 8: {}}
    assert grid.defaults_for(resolve, 7) == {"PSLS1": "P1"} and grid.defaults_for(resolve, "8") == {}
    assert grid.defaults_for(resolve, None) == {}                       # grade not known: nothing filled in
    assert grid.defaults_for(lambda key: None, 7) is None                  # PARAKH's own lists: no defaults


def test_a_new_activity_is_made_for_a_grade_and_a_subject_without_parakh_codes_takes_typed_ncf_codes(world):
    users = _library(world)
    codes = client.get(f"{API}/activity-library/codes/Preparatory", headers=users["t1"]).json()
    assert codes["grades"] == [{"id": 6, "name": "Grade 3"}, {"id": 7, "name": "Grade 4"}, {"id": 8, "name": "Grade 5"}]
    rubric = {a: {"beginner": f"{a} b", "proficient": f"{a} p", "advanced": f"{a} a"}
              for a in ("awareness", "sensitivity", "creativity")}
    body = {"stage": "Preparatory", "title": "R2 story circle", "activity_text": "Children retell a story.",
            "assessment_text": "Can you tell it again?", "rubric": rubric, "grade_id": 8, "subjects": ["PSLS2"],
            "goals": ["L2CG1"], "competencies": ["L2C1.1"]}                # R2 has no PARAKH code here: typed NCF codes
    made = client.post(f"{API}/activity-library", headers=users["t1"], json=body)
    assert made.status_code in (200, 201), made.text
    assert made.json()["grade_id"] == 8 and made.json()["grade_name"] == "Grade 5" and made.json()["usable_in_excel"]
    assert client.post(f"{API}/activity-library", headers=users["t1"],
                       json={**body, "title": "Wrong grade", "grade_id": 9}).status_code == 422     # Grade 6 is Middle
    assert client.post(f"{API}/activity-library", headers=users["t1"],
                       json={**body, "title": "Bad code", "competencies": ["not a code!"]}).status_code == 422


def test_activities_are_shown_by_name_and_code():
    from backend.services import activity_library as lib
    name = activity_grid.short_name                 # the grid: the library's label without the workbook key
    assert name("Important Idea Circle (L2CG1,C-1.1) (#Ld3d2f493-d277-11f1-ae20-a44cc81641cb)") == "Important Idea Circle (L2CG1,C-1.1)"
    assert name("TWCG4,C-4.1 (#P123)") == "TWCG4,C-4.1" and name("85: Conversation in pairs") == "Conversation in pairs"
    # the name: after the codes in a title made here, else the title the activity's text gives
    assert lib.activity_name("L2CG1,C-1.1 Important Idea Circle", "") == "Important Idea Circle"
    assert lib.activity_name("Dance and Movement C-4.2 My Village Dance", "") == "My Village Dance"
    assert lib.activity_name("FSCG1,C-1.2", "Text for Activity: Children wash hands.\n\nMagic Hands Wash\nChildren learn") \
        == "Magic Hands Wash"
    assert lib.activity_name("", "Activity Title: “Shape Detectives: Observe, Compare, Explain”\nStep 1") \
        == "Shape Detectives: Observe, Compare, Explain"
    assert lib.activity_name("", "Suggested Activity:\n“Safe or Unsafe?”\nIn this discussion") == "Safe or Unsafe?"
    assert lib.activity_name("", "Task: \"The Double-Take Performance\"\nStudents") == "The Double-Take Performance"
    assert lib._label("Important Idea Circle", "L2CG1,C-1.1 Important Idea Circle") == "Important Idea Circle (L2CG1,C-1.1)"
    assert lib._label("Safe or Unsafe?", "CG 1-C1.6") == "Safe or Unsafe? (CG 1-C1.6)" and lib._label("", "TWCG4,C-4.1") == "TWCG4,C-4.1"
    # no title in the text: no name (the code alone is shown; the school can give it a display name)
    assert lib.activity_name("TWCG4,C-4.1", "Sequence of the Activity:\n1. Step 1- The teacher provides an overview") == ""


def test_part_b_text_answers_offer_suggestions_that_fit():
    from backend.hpc.stages import get_stage
    from backend.services import hpc_cards
    for stage in ("FOUNDATIONAL", "PREPARATORY", "MIDDLE"):
        part_b = next(p for p in get_stage(stage).PARTS if p.code == "B")
        for f in part_b.fields(None):
            meta = hpc_cards.field_meta(f)
            assert all(not f.max_len or len(s) <= f.max_len for s in meta["suggestions"]), f.key
            if f.options:
                assert meta["suggestions"] == []                # pick lists have their options
    middle = {f.key: hpc_cards.field_meta(f) for f in next(p for p in get_stage("MIDDLE").PARTS if p.code == "B").fields(None)}
    assert middle["b_learnt"]["suggestions"] and middle["b_interesting"]["suggestions"]
    assert all(len(s) <= 60 for s in middle["b_interesting"]["suggestions"])


def test_missing_part_b_answers_are_named_on_the_grid_row():
    blank = {"part_b": None, "part_c": None}
    parts = activity_grid._parts("Foundational", blank)
    missing = activity_grid.answers_missing("Foundational", parts, {})
    assert missing == ["Self: I liked doing this work", "Self: I found this work easy"]
    assert activity_grid.answers_missing("Foundational", parts, {"b_sa_liked": "Yes", "b_sa_easy": "Yes"}) == []


def test_mix_hands_out_only_safe_options_for_several_option_questions():
    from backend.hpc.stages import get_stage
    from backend.hpc.suggestions import multi_mix
    fields = {f.key: f for f in next(p for p in get_stage("MIDDLE").PARTS if p.code == "B").fields(None)}
    strengths, pick = multi_mix("b_strengths", fields["b_strengths"].options)
    assert pick == 2 and "Any Other" not in strengths and "Collaboration" in strengths
    # barriers are never handed out at random (B7): the teacher ticks the ones that apply
    assert multi_mix("b_barriers", fields["b_barriers"].options) == ([], 0)
    grid, pick = multi_mix("b_grid_awareness", fields["b_grid_awareness"].options)
    assert pick == 2 and grid == list(fields["b_grid_awareness"].options)
    assert multi_mix("a3_resources", ["Books", "TV", "Radio"]) == ([], 0)      # facts are never mixed
    prep_a3 = {f.key: f for f in next(p for p in get_stage("PREPARATORY").PARTS if p.code == "A3").fields(None)}
    support, pick = multi_mix("a3_support", prep_a3["a3_support"].options)
    assert pick == 2 and "Numbers and Math" in support and "Other subject area" not in support
    mid_a4 = {f.key: f for f in next(p for p in get_stage("MIDDLE").PARTS if p.code == "A4").fields(None)}
    support, pick = multi_mix("a4_support", mid_a4["a4_support"].options)
    assert pick == 2 and "Maths" in support and not {"Any other", "Managing difficult emotions"} & set(support)
