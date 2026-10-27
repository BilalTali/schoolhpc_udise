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
    entries = [{"key": "P1", "label": "Story telling", "subjects": ["PSLS1"]},
               {"key": "P2", "label": "Counting game", "subjects": ["PSLS3"]}]
    allowed = {e["key"]: e["subjects"] for e in entries}
    problems = activity_grid._check_values("Preparatory", {"b_act_PSLS3": "P1", "b_act_PSLS1": "P1"}, allowed, set())
    assert "b_act_PSLS1" not in problems
    assert "Language 1 (R1)" in problems["b_act_PSLS3"] and "Mathematics" in problems["b_act_PSLS3"]
    # a choice the student already has stays allowed (nothing on PARAKH is undone by this rule)
    assert activity_grid._check_values("Preparatory", {"b_act_PSLS3": "P1"}, allowed, {"P1"}) == {}
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


def test_a_subject_without_activities_of_its_own_can_take_any_activity():
    allowed = {"P1": ["PSLS1"], "P2": ["PSLS3"]}
    assert activity_grid._check_values("Preparatory", {"b_act_PSLS7": "P1"}, allowed, set()) == {}    # Other Learning Activities
    assert "b_act_PSLS3" in activity_grid._check_values("Preparatory", {"b_act_PSLS3": "P1"}, allowed, set())
    assert activity_grid.subjects_for(["PSLS1", "PSLS3", "PSLS7"], ["PSLS1"], {"PSLS1", "PSLS3"}) == ["PSLS1", "PSLS7"]


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
