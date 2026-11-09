"""The school's HPC records Excel: every student's card as the app keeps it, in words, without signing in to PARAKH."""
import io
import json

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from backend.config import DATA_DIR
from backend.hpc import sync
from backend.hpc.stages.common import Lookups
from backend.main import app
from backend.services import card_store
from backend.tests.conftest import blank_student, filled_row, make_lookups, session_headers

API = "/api/v1"


def _school_with_teacher(code, email, username):
    c = TestClient(app)
    assert c.post(f"{API}/auth/school/register", json={
        "udise_code": code, "school_name": f"School {code}", "state": "Jammu and Kashmir", "district": "Budgam",
        "admin_name": "Admin", "admin_email": email, "password": "secret123"}).status_code == 201
    h, _ = session_headers(code)
    r = c.post(f"{API}/school/teachers", headers=h, json={"teacher_name": "BILAL TALI", "username": username,
                                                           "password": "secret123", "assigned_stages": ["Preparatory"]})
    assert r.status_code == 201, r.text
    return c, h, r.json()["id"]


def _keep_lists(lk, parakh_school_id, stage):
    folder = DATA_DIR / "lookups"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{parakh_school_id}_{stage}.json").write_text(
        json.dumps({k: getattr(lk, k) for k in Lookups.SNAPSHOT_KEYS}), encoding="utf-8")


def _store_card(teacher_id, student_id, row):
    """A card as the app keeps it after reading it from PARAKH (the parts as a save would write them)."""
    lk = make_lookups("PREPARATORY")
    data = blank_student("PREPARATORY", student_id)
    payloads, _ = sync.build_payloads("PREPARATORY", data, row, lk)
    parts = {p["hpc_col"]: p["formdata"] for p in payloads}
    parts[card_store.RECORD] = data.record
    folder = card_store.CARDS_DIR / f"teacher_{teacher_id}" / "2627" / "preparatory"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{student_id}.json").write_text(json.dumps({"parts": parts, "read_at": {"part_a1": "2026-11-01T09:00:00+00:00"}}),
                                               encoding="utf-8")
    return lk


def test_the_records_excel_has_every_kept_card_in_words():
    c, h, tid = _school_with_teacher("03000000001", "rec1@example.com", "recteach1")
    row = filled_row("PREPARATORY")
    row.pop("a1_mother_tongue")                                        # saved as Kashmiri (the school default)
    lk = _store_card(tid, "7001", row)
    _keep_lists(lk, "1", "preparatory")                                # the school's PARAKH id on the test record is "1"
    r = c.get(f"{API}/school/hpc/records.xlsx", headers=h)
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[0] == "About" and "Prep A1" in wb.sheetnames
    ws = wb["Prep A1"]
    heads = [x.value for x in ws[2]]
    assert heads[:6] == ["PARAKH ID", "Student name", "Class", "Section", "Teacher (copy of)", "Last read from PARAKH"]
    first = [x.value for x in ws[3]]
    assert first[0] == "7001" and first[1] == "TEST STUDENT" and first[4] == "BILAL TALI"
    assert first[heads.index("Mother Tongue")] == "Kashmiri"
    assert first[heads.index("Medium of Instruction")] == "English"                       # a code, put into words
    assert ws["A3"].border.left.style == "thin"                                            # clear borders


def test_nothing_kept_yet_says_so():
    c, h, _ = _school_with_teacher("03000000002", "rec2@example.com", "recteach2")
    r = c.get(f"{API}/school/hpc/records.xlsx", headers=h)
    assert r.status_code == 409 and "no cards" in r.json()["detail"]


def test_a_teacher_cannot_download_the_school_records():
    c, h, _ = _school_with_teacher("03000000003", "rec3@example.com", "recteach3")
    th, _ = session_headers("recteach3")
    assert c.get(f"{API}/school/hpc/records.xlsx", headers=th).status_code in (401, 403)
