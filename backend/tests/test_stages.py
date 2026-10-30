"""Building the portal save requests for both stages from workbook rows."""
import json

import pytest

from backend.hpc import sync
from backend.hpc.stages import get_stage
from backend.tests.conftest import blank_student, filled_row, make_lookups


@pytest.mark.parametrize("stage", ["FOUNDATIONAL", "PREPARATORY", "MIDDLE"])
def test_filled_row_builds_every_part_in_order(stage):
    lk = make_lookups(stage)
    payloads, errors = sync.build_payloads(stage, blank_student(stage), filled_row(stage), lk)
    assert errors == []
    codes = [p.code for p in get_stage(stage).PARTS]
    assert [p["current_part"] for p in payloads] == codes[1:] + ["mc"]
    assert payloads[-1]["hpc_status"] == "COMPLETED"
    for part, payload in zip(get_stage(stage).PARTS, payloads):
        assert payload["hpc_col"] == part.col
        # Part B is sent as a list, every other part as a JSON string (like the portal pages do)
        assert isinstance(payload["formdata"], list if part.code == "B" else str)


def test_preparatory_a1_attendance_and_portal_values():
    payloads, _ = sync.build_payloads("PREPARATORY", blank_student("PREPARATORY"), filled_row("PREPARATORY"),
                                      make_lookups("PREPARATORY"))
    a1 = payloads[0]
    fd = json.loads(a1["formdata"])
    assert fd["attn"]["1"][12] == 264 and fd["attn"]["2"][12] == 240
    assert fd["attn"]["3"][0] == 90.91 and fd["attn"]["3"][12] == 90.91
    assert fd["gen"][19] == "24"                                  # days absent
    assert fd["gen"][2] == "grd5" and fd["gen"][3] == "A"        # grade code and section from the portal record
    assert fd["ints"] == ["STU_INTRST_READING", "STU_INTRST_ART"]
    assert (a1["cond_class"], a1["med_inst"], a1["location_id"]) == ("grd5", 3, 1)


def test_part_b_puts_a_bank_activity_on_as_a_manual_one_and_finishes_it():
    payloads, _ = sync.build_payloads("PREPARATORY", blank_student("PREPARATORY"), filled_row("PREPARATORY"),
                                      make_lookups("PREPARATORY"))
    b = payloads[3]
    act = b["formdata"][0]
    assert act["nm"] == "Conversation in pairs" and act["is_complete"] is True
    assert act["dt"]["gl"] == ["L1CG1"] and act["dt"]["awr"][3] == "proficient" and act["dt"]["sen"][3] == "advance"
    assert act["dt"]["domain"] == [f"PSLS{i}" for i in range(1, 8)]
    assert act["id"] == "1001_88899091929394_1"
    assert act["dt"]["act_bank_id"] is None and "is_global" not in act["dt"] and act["is_modified"] is True
    assert b["act_bank_map"] == [] and "global_activity_bank_id" not in b


def test_middle_teacher_feedback_follows_rubric_levels():
    payloads, _ = sync.build_payloads("MIDDLE", blank_student("MIDDLE"), filled_row("MIDDLE"), make_lookups("MIDDLE"))
    dt = payloads[4]["formdata"][0]["dt"]
    assert dt["tf"] == ["2", "1", "3"]          # proficient, advanced, beginner -> portal's inverted scale
    assert dt["activity"] == [1]                # approach copied from the bank activity


def test_empty_row_reports_required_fields_and_writes_nothing():
    _, errors = sync.build_payloads("PREPARATORY", blank_student("PREPARATORY"), {}, make_lookups("PREPARATORY"))
    text = "\n".join(errors)
    for expected in ("Mother Tongue: required", "How I feel", "No activity chosen for: Language 1 (R1)",
                     "summative max marks: required", "declaration"):
        assert expected in text


def test_bad_values_are_reported():
    row = filled_row("PREPARATORY")
    row.update({"a1_medium": "Klingon", "a1_present_1": 30, "a1_mother_tongue": "x" * 21, "d_1_obtained": 60})
    _, errors = sync.build_payloads("PREPARATORY", blank_student("PREPARATORY"), row, make_lookups("PREPARATORY"))
    text = "\n".join(errors)
    assert "'Klingon' is not one of" in text
    assert "days present (30) is more than working days (22)" in text
    assert "the portal allows 20" in text
    assert "marks obtained (60) are more than max marks (50)" in text


def test_unchanged_cells_keep_stored_values_exactly():
    stage, lk = "PREPARATORY", make_lookups("PREPARATORY")
    data = blank_student(stage)
    a2 = get_stage(stage).PARTS[1].blank()
    a2["favorites"][2] = " Eid with family "              # odd spacing stored by the portal
    data.raw_parts["part_a2"] = json.dumps(a2)
    row = {**filled_row(stage), **sync.to_row(stage, data, lk)}
    row.update(filled_row(stage))
    payloads, errors = sync.build_payloads(stage, data, row, lk)
    assert json.loads(payloads[1]["formdata"])["favorites"][2] == " Eid with family "


def test_foundational_parts_follow_the_portal_pages():
    payloads, errors = sync.build_payloads("FOUNDATIONAL", blank_student("FOUNDATIONAL"), filled_row("FOUNDATIONAL"),
                                           make_lookups("FOUNDATIONAL"))
    assert errors == []
    a1, a2, b, c, d = payloads
    att = json.loads(a1["formdata"])["attn"]
    assert att["1"][11] == 0 and att["3"][11] == 0          # blank month stored as 0, 0%
    assert att["1"][12] == 242 and att["3"][12] == 90.91
    dt = b["formdata"][0]["dt"]
    assert dt["prof"] == ["S", "A", "C"]                      # sensitivity advanced, awareness proficient, creativity beginner
    assert dt["sa"][:6] == [1, 0, 0, 0, 1, 0]                 # liked: Yes, easy: No
    assert dt["sa"][6:11] == [0, 1, 1, 0, 0]                  # needed: Teachers, Books
    assert b["formdata"][0]["is_complete"] is True
    part_c = json.loads(c["formdata"])
    assert part_c["awr"] == ["", "FSDOM1,FSDOM2,FSDOM3,FSDOM4,FSDOM5,FSDOM51", ""]
    credit = json.loads(d["formdata"])
    # all six domains Proficient on all three abilities: 3 x 0.99 = 2.97 credits, Balvatika level 0.1
    assert credit["table2"][0] == ["Physical Development", "Proficient", "Proficient", "Proficient", "2.97", "0.30", 67]
    assert credit["table2"][-1] == ["Total", "", "", "", "17.82", "1.80", 402]
    assert credit["credit"][0] == [4.5, 0.1, "0.45", ""] and credit["declaration"] is True
    assert d["current_part"] == "mc" and d["hpc_status"] == "COMPLETED"


def test_foundational_part_c_needs_every_domain_level():
    row = filled_row("FOUNDATIONAL")
    row["c_FSDOM3_sen"] = ""
    _, errors = sync.build_payloads("FOUNDATIONAL", blank_student("FOUNDATIONAL"), row, make_lookups("FOUNDATIONAL"))
    assert any("Cognitive Development: Sensitivity level: required" in e for e in errors)


@pytest.mark.parametrize("stage", ["FOUNDATIONAL", "PREPARATORY", "MIDDLE"])
@pytest.mark.parametrize("present", ["", 0])
def test_months_without_working_days_are_accepted(stage, present):
    """Schools have months with no working days (holidays): 0 working days, days present 0 or left blank."""
    row = filled_row(stage)
    for m in (2, 3, 9):                                       # May, June, December
        row[f"a1_working_{m}"], row[f"a1_present_{m}"] = 0, present
    payloads, errors = sync.build_payloads(stage, blank_student(stage), row, make_lookups(stage))
    assert errors == []
    a1 = next(p for p in payloads if p["hpc_col"] == "part_a1")["formdata"]
    a1 = json.loads(a1) if isinstance(a1, str) else a1
    assert a1["attn"]["1"][1] == 0 and a1["attn"]["3"][1] in (0, "")


@pytest.mark.parametrize("stage", ["FOUNDATIONAL", "PREPARATORY", "MIDDLE"])
def test_mother_father_guardian_is_father_unless_chosen(stage):
    """Like the PARAKH page, which pre-selects Father: a blank answer is Father, not a missing one."""
    a1 = next(p for p in get_stage(stage).PARTS if p.code == "A1")
    relation = next(f for f in a1.fields(make_lookups(stage)) if f.key == "a1_guardian_relation")
    assert relation.read(None) == "Father"                                     # nothing on the card yet
    for given, stored in (("", "FATHER"), ("Mother", "MOTHER")):
        row = {**filled_row(stage), "a1_guardian_relation": given}
        payloads, errors = sync.build_payloads(stage, blank_student(stage), row, make_lookups(stage))
        assert not [e for e in errors if "Mother/Father/Guardian:" in e]
        fd = next(p for p in payloads if p["hpc_col"] == "part_a1")["formdata"]
        fd = json.loads(fd) if isinstance(fd, str) else fd
        assert fd["gen"][23] == stored


def test_the_class_list_keeps_the_date_of_birth_for_ages():
    """Read with gender and admission number from the same record, so "All about me" ages need no PARAKH call."""
    student = {"student_id": "1001"}
    sync.add_details(student, blank_student("PREPARATORY").record)
    assert student["dob"] == "2015-01-01" and student["gender"] == "Male" and student["admission_number"] == "A1"
