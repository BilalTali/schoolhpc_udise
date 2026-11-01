"""Part C (P1): notes written from each subject's own levels (C1, C3) and Part C against Part B (C4)."""
import itertools

import pytest

from backend.hpc import checks, credit, notes, suggestions
from backend.hpc.stages import foundational, middle, preparatory
from backend.tests.test_cards_and_auth import API, teacher_client  # noqa: F401  (fixture)

LEVELS = ["Beginner", "Proficient", "Advanced"]


def lv(a, s, c):
    return {"awareness": a, "sensitivity": s, "creativity": c}


# --- C1: the note follows the ticked levels -------------------------------------------------------------------

def test_c1_note_names_the_strongest_and_weakest_ability_with_their_levels():
    text = notes.note("PSLS3", lv("Beginner", "Proficient", "Advanced"))
    assert text.startswith("Strength - Creativity (Advanced): finding different ways to solve a problem")
    assert "To improve - Awareness (Beginner): number concepts" in text
    assert "good understanding" not in text and "needs support" not in text


def test_c1_no_note_without_all_three_levels():
    assert notes.note("SM", lv("Advanced", "", "Beginner")) == ""
    assert notes.note("SM", {}) == ""


def test_c1_never_the_same_note_under_two_subjects_of_a_stage():
    for stage in (preparatory, middle, foundational):
        for combo in itertools.product(LEVELS, repeat=3):
            texts = [notes.note(d, lv(*combo)) for d in stage.DOMAINS]
            assert all(texts) and len(set(texts)) == len(texts), (stage.__name__, combo)


def test_c1_no_written_work_for_art_pe_skill_other_or_bagless():
    for d in ("PSLS5", "PSLS6", "PSLS7", "SAE", "SPE", "SV", "SLA", "SVE", *foundational.DOMAINS):
        for combo in itertools.product(LEVELS, repeat=3):
            assert "writ" not in notes.note(d, lv(*combo)).lower(), d


def test_c1_notes_fit_parakhs_limits():
    for d in notes.SUBJECT_WORDS:
        for combo in itertools.product(LEVELS, repeat=3):
            limit = 330 if d.startswith("FSDOM") else 400
            assert 0 < len(notes.note(d, lv(*combo), limit, activity="A long activity name " * 3)) <= limit


def test_c1_stock_notes_are_no_longer_offered_or_mixed():
    assert suggestions.suggestions_for("c_SM_remark", 400) == []
    assert suggestions.record_kind("Mathematics: Remark", "c_SM_remark") == "levels"
    assert suggestions.record_kind("Physical Development: key performance descriptor", "c_FSDOM1_descriptor") == "levels"


# --- C3: Foundational descriptors ------------------------------------------------------------------------------

def test_c3_all_advanced_is_never_called_age_appropriate_or_developing():
    for d in foundational.DOMAINS:
        text = notes.note(d, lv("Advanced", "Advanced", "Advanced"), 330)
        assert "age-appropriate" not in text and "developing" not in text
        assert "(Advanced)" in text and "Beginner" not in text


def test_c3_foundational_credits_stay_4_44_0_89_100():
    part_c = {"awr": [",".join(foundational.DOMAINS), "", ""], "sen": [",".join(foundational.DOMAINS), "", ""],
              "cre": [",".join(foundational.DOMAINS), "", ""]}
    t = credit.build_foundational(part_c, "grd1", {})
    assert t["table2"][0][4:] == ["4.44", "0.89", 100]


# --- checks on what is on a card (C1, C3) -----------------------------------------------------------------------

def test_checks_flag_the_sample_cards_problems():
    # Preparatory sample: stock phrases at random, "written work" under Art and PE, praise beside Beginner
    row = {f"c_{d}_{a}": "Beginner" for d in preparatory.DOMAINS for a in notes.ABILITIES}
    row.update({f"c_{d}_remark": "Takes part actively; needs more practice in written work." for d in ("PSLS5", "PSLS6")})
    row["c_PSLS3_remark"] = "Shows good understanding of the concepts taught."
    found = checks.part_c_warnings("preparatory", preparatory.DOMAINS, preparatory.SUBJECTS, row)
    assert any("Art Education: the note mentions written work" in w for w in found)
    assert any("Mathematics: the note praises" in w for w in found)
    assert any("stock phrase" in w for w in found)
    assert any("same note is under 2 subjects" in w for w in found)
    # Middle sample: one typed sentence under all 11 subjects
    row = {f"c_{d}_remark": "Demonstrates consistent academic effort." for d in middle.DOMAINS}
    assert any("under 11 subjects" in w for w in checks.part_c_warnings("middle", middle.DOMAINS, middle.SUBJECTS, row))


def test_checks_a_generated_note_must_match_the_levels_ticked_now():
    row = {"c_SM_awareness": "Advanced", "c_SM_sensitivity": "Proficient", "c_SM_creativity": "Beginner"}
    row["c_SM_remark"] = notes.note("SM", notes.levels_from_row(row, "SM"))
    assert checks.part_c_warnings("middle", ["SM"], ["Mathematics"], row) == []
    row["c_SM_creativity"] = "Advanced"                                    # the level changed after the note
    assert "written for other levels" in checks.part_c_warnings("middle", ["SM"], ["Mathematics"], row)[0]


def test_checks_foundational_all_advanced_with_age_appropriate():
    row = {f"c_FSDOM1_{s}": "Advanced" for s in ("awr", "sen", "cre")}
    row["c_FSDOM1_descriptor"] = "Shows age-appropriate progress in this domain."
    found = checks.part_c_warnings("foundational", ["FSDOM1"], ["Physical Development"], row)
    assert any("undersells" in w for w in found)


# --- C4: Part C against Part B ----------------------------------------------------------------------------------

def test_c4_warns_when_part_c_is_two_steps_from_the_activity_rating():
    part_b = [{"nm": "Shapes walk", "dt": {"domain": ["SM"], "awr": ["", "", "", "beginner"],
                                            "sen": ["", "", "", "proficient"], "cre": ["", "", "", "advance"]}}]
    row = {"c_SM_awareness": "Advanced", "c_SM_sensitivity": "Proficient", "c_SM_creativity": "Proficient"}
    found = checks.part_b_vs_c(["SM"], ["Mathematics"], row, part_b)
    assert found == ["Mathematics: Awareness is Advanced in Part C but Beginner in its Part B activity"]
    assert notes.activity_names(part_b) == {"SM": "Shapes walk"}


# --- through the app: Mix writes the notes from the levels -----------------------------------------------------

def test_mix_writes_each_note_from_the_students_levels_and_leaves_the_rest_blank(teacher_client):  # noqa: F811
    client, _ = teacher_client
    bulk = f"{API}/teacher/hpc-cards/Preparatory/bulk"
    sid = client.get(bulk, params={"field": "c_PSLS3_remark"}).json()["rows"][0]["student_id"]
    for ability, level in (("awareness", "Beginner"), ("sensitivity", "Proficient"), ("creativity", "Advanced")):
        assert client.put(bulk, json={"field": f"c_PSLS3_{ability}", "values": {sid: level}}).status_code == 200
        client.put(bulk, json={"field": f"c_PSLS5_{ability}", "values": {sid: ""}})
    keys = ["c_PSLS3_remark", "c_PSLS5_remark"]
    done = client.post(f"{API}/teacher/hpc-cards/Preparatory/bulk-mix",
                       json={"fields": keys, "replace": True, "apply": True}).json()
    maths = client.get(bulk, params={"field": "c_PSLS3_remark"}).json()
    assert maths["field"]["from_records"] == "levels" and maths["field"]["suggestions"] == []
    assert maths["rows"][0]["value"].startswith("Strength - Creativity (Advanced)")
    assert maths["rows"][0]["value"] == maths["rows"][0]["from_levels"]
    art = client.get(bulk, params={"field": "c_PSLS5_remark"}).json()["rows"][0]
    assert art["from_levels"] == ""                                          # no levels: no note, and it is reported
    assert any(s["key"] == "c_PSLS5_remark" and "left blank" in s["reason"] for s in done["skipped"])
