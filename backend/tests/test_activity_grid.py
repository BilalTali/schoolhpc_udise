"""Part B from the Activities grid: grouping, keeping what PARAKH has, and the checks before a save."""
import copy

from backend.hpc import sync
from backend.hpc.stages import activity_grid as grid
from backend.hpc.stages import get_stage
from backend.hpc.stages.activity import bank_dt
from backend.tests.conftest import BANK_CONTENT, blank_student, filled_row, make_lookups

PREP = get_stage("PREPARATORY")
SUBJ = PREP.DOMAINS                                     # PSLS1 .. PSLS7


def grid_row(**per_subject):
    """filled_row with the grid replaced: per_subject[code] = (key, aw, sen, cre); others default."""
    row = {k: v for k, v in filled_row("PREPARATORY").items() if not k.startswith(("b_act_", "b_lvl_"))}
    for s in SUBJ:
        key, *levels = per_subject.get(s, ("P85", "Proficient", "Proficient", "Proficient"))
        row[grid.act_key(s)] = key
        for (ability, _), level in zip(grid.ABILITIES, levels):
            row[grid.level_key(s, ability)] = level
    return row


def portal_activity(bank, domains, levels=("proficient", "proficient", "proficient"), n=1, sa=None, nm=None):
    dt = bank_dt(PREP.blank_activity, BANK_CONTENT, bank, True, lambda c: {}, list(levels))
    dt.update({"domain": list(domains), "sa": sa or [1] * 8, "tfob": "kept notes"})
    return {"nm": nm or f"Bank {bank}", "id": f"1001_{bank}_{n}", "is_complete": True, "is_modified": False, "dt": dt}


def student_with(*activities):
    data = blank_student("PREPARATORY")
    data.raw_parts["part_b"] = list(activities)
    return data


def lookups_with(*bank_ids):
    lk = make_lookups("PREPARATORY")
    base = lk.activities[85]
    for b in bank_ids:
        lk.activities[b] = {**copy.deepcopy(base), "id": b, "activity_caption": f"Bank {b}"}
    return lk


def part_b(stage, data, row, lk, resolve=None):
    payloads, errors = sync.build_payloads(stage, data, row, lk, resolve)
    b = next(p for p in payloads if p["hpc_col"] == "part_b")
    return b, [e for e in errors if e.startswith("Part B")]


def test_one_activity_with_the_same_levels_is_sent_once():
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), grid_row(), make_lookups("PREPARATORY"))
    assert errors == []
    assert len(b["formdata"]) == 1 and b["formdata"][0]["dt"]["domain"] == SUBJ


def test_same_activity_with_different_levels_becomes_two_activities():
    row = grid_row(PSLS3=("P85", "Advanced", "Beginner", "Proficient"), PSLS5=("P85", "Advanced", "Beginner", "Proficient"))
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), row, make_lookups("PREPARATORY"))
    assert errors == []
    acts = b["formdata"]
    assert [a["dt"]["domain"] for a in acts] == [["PSLS1", "PSLS2", "PSLS4", "PSLS6", "PSLS7"], ["PSLS3", "PSLS5"]]
    assert all(is_manual(a) for a in acts)                           # every activity goes on as a manual one
    assert [acts[1]["dt"][k][3] for k in ("awr", "sen", "cre")] == ["advance", "beginner", "proficient"]
    assert acts[1]["dt"]["tf"] == ["3", "1", "2"]                    # Preparatory feedback follows the levels
    assert len({a["id"] for a in acts}) == 2 and all(a["is_complete"] for a in acts)
    assert b["act_bank_map"] == []


def test_one_activity_per_subject():
    lk = lookups_with(*range(201, 208))
    row = grid_row(**{s: (f"P{201 + i}", "Beginner", "Proficient", "Advanced") for i, s in enumerate(SUBJ)})
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), row, lk)
    assert errors == []
    assert [a["dt"]["domain"] for a in b["formdata"]] == [[s] for s in SUBJ]
    assert [a["nm"] for a in b["formdata"]] == [f"Bank {201 + i}" for i in range(7)]


def test_unchanged_grid_keeps_the_activities_and_their_answers_and_makes_them_manual():
    a = portal_activity(85, SUBJ[:5], sa=[2] * 8, n=1)
    b2 = portal_activity(91, SUBJ[5:], sa=[3] * 8, n=2)
    data = student_with(a, b2)
    lk = lookups_with(91)
    row = {k: v for k, v in filled_row("PREPARATORY").items() if not k.startswith(("b_act_", "b_lvl_"))}
    row.update(sync.to_row("PREPARATORY", data, lk))         # what the workbook shows: the first activity's answers
    b, errors = part_b("PREPARATORY", data, row, lk)
    assert errors == []
    assert [x["id"] for x in b["formdata"]] == ["1001_85_1", "1001_91_2"]
    assert all(is_manual(x) for x in b["formdata"])                   # bank copies become manual ones
    assert b["formdata"][1]["dt"]["sa"] == [3] * 8                     # the second keeps its own answers


def test_changed_activity_gets_the_students_answers_and_others_keep_theirs():
    a = portal_activity(85, SUBJ[:5], sa=[2] * 8, n=1)
    b2 = portal_activity(91, SUBJ[5:], sa=[3] * 8, n=2)
    data = student_with(a, b2)
    lk = lookups_with(91, 93)
    row = grid_row(**{s: ("P85", "Proficient", "Proficient", "Proficient") for s in SUBJ[:5]},
                   PSLS6=("P91", "Advanced", "Advanced", "Advanced"), PSLS7=("P93", "Beginner", "Beginner", "Beginner"))
    row.update({f"b_self_{i}": "No" for i in range(1, 9)})            # the student's answers in Excel
    b, errors = part_b("PREPARATORY", data, row, lk)
    assert errors == []
    acts = b["formdata"]
    assert [x["dt"]["domain"] for x in acts] == [SUBJ[:5], ["PSLS6"], ["PSLS7"]]
    assert acts[0]["id"] == "1001_85_1" and acts[1]["id"] == "1001_91_2" and is_manual(acts[2]) and acts[2]["nm"] == "Bank 93"
    assert acts[0]["dt"]["sa"] == [2] * 8                     # first activity: Excel answers (2 = No)
    assert acts[1]["dt"]["sa"] == [2] * 8 and acts[2]["dt"]["sa"] == [2] * 8   # changed and new: the student's answers
    assert acts[1]["dt"]["awr"][3] == "advance"


def test_an_activity_is_only_removed_with_replace():
    data = student_with(portal_activity(85, SUBJ[:5], n=1), portal_activity(91, SUBJ[5:], n=2, nm="Old one"))
    lk = lookups_with(91)
    row = grid_row()                                         # every subject on 85: activity 91 is no longer used
    _, errors = part_b("PREPARATORY", data, row, lk)
    assert len(errors) == 1 and "would remove activity 'Old one'" in errors[0] and "Replace activities" in errors[0]
    b, errors = part_b("PREPARATORY", data, {**row, grid.REPLACE_KEY: "Yes"}, lk)
    assert errors == [] and [x["id"] for x in b["formdata"]] == ["1001_85_1"] and b["formdata"][0]["dt"]["domain"] == SUBJ


def test_overlapping_activities_are_locked_until_replace():
    data = student_with(portal_activity(85, SUBJ, n=1), portal_activity(91, ["PSLS4"], n=2))
    lk = lookups_with(91)
    now = grid.current(SUBJ, data.raw_parts["part_b"])
    assert now.locked and now.values[grid.act_key("PSLS4")] == "P85"           # the first activity is shown
    row = grid_row(PSLS4=("P91", "Advanced", "Advanced", "Advanced"))
    _, errors = part_b("PREPARATORY", data, row, lk)
    assert len(errors) == 1 and "share subjects" in errors[0]
    b, errors = part_b("PREPARATORY", data, {**row, grid.REPLACE_KEY: "Yes"}, lk)
    assert errors == [] and [x["dt"]["domain"] for x in b["formdata"]] == [[s for s in SUBJ if s != "PSLS4"], ["PSLS4"]]


def test_unchanged_locked_student_is_left_alone():
    data = student_with(portal_activity(85, SUBJ, n=1), portal_activity(91, ["PSLS4"], n=2))
    lk = lookups_with(91)
    row = {k: v for k, v in filled_row("PREPARATORY").items() if not k.startswith(("b_act_", "b_lvl_"))}
    b, errors = part_b("PREPARATORY", data, row, lk)
    assert errors == [] and len(b["formdata"]) == 2


def test_missing_choices_are_listed_by_subject():
    row = grid_row(PSLS3=("", "", "", ""), PSLS5=("P85", "Advanced", "", ""))
    _, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), row, make_lookups("PREPARATORY"))
    assert errors == ["Part B - Activity: No activity chosen for: Mathematics",
                      "Part B - Activity: Levels not chosen for: Art Education (Sensitivity, Creativity)"]


def test_blank_levels_come_from_part_c():
    row = grid_row()
    for s in SUBJ:
        for ability, _ in grid.ABILITIES:
            row.pop(grid.level_key(s, ability))
    for s in SUBJ:                                            # Part C: Proficient, Proficient, Advanced
        row.update({f"c_{s}_awareness": "Proficient", f"c_{s}_sensitivity": "Proficient", f"c_{s}_creativity": "Advanced"})
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), row, make_lookups("PREPARATORY"))
    assert errors == []
    assert [b["formdata"][0]["dt"][k][3] for k in ("awr", "sen", "cre")] == ["proficient", "proficient", "advance"]


def test_picture_activity_cannot_be_added_but_can_be_kept():
    lk = make_lookups("PREPARATORY")

    def resolve(key):
        if key == "P1":
            return {"portal_id": 1, "caption": "Has pictures", "content": BANK_CONTENT, "usable": False,
                    "reason": "Has pictures - choose it on the PARAKH website instead."}
        return grid.resolver_from_lookups(lk)(key)
    _, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), grid_row(PSLS1=("P1", "Advanced", "Advanced", "Advanced")), lk, resolve)
    assert errors == ["Part B - Activity: 'Has pictures' cannot be added: Has pictures - choose it on the PARAKH website instead."]

    data = student_with(portal_activity(1, SUBJ, n=1))           # already on the card: kept, levels can change
    b, errors = part_b("PREPARATORY", data, grid_row(**{s: ("P1", "Advanced", "Advanced", "Advanced") for s in SUBJ}), lk, resolve)
    assert errors == [] and b["formdata"][0]["id"] == "1001_1_1" and b["formdata"][0]["dt"]["awr"][3] == "advance"


def test_teachers_own_parakh_activity_also_goes_on_as_manual():
    lk = make_lookups("PREPARATORY")

    def resolve(key):
        if key == "T40321":
            return {"portal_id": 40321, "caption": "My role play", "content": BANK_CONTENT, "is_global": False, "usable": True}
        return None
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), grid_row(**{s: ("T40321", "Beginner", "Beginner", "Beginner") for s in SUBJ}), lk, resolve)
    assert errors == []
    assert b["act_bank_map"] == [] and is_manual(b["formdata"][0]) and b["formdata"][0]["nm"] == "My role play"


def test_middle_takes_the_approach_from_the_activity_and_keeps_student_answers():
    row = filled_row("MIDDLE")
    payloads, errors = sync.build_payloads("MIDDLE", blank_student("MIDDLE"), row, make_lookups("MIDDLE"))
    assert errors == []
    dt = next(p for p in payloads if p["hpc_col"] == "part_b")["formdata"][0]["dt"]
    assert dt["activity"] == [1] and dt["ast"] == [2] and dt["slr"] == ["1", "2", "3"]


def test_new_activity_ids_never_clash_with_kept_ones():
    data = student_with(portal_activity(85, ["PSLS1"], n=2))     # an id with n=2 already used
    data.raw_parts["part_b"][0]["id"] = "1001_88_2"
    row = grid_row(**{s: ("P85", "Beginner", "Beginner", "Beginner") for s in SUBJ[1:]},
                   PSLS1=("P85", "Proficient", "Proficient", "Proficient"))
    b, errors = part_b("PREPARATORY", data, row, make_lookups("PREPARATORY"))
    assert errors == []
    ids = [a["id"] for a in b["formdata"]]
    assert ids[0] == "1001_88_2" and len(set(ids)) == len(ids)


def test_check_value_messages():
    assert grid.check_value("b_act_PSLS1", "85: something") == "Choose an activity from the list."
    assert grid.check_value("b_lvl_PSLS1_awareness", "Expert") == "Choose Beginner, Proficient or Advanced."
    assert grid.check_value("b_lvl_PSLS1_awareness", "") is None and grid.check_value("b_act_PSLS1", "T40321") is None



# ---------------------------------------------------------------------------
# Edited activities and activities made in this app
# ---------------------------------------------------------------------------

EDITED = {**copy.deepcopy(BANK_CONTENT), "desc": ["Our own way.", "Our own question?"],
          "awr": ["new b", "new p", "new a", ""]}


def edited_resolver(modified=True):
    def resolve(key):
        if key == "P85":
            return {"portal_id": 85, "caption": "Bank 85", "content": EDITED if modified else BANK_CONTENT,
                    "is_global": True, "usable": True, "modified": modified}
        return None
    resolve.typed = {"Bank 85": "P85"} if modified else {}
    return resolve


def is_manual(act):
    """PARAKH's "Create Manually" kind, as its Part B page saves it: no bank id, no is_global, is_modified true."""
    return act["dt"]["act_bank_id"] is None and "is_global" not in act["dt"] and act["is_modified"] is True


def test_an_edited_activity_goes_on_the_card_as_a_manual_one_not_global():
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), grid_row(), make_lookups("PREPARATORY"), edited_resolver())
    assert errors == []
    act = b["formdata"][0]
    assert is_manual(act) and act["nm"] == "Bank 85" and act["is_complete"]
    assert act["dt"]["desc"] == ["Our own way.", "Our own question?"] and act["dt"]["awr"] == ["new b", "new p", "new a", "proficient"]
    assert b["act_bank_map"] == [] and "global_activity_bank_id" not in b


def test_editing_updates_cards_that_already_have_the_activity_but_keeps_the_students_answers():
    data = student_with(portal_activity(85, SUBJ, sa=[2] * 8))
    lk = make_lookups("PREPARATORY")
    b, errors = part_b("PREPARATORY", data, grid_row(), lk, edited_resolver())
    assert errors == []
    act = b["formdata"][0]
    assert act["id"] == "1001_85_1" and is_manual(act)                 # was picked from the bank, now manual
    assert act["dt"]["desc"][0] == "Our own way." and act["dt"]["awr"][3] == "proficient"
    assert act["dt"]["tfob"] == "kept notes"                     # the student's answers still come from the row
    # read back from PARAKH: the manual copy is found again by its name, and a second save changes nothing
    resolve = edited_resolver()
    data = student_with(*b["formdata"])
    assert grid.current(SUBJ, data.raw_parts["part_b"], resolve.typed).values["b_act_PSLS1"] == "P85"
    plan = grid.plan(SUBJ, dict(zip(SUBJ, PREP.SUBJECTS)), PREP.ACTIVITY_GRID, data.raw_parts["part_b"], grid_row(), resolve)
    assert plan.errors == [] and [c["action"] for c in plan.changes] == ["keep"]
    assert not grid.stale_texts(data.raw_parts["part_b"], grid.current(SUBJ, data.raw_parts["part_b"], resolve.typed), resolve)
    # nothing edited: the bank copy still becomes a manual one, with the bank's texts
    data = student_with(portal_activity(85, SUBJ))
    b, errors = part_b("PREPARATORY", data, grid_row(), lk, edited_resolver(modified=False))
    act = b["formdata"][0]
    assert errors == [] and act["id"] == "1001_85_1" and is_manual(act)
    assert act["dt"]["desc"] == BANK_CONTENT["desc"] and act["dt"]["awr"][:3] == BANK_CONTENT["awr"][:3]


def local_resolver():
    content = {"gl": ["L1CG1"], "cpt": ["L1C1.1"], "desc": ["Retell a story.", "Can you tell it again?"],
               "awr": ["ab", "ap", "aa"], "sen": ["sb", "sp", "sa"], "cre": ["cb", "cp", "ca"]}

    def resolve(key):
        if key == "Lstory":
            return {"portal_id": None, "caption": "Story circle", "content": content, "is_global": False,
                    "usable": True, "modified": False}
        return edited_resolver(False)(key)
    resolve.typed = {"Story circle": "Lstory"}
    return resolve


def test_an_activity_made_here_goes_on_the_card_typed_and_is_recognised_again():
    lk = make_lookups("PREPARATORY")
    resolve = local_resolver()
    row = grid_row(**{s: ("Lstory", "Advanced", "Proficient", "Beginner") for s in SUBJ})
    b, errors = part_b("PREPARATORY", blank_student("PREPARATORY"), row, lk, resolve)
    assert errors == []
    act = b["formdata"][0]
    assert act["nm"] == "Story circle" and is_manual(act)
    assert act["dt"]["desc"] == ["Retell a story.", "Can you tell it again?"] and act["dt"]["awr"] == ["ab", "ap", "aa", "advance"]
    assert act["is_complete"] and b["act_bank_map"] == [] and "global_activity_bank_id" not in b

    # read back from PARAKH: shown as the same activity, and saving again keeps it (no "would remove")
    data = student_with(*b["formdata"])
    now = grid.current(SUBJ, data.raw_parts["part_b"], resolve.typed)
    assert now.values["b_act_PSLS1"] == "Lstory" and now.values["b_lvl_PSLS1_awareness"] == "Advanced"
    again, errors = part_b("PREPARATORY", data, row, lk, resolve)
    assert errors == [] and again["formdata"][0]["id"] == act["id"]



# ---------------------------------------------------------------------------
# A teacher removes their version: the app's own manual copy gets the bank's texts and stays manual
# ---------------------------------------------------------------------------

def manual_copy(act_id="1001_85_1", nm="Bank 85"):
    """A manual copy on the card, as this app writes it for an edited bank activity."""
    b, _ = part_b("PREPARATORY", blank_student("PREPARATORY"), grid_row(), make_lookups("PREPARATORY"), edited_resolver())
    act = copy.deepcopy(b["formdata"][0])
    act["id"], act["nm"] = act_id, nm
    return act


def unedited_resolver(owned):
    resolve = edited_resolver(modified=False)
    base = resolve

    def with_key(key):
        entry = base(key)
        return {**entry, "key": key} if entry else None
    with_key.typed, with_key.owned = {}, owned
    return with_key


def test_after_the_teachers_version_is_removed_the_apps_manual_copy_gets_the_bank_texts():
    data = student_with(manual_copy())
    resolve = unedited_resolver({"1001_85_1": "P85"})
    names = grid.typed_keys(resolve)
    now = grid.current(SUBJ, data.raw_parts["part_b"], names)
    assert now.values["b_act_PSLS1"] == "P85"                          # recognised by its recorded id
    assert grid.stale_texts(data.raw_parts["part_b"], now, resolve)    # so a save updates the card
    b, errors = part_b("PREPARATORY", data, grid_row(), make_lookups("PREPARATORY"), resolve)
    assert errors == []
    act = b["formdata"][0]
    assert act["id"] == "1001_85_1" and act["nm"] == "Bank 85"
    assert is_manual(act)
    assert act["dt"]["desc"] == BANK_CONTENT["desc"] and act["dt"]["awr"] == BANK_CONTENT["awr"][:3] + ["proficient"]
    assert act["dt"]["tfob"] == "kept notes" or act["dt"]["tfob"] == data.raw_parts["part_b"][0]["dt"]["tfob"]
    assert b["act_bank_map"] == []
    plan = grid.plan(SUBJ, dict(zip(SUBJ, PREP.SUBJECTS)), PREP.ACTIVITY_GRID, copy.deepcopy(data.raw_parts["part_b"]), grid_row(), resolve)
    assert [c["action"] for c in plan.changes] == ["update"]           # shown before saving


def test_a_manual_activity_the_app_did_not_write_is_left_alone():
    data = student_with(manual_copy(act_id="1001_0_1"))                  # same name, but not in the record
    resolve = unedited_resolver({"9999_85_1": "P85"})
    now = grid.current(SUBJ, data.raw_parts["part_b"], grid.typed_keys(resolve))
    assert now.values.get("b_act_PSLS1", "") == ""                      # not taken for the bank activity
    assert not grid.stale_texts(data.raw_parts["part_b"], now, resolve)
    b, errors = part_b("PREPARATORY", data, grid_row(), make_lookups("PREPARATORY"), resolve)
    assert any("Saving would remove activity 'Bank 85'" in e for e in errors)   # the teacher decides (Replace)
    assert data.raw_parts["part_b"][0]["dt"]["act_bank_id"] is None


def test_the_record_keeps_manual_copies_and_forgets_bank_linked_ones():
    from backend.services import own_activities
    manual = manual_copy()
    own_activities.remember("teacher_x", [manual, {"id": "1001_0_9", "nm": "Typed on PARAKH", "dt": {"act_bank_id": None}}],
                            {"Bank 85": "P85"})
    assert own_activities.load("teacher_x") == {"1001_85_1": "P85"}
    back = copy.deepcopy(manual)
    back["dt"]["act_bank_id"] = 85
    own_activities.remember("teacher_x", [back], {})
    assert own_activities.load("teacher_x") == {}


def test_middle_own_activity_carries_its_approach_and_is_finished():
    mid = get_stage("MIDDLE")
    content = {"gl": ["SCG1"], "cpt": ["SC1.1"], "desc": ["Build a model.", "What did you find?"],
               "awr": ["ab", "ap", "aa"], "sen": ["sb", "sp", "sa"], "cre": ["cb", "cp", "ca"],
               "approaches": [1], "any-other": ""}

    def resolve(key):
        if key == "Lmid":
            return {"portal_id": None, "caption": "LIVE TEST Middle", "content": content, "is_global": False,
                    "usable": True, "modified": False}
        return None
    resolve.typed = {"LIVE TEST Middle": "Lmid"}
    row = {k: v for k, v in filled_row("MIDDLE").items() if not k.startswith(("b_act_", "b_lvl_"))}
    for s in mid.DOMAINS:
        row[grid.act_key(s)] = "Lmid"
        for ability, _ in grid.ABILITIES:
            row[grid.level_key(s, ability)] = "Proficient"
    payloads, errors = sync.build_payloads("MIDDLE", blank_student("MIDDLE"), row, make_lookups("MIDDLE"), resolve)
    assert [e for e in errors if e.startswith("Part B")] == []
    act = next(p for p in payloads if p["hpc_col"] == "part_b")["formdata"][0]
    assert act["dt"]["act_bank_id"] is None and act["is_modified"] is True and act["is_complete"]
    assert act["dt"]["activity"] == [1] and act["dt"]["desc"] == ["Build a model.", "What did you find?"]
