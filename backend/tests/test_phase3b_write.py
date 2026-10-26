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

    def _request(self, method, path, **kwargs):
        if method.upper() == "PATCH":
            payload = kwargs["json"]
            if self.reset_to:
                payload = {**payload, "current_part": self.reset_to}
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
