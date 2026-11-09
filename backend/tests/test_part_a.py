"""Part A (P3): name and age from the record (A1), cut-off text (A2), the goal fields (A3), template options (A4),
'I ... very well' (A5), ambition and guidance (A6), the hand's fingers (A7), peer sheets and 'specify' (A8),
blank months (A9), interests (A10), capitals (A11), name and gender (A12), the avatar (A14)."""
import json
from datetime import date

from backend.hpc import part_a_checks, suggestions, sync
from backend.hpc.stages import get_stage
from backend.hpc.stages.common import record_age, record_name, tidy_case
from backend.tests.conftest import blank_student, filled_row, make_lookups


def _payload(stage, row, data=None):
    data = data or blank_student(stage)
    payloads, errors = sync.build_payloads(stage, data, row, make_lookups(stage))
    out = {}
    for p in payloads:
        out[p["hpc_col"]] = json.loads(p["formdata"]) if isinstance(p["formdata"], str) else p["formdata"]
    return out, errors


def _fields(stage):
    return {f.key: f for p in get_stage(stage).PARTS for f in p.fields(make_lookups(stage))}


# --- A1 ---------------------------------------------------------------------------------------------------------

def test_a1_middle_name_and_age_come_from_the_record_not_what_was_typed():
    row = filled_row("MIDDLE")
    row["a2_about_9"], row["a2_about_10"] = "Aarav", "40"
    data = blank_student("MIDDLE")
    data.record["stu_info"].update(student_name="PAKEEZA", dob="2014-03-10")
    parts, _ = _payload("MIDDLE", row, data)
    about = parts["part_a2"]["allAboutMe"]
    assert about[8] == "Pakeeza" and about[9] == record_age({"dob": "2014-03-10"})


def test_a1_record_helpers():
    assert record_name({"student_name": "MUSTAFA AHMAD DAR GOJJAR"}, 15) == "Mustafa"
    assert record_name({"student_name": "INSHA TARIQ"}) == "Insha Tariq"
    assert record_age({"dob": "2014-03-10"}, today=date(2026, 11, 1)) == "12"
    assert record_age({"dob": ""}) == ""


# --- A2, A4, A5, A6, A10, A12: warnings -------------------------------------------------------------------------

def test_a2_text_cut_at_the_limit_is_flagged():
    f = _fields("MIDDLE")
    row = {"a2_about_8": "Solving complex equations and learning new co"}            # 45 = the limit
    found = part_a_checks.part_a_warnings("middle", row, [f["a2_about_8"]], {})
    assert any("looks cut off" in w for w in found["A2"])
    assert not part_a_checks.looks_cut_off("I finish my work on time.", 45)


def test_a4_template_options_are_taken_out_of_the_answer():
    row = filled_row("MIDDLE")
    row["a2_about_5"] = "Completing assignment(sometimes, most times, all the time)"
    parts, _ = _payload("MIDDLE", row)
    assert parts["part_a2"]["allAboutMe"][4] == "Completing assignment"


def test_a5_a6_a10_a12_warnings():
    f = _fields("MIDDLE")
    from backend.hpc.fields import Field
    interests = Field("a1_interests", "Interests", ("ints",), "multi", {f"I{i}": i for i in range(11)})
    row = {"a2_about_4": "", "a3_myAmbition": "Shows high curiosity, regular attendance, and enthusiastic participation",
           "a3_guidanceFrom": "Educational kits, science books, and digital resources",
           "a1_interests": [f"I{i}" for i in range(9)]}
    found = part_a_checks.part_a_warnings("middle", row, [*f.values(), interests],
                                          {"student_name": "MUSTAFA AHMAD", "gender": "FEMALE"})
    text = json.dumps(found)
    assert "'I ... very well' is empty" in text
    assert "reads like a teacher's remark" in text and "names no person" in text
    assert "are ticked - tick only" in text
    assert "'Mustafa' is usually a boy's name" in text
    ok = part_a_checks.part_a_warnings("middle", {"a2_about_4": "draw", "a3_myAmbition": "To become a doctor.",
                                                 "a3_guidanceFrom": "My teachers and parents"}, [], {})
    assert ok == {}


# --- A3 ---------------------------------------------------------------------------------------------------------

def test_a3_goal_fields_go_where_parakhs_page_keeps_them():
    row = filled_row("MIDDLE")
    row.update({"a2_personalGoal_goal": "Exercise daily", "a2_personalGoal_reason": "It keeps me healthy",
                "a2_personalGoal_step1": "Wake up early", "a2_personalGoal_step2": "Walk to school"})
    parts, _ = _payload("MIDDLE", row)
    assert parts["part_a2"]["personalGoal"] == ["Exercise daily", "It keeps me healthy", "Wake up early", "Walk to school"]


# --- A7 ---------------------------------------------------------------------------------------------------------

def test_a7_each_finger_has_its_prompt_and_phrases_that_fit_it():
    f = _fields("PREPARATORY")
    labels = [f[f"a2_about_{i}"].label for i in range(1, 6)]
    assert labels == ["Things about me: I am good at", "Things about me: I am not so good at",
                      "Things about me: I would like to improve my skill of", "Things about me: I like to",
                      "Things about me: I don't like to"]
    for i in range(1, 6):
        fld = f[f"a2_about_{i}"]
        phrases = suggestions.suggestions_for(fld.key, fld.max_len, fld.label)
        assert phrases and "My parents" not in phrases and "For my homework" not in phrases
        assert not suggestions.mixable(fld.key, fld.label)


# --- A8 ---------------------------------------------------------------------------------------------------------

def test_a8_the_friends_name_on_a_filled_peer_sheet_is_the_student():
    row = filled_row("PREPARATORY")
    row["a3_peer1_1"] = "Yes"
    data = blank_student("PREPARATORY")
    data.record["stu_info"]["student_name"] = "MUSTAFA AHMAD DAR"
    parts, _ = _payload("PREPARATORY", row, data)
    assert parts["part_a3"]["pr1"][1] == "Mustafa Ahmad Dar"


def test_a8_other_subject_area_needs_its_words():
    row = filled_row("PREPARATORY")
    row["a3_support"], row["a3_support_other"] = "Other subject area", ""
    _, errors = _payload("PREPARATORY", row)
    assert any("'Other subject area' is ticked" in e for e in errors)


# --- A9, A11, A14 -----------------------------------------------------------------------------------------------

def test_a9_foundational_months_without_data_stay_blank():
    row = filled_row("FOUNDATIONAL")
    for m in range(1, 13):
        row[f"a1_working_{m}"] = row[f"a1_present_{m}"] = ""
    row["a1_working_6"], row["a1_present_6"] = 25, 23
    parts, _ = _payload("FOUNDATIONAL", row)
    att = parts["part_a1"]["attn"]
    assert att["1"][0] == "" and att["3"][0] == "" and att["3"][5] == 92


def test_a11_names_in_one_case_get_capitals():
    assert tidy_case("kashmiri") == "Kashmiri" and tidy_case("GHULAM HASSAN") == "Ghulam Hassan"
    assert tidy_case("McDonald") == "McDonald"
    row = filled_row("MIDDLE")
    row["a1_mother_tongue"] = "kashmiri"
    parts, _ = _payload("MIDDLE", row)
    assert parts["part_a1"]["gen"][16] == "Kashmiri"


def test_a14_the_avatar_is_never_handed_out_at_random():
    assert not suggestions.mixable("a2_avatar", "My avatar (avat_01 ... avat_20)")


# --- School defaults: mother tongue Kashmiri, English, Rural ---------------------------------------------------

def test_an_empty_mother_tongue_is_saved_as_kashmiri_and_a_given_one_is_kept():
    for stage in ("FOUNDATIONAL", "PREPARATORY", "MIDDLE"):
        row = filled_row(stage)
        row.pop("a1_mother_tongue")                                   # nothing on PARAKH, the workbook or the card
        parts, errors = _payload(stage, row)
        assert parts["part_a1"]["gen"][16] == "Kashmiri", stage
        assert not [e for e in errors if "Mother Tongue" in e], errors
        row["a1_mother_tongue"] = "Urdu"
        parts, _ = _payload(stage, row)
        assert parts["part_a1"]["gen"][16] == "Urdu", stage


def test_class_settings_start_with_english_and_rural():
    from backend.services import class_settings
    blank = class_settings.blank("Preparatory")
    assert (blank["medium"], blank["rural_urban"]) == ("English", "Rural")
    assert "Medium of instruction" not in class_settings.missing("Preparatory", blank)
