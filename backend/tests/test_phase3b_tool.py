"""The phase 3b stage 1 tool: read only by construction, names masked, snapshot taken (fake PARAKH)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.hpc import portal
from backend.tests.conftest import FakePortal, blank_student, make_lookups

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import phase3b  # noqa: E402


def test_only_get_requests_can_leave(monkeypatch):
    sent = []
    monkeypatch.setattr(portal.Portal, "_request", lambda self, method, path, **kw: sent.append((method, path)) or {"data": {}})
    client = portal.Portal(portal.Session(access_token="x", staff={}))
    monkeypatch.setattr(phase3b.hpc_sessions, "portal_for", lambda kind, i: client)
    monkeypatch.setattr(phase3b, "SessionLocal", lambda: _FakeDb())
    ro = phase3b.read_only_client("t1")
    ro._request("GET", "/captcha")
    with pytest.raises(phase3b.ReadOnly):
        ro._request("PATCH", "/states/jk/hpc/2627/PREPARATORY/1001")
    with pytest.raises(phase3b.ReadOnly):
        ro._request("post", "/anything")
    with pytest.raises(phase3b.ReadOnly):
        ro.save_part("Preparatory", "1001", {})
    assert sent == [("GET", "/captcha")]                       # nothing else was sent


class _FakeDb:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, model, key):
        return SimpleNamespace(id=key)


def test_preview_masks_names_takes_a_snapshot_and_restore_preview_finds_changes(monkeypatch, tmp_path, capsys):
    data = blank_student("PREPARATORY", "1001")
    a1 = {"basic": [""] * 11, "gen": [""] * 26, "attn": {"1": [""] * 13, "2": [""] * 13, "3": [""] * 13, "4": ""},
          "ints": [], "spec": ""}
    a1["gen"][16], a1["gen"][24] = "Kashmiri", "Parent Fullname"
    data.raw_parts["part_a1"] = json.dumps(a1)
    fake = FakePortal({("PREPARATORY", "1001"): {"record": data.record, "parts": data.raw_parts}})
    monkeypatch.setattr(phase3b, "read_only_client", lambda teacher_id: fake)
    monkeypatch.setattr(phase3b, "Lookups", lambda client, code: make_lookups("PREPARATORY", fake))
    monkeypatch.setattr(phase3b.snapshots, "SNAPSHOT_DIR", tmp_path)
    args = SimpleNamespace(teacher="t1", stage="Preparatory", student="1001", snapshot=None)

    assert phase3b.preview(args) == 0
    out = capsys.readouterr().out
    assert "Mother Tongue: Kashmiri" in out and "(hidden, 15 characters)" in out
    assert "Parent Fullname" not in out and "TEST STUDENT" not in out          # names never printed
    assert "Nothing was saved" in out and fake.saved == []
    assert len(list(tmp_path.rglob("*.json"))) == 1

    phase3b.restore_preview(args)
    assert "A restore would change nothing" in capsys.readouterr().out

    a1["gen"][16] = "Urdu"                                                    # PARAKH changed after the snapshot
    fake.students[("PREPARATORY", "1001")]["parts"]["part_a1"] = json.dumps(a1)
    phase3b.restore_preview(args)
    out = capsys.readouterr().out
    assert "Mother Tongue: now 'Urdu' -> restore 'Kashmiri'" in out and fake.saved == []
