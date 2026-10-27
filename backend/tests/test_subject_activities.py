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
