"""The stage 2 write tool against a fake PARAKH: no-op A1 save, and the full restore ending at 'mc'."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.hpc import sync
from backend.tests.conftest import FakePortal, blank_student, filled_row, make_lookups

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import phase3b_write as w  # noqa: E402


def completed_card():
    """A fake PARAKH holding a completed Preparatory card (built with the real save code)."""
    data = blank_student("PREPARATORY", "1001")
    payloads, errors = sync.build_payloads("PREPARATORY", data, filled_row("PREPARATORY"), make_lookups("PREPARATORY"))
    assert errors == []
    parts = {p["hpc_col"]: copy.deepcopy(p["formdata"]) for p in payloads}
    record = {**data.record, "current_part": "mc"}
    return FakePortal({("PREPARATORY", "1001"): {"record": record, "parts": parts}})


@pytest.fixture
def setup(monkeypatch):
    fake = completed_card()
    monkeypatch.setattr(w, "client_for", lambda teacher_id: fake)
    monkeypatch.setattr(w, "Lookups", lambda client, code: make_lookups("PREPARATORY", fake))
    args = SimpleNamespace(teacher="t1", stage="Preparatory", student="1001", snapshot=None, confirm="SAVE")
    return fake, args


def test_noop_a1_sends_one_identical_request_and_keeps_the_status(setup, capsys):
    fake, args = setup
    before = copy.deepcopy(fake.students[("PREPARATORY", "1001")])
    assert w.noop_a1(args) == 0
    assert len(fake.saved) == 1
    _, _, sent = fake.saved[0]
    assert sent["hpc_col"] == "part_a1" and sent["current_part"] == "mc"
    assert sent["formdata"] == before["parts"]["part_a1"]                 # byte-for-byte the stored data
    assert fake.students[("PREPARATORY", "1001")] == before                # PARAKH unchanged
    assert "no differences" in capsys.readouterr().out


def test_nothing_is_sent_without_confirm_or_when_a1_would_differ(setup):
    fake, args = setup
    with pytest.raises(SystemExit):
        w.noop_a1(SimpleNamespace(**{**vars(args), "confirm": ""}))
    stored = fake.students[("PREPARATORY", "1001")]["parts"]
    stored["part_a1"] = json.dumps(json.loads(stored["part_a1"]), indent=1)    # same data, different text
    with pytest.raises(SystemExit) as exc:
        w.noop_a1(args)
    assert "byte-for-byte" in str(exc.value) and fake.saved == []


def test_status_change_stops_and_the_restore_puts_everything_back_ending_at_mc(setup, capsys):
    fake, args = setup
    original = copy.deepcopy(fake.students[("PREPARATORY", "1001")])
    real_save = fake.save_part

    def portal_resets_status(stage, sid, payload):              # what we fear the real page does
        real_save(stage, sid, {**payload, "current_part": "A2"})
    fake.save_part = portal_resets_status
    assert w.noop_a1(args) == 2
    out = capsys.readouterr().out
    assert "current part: 'mc' -> 'A2'" in out and "STOP" in out
    assert fake.students[("PREPARATORY", "1001")]["record"]["current_part"] == "A2"

    fake.save_part = real_save
    fake.saved.clear()
    w.restore_plan(SimpleNamespace(**{**vars(args), "confirm": ""}), send=False)      # plan only: nothing sent
    assert fake.saved == [] and "Nothing was sent" in capsys.readouterr().out
    assert w.restore_plan(SimpleNamespace(**{**vars(args), "confirm": "RESTORE"}), send=True) == 0
    assert [p["hpc_col"] for _, _, p in fake.saved] == ["part_a1", "part_a2", "part_a3", "part_b", "part_c", "hpc_credit"]
    assert [p["current_part"] for _, _, p in fake.saved] == ["A2", "A3", "B", "C", "D", "mc"]
    assert fake.saved[-1][2]["hpc_status"] == "COMPLETED"
    assert fake.students[("PREPARATORY", "1001")] == original             # every part exactly as before
    assert "no differences" in capsys.readouterr().out
