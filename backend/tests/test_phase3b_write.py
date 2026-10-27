"""The stage 2 write tool against a fake PARAKH: no-op A1 save, and the full restore ending at 'mc'."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.hpc import sync
from backend.hpc.portal import PortalError
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import phase3b_write as w  # noqa: E402


class ClientLikePortal(FakePortal):
    """Saves go through _request like the real client, so the one-write guard sees them."""
    status = "COMPLETED"
    reset_to = None                     # set to "A2" to act like a page that resets the card's progress
    alter_b = False                     # set to act like a PARAKH that stores Part B differently

    def _request(self, method, path, **kwargs):
        if method.upper() == "PATCH":
            payload = kwargs["json"]
            if self.reset_to:
                payload = {**payload, "current_part": self.reset_to}
            if self.alter_b and payload.get("hpc_col") == "part_b":
                payload = copy.deepcopy(payload)
                payload["formdata"][0]["is_modified"] = False
            FakePortal.save_part(self, "Preparatory", path.rsplit("/", 1)[-1], payload)
            self.last_status = 200
            return {"success": True, "message": "Updated", "data": {"id": 1}}
        raise AssertionError(f"unexpected {method}")

    def save_part(self, stage, student_id, payload):
        return self._request("PATCH", f"/states/jk/hpc/2627/PREPARATORY/{student_id}", json=payload)

    def roster(self, stage):
        return [{**r, "hpc_status": self.status} for r in FakePortal.roster(self, stage)]


def completed_card():
    data = blank_student("PREPARATORY", "1001")
    payloads, errors = sync.build_payloads("PREPARATORY", data, filled_row("PREPARATORY"), make_lookups("PREPARATORY"))
    assert errors == []
    parts = {p["hpc_col"]: copy.deepcopy(p["formdata"]) for p in payloads}
    record = {**data.record, "current_part": "mc", "cond_class": "grd5"}
    record["stu_info"] = {**record["stu_info"], "med_inst": 3, "location_id": 1}
    return ClientLikePortal({("PREPARATORY", "1001"): {"record": record, "parts": parts}})


@pytest.fixture
def setup(monkeypatch):
    fake = completed_card()
    monkeypatch.setattr(w, "client_for", lambda teacher_id: fake)
    monkeypatch.setattr(w, "Lookups", lambda client, code: make_lookups("PREPARATORY", fake))
    args = SimpleNamespace(teacher="t1", stage="Preparatory", student="1001", snapshot=None, confirm="SAVE")
    return fake, args


def test_noop_a1_sends_one_identical_request_and_reports_it(setup, capsys):
    fake, args = setup
    before = copy.deepcopy(fake.students[("PREPARATORY", "1001")])
    assert w.noop_a1(args) == 0
    out = capsys.readouterr().out
    assert len(fake.saved) == 1
    _, _, sent = fake.saved[0]
    assert sent["hpc_col"] == "part_a1" and sent["current_part"] == "mc"
    assert sent["formdata"] == before["parts"]["part_a1"]
    assert fake.students[("PREPARATORY", "1001")] == before
    for line in ("cond_class: sending 'grd5', PARAKH holds 'grd5' -> same", "med_inst: sending 3, PARAKH holds 3 -> same",
                 "location_id: sending 1, PARAKH holds 1 -> same", "HTTP status 200", "success=True",
                 "Write requests sent: 1 (PATCH)", "class list status 'COMPLETED'", "All checks passed"):
        assert line in out, line
    assert "TEST STUDENT" not in out                                   # no names in the output


def test_refuses_when_extra_values_differ_and_never_sends_a_second_write(setup):
    fake, args = setup
    fake.students[("PREPARATORY", "1001")]["record"]["stu_info"]["med_inst"] = 4    # PARAKH says something else
    with pytest.raises(SystemExit) as exc:
        w.noop_a1(args)
    assert "med_inst differs" in str(exc.value) and fake.saved == []

    client = completed_card()
    writes = w.guard_one_write(client)
    client.save_part("Preparatory", "1001", {"hpc_col": "part_a1", "formdata": "{}", "current_part": "mc"})
    with pytest.raises(PortalError):
        client.save_part("Preparatory", "1001", {"hpc_col": "part_a2", "formdata": "{}", "current_part": "mc"})
    assert len(writes) == 1 and len(client.saved) == 1                 # the second never left


def test_nothing_is_sent_without_confirm_or_when_a1_would_differ(setup):
    fake, args = setup
    with pytest.raises(SystemExit):
        w.noop_a1(SimpleNamespace(**{**vars(args), "confirm": ""}))
    stored = fake.students[("PREPARATORY", "1001")]["parts"]
    stored["part_a1"] = json.dumps(json.loads(stored["part_a1"]), indent=1)
    with pytest.raises(SystemExit) as exc:
        w.noop_a1(args)
    assert "byte-for-byte" in str(exc.value) and fake.saved == []


def test_status_change_stops_shows_the_plan_and_the_restore_puts_everything_back(setup, capsys):
    fake, args = setup
    original = copy.deepcopy(fake.students[("PREPARATORY", "1001")])
    fake.reset_to = "A2"
    assert w.noop_a1(args) == 2
    out = capsys.readouterr().out
    assert "current part: 'mc' -> 'A2'" in out and "STOP" in out and "Restore from snapshot" in out
    assert "Nothing was sent (plan only)" in out and len(fake.saved) == 1        # only the one A1 request

    fake.reset_to = None
    fake.saved.clear()
    del fake._request, fake.refresh            # the restore is its own run: a fresh connection without the 2a guard
    assert w.restore_plan(SimpleNamespace(**{**vars(args), "confirm": "RESTORE"}), send=True) == 0
    assert [p["current_part"] for _, _, p in fake.saved] == ["A2", "A3", "B", "C", "D", "mc"]
    assert fake.saved[-1][2]["hpc_status"] == "COMPLETED"
    assert fake.students[("PREPARATORY", "1001")]["parts"] == original["parts"]
    assert fake.students[("PREPARATORY", "1001")]["record"]["current_part"] == "mc"



# ---------------------------------------------------------------------------
# Live test steps 2-4: one Part B request built by the real save code
# ---------------------------------------------------------------------------

from backend.services import own_activities  # noqa: E402
from backend.tests.conftest import BANK_CONTENT  # noqa: E402

CAPTION = "Conversation in pairs"
EDITED = {**copy.deepcopy(BANK_CONTENT), "desc": [BANK_CONTENT["desc"][0], "What did you say? (test)"]}


def library(modified, owner="teacher_t1"):
    """A stand-in for the teacher's Activity Library: P85, edited or not, with the app's record of its own copies."""
    def resolve(key):
        if key != "P85":
            return None
        return {"portal_id": 85, "caption": CAPTION, "content": EDITED if modified else BANK_CONTENT, "is_global": True,
                "usable": True, "modified": modified, "key": "P85"}
    resolve.typed = {CAPTION: "P85"} if modified else {}
    resolve.owned = own_activities.load(owner)
    resolve.remember = lambda fd: own_activities.remember(owner, fd, resolve.typed)
    return resolve


@pytest.fixture
def part_b_setup(setup, monkeypatch):
    fake, args = setup
    state = {"modified": True}
    monkeypatch.setattr(w, "resolver_for", lambda teacher, stage, lookups: library(state["modified"]))
    dashboard = {k: v for k, v in filled_row("PREPARATORY").items() if k.startswith("b_")}
    monkeypatch.setattr(w, "dashboard_for", lambda teacher, session, stage, sid, lookups: dict(dashboard))
    return fake, args, state


def stored_b(fake):
    fd = fake.students[("PREPARATORY", "1001")]["parts"]["part_b"]
    return json.loads(fd) if isinstance(fd, str) else fd


def test_part_b_plan_shows_the_manual_copy_and_sends_nothing(part_b_setup, capsys):
    fake, args, _ = part_b_setup
    assert w.part_b_plan(args) == 0
    out = capsys.readouterr().out
    assert "On PARAKH now:" in out and "from the bank #85 (global)" in out
    assert "The app would send:" in out and "MANUAL (no bank number), is_modified=True, library P85" in out
    assert "act_bank_map: []" in out and "Would send ONE request: part_b, current part 'mc'" in out
    assert "Nothing was sent" in out and fake.saved == []


def test_step2_edited_activity_goes_on_as_manual_and_step4_takes_it_back_to_the_bank(part_b_setup, capsys):
    fake, args, state = part_b_setup
    original = copy.deepcopy(fake.students[("PREPARATORY", "1001")])
    assert w.part_b_save(args) == 0
    out = capsys.readouterr().out
    assert len(fake.saved) == 1 and fake.saved[0][2]["hpc_col"] == "part_b" and fake.saved[0][2]["current_part"] == "mc"
    assert "hpc_status" not in fake.saved[0][2]
    act = stored_b(fake)[0]
    assert act["dt"]["act_bank_id"] is None and "is_global" not in act["dt"] and act["is_modified"] is True
    assert act["dt"]["desc"][1] == "What did you say? (test)"
    for line in ("Write requests sent: 1 (PATCH)", "On PARAKH after the save:", "MANUAL (no bank number)",
                 "Other parts and current part, compared with before: no differences",
                 "Part B as stored, compared with what was sent: no differences", "All checks passed"):
        assert line in out, line
    assert "TEST STUDENT" not in out
    assert own_activities.load("teacher_t1") == {act["id"]: "P85"}     # the app knows this manual copy is its own
    others = {k: v for k, v in fake.students[("PREPARATORY", "1001")]["parts"].items() if k != "part_b"}
    assert others == {k: v for k, v in original["parts"].items() if k != "part_b"}

    # step 4: the teacher removes their version -> the same card activity is the bank one again
    state["modified"] = False
    fake.saved.clear()
    del fake._request, fake.refresh           # each step is its own run (fresh connection, fresh guard)
    assert w.part_b_save(args) == 0
    back = stored_b(fake)[0]
    assert back["id"] == act["id"] and back["dt"]["act_bank_id"] == 85 and back["dt"]["is_global"] is True
    assert back["is_modified"] is False and back["dt"]["desc"] == BANK_CONTENT["desc"]
    assert len(fake.saved) == 1 and own_activities.load("teacher_t1") == {}


def test_part_b_is_not_sent_when_nothing_would_change(part_b_setup):
    fake, args, state = part_b_setup
    state["modified"] = False
    with pytest.raises(SystemExit) as exc:
        w.part_b_save(args)
    assert "would not change" in str(exc.value) and fake.saved == []
    with pytest.raises(SystemExit):
        w.part_b_save(SimpleNamespace(**{**vars(args), "confirm": ""}))


def test_part_b_stops_with_the_restore_plan_when_parakh_stores_something_else(part_b_setup, capsys):
    fake, args, _ = part_b_setup
    fake.alter_b = True
    assert w.part_b_save(args) == 2
    out = capsys.readouterr().out
    assert "PARAKH stored something else than was sent" in out and "STOP" in out
    assert "Restore from snapshot" in out and "Nothing was sent (plan only)" in out and len(fake.saved) == 1
