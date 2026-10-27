"""M-6: an upload larger than the limit is refused and nothing of it is kept."""
import uuid

from fastapi.testclient import TestClient

API = "/api/v1"
HDR = {"X-Requested-With": "TeacherAssist"}


def _teacher(tmp_path, monkeypatch):
    from backend.main import app
    from backend.services import hpc_sessions
    monkeypatch.setattr(hpc_sessions, "SESSIONS_DIR", tmp_path / "sessions")
    tag = uuid.uuid4().hex[:8]
    udise = str(int(tag, 16) % 10**11).zfill(11)
    c = TestClient(app)
    c.headers.update(HDR)
    c.post(f"{API}/auth/school/register", json={"udise_code": udise, "school_name": "Size School", "state": "Test",
           "district": "Test", "admin_name": "Size Admin", "admin_email": f"sz.{tag}@example.com", "password": "secret123"})
    c.post(f"{API}/auth/login", json={"identifier": udise, "password": "secret123"})
    c.post(f"{API}/school/teachers", json={"teacher_name": "Size Teacher", "username": f"size{tag}", "password": "secret123",
                                           "assigned_stages": ["Preparatory"]})
    c.post(f"{API}/auth/login", json={"identifier": f"size{tag}", "password": "secret123"})
    return c


def test_a_file_over_the_limit_is_refused_and_not_kept(tmp_path, monkeypatch):
    from backend import config
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1024 * 1024)
    c = _teacher(tmp_path, monkeypatch)
    r = c.post(f"{API}/teacher/upload/validate", files={"file": ("big.xlsx", b"x" * (1024 * 1024 + 1))})
    assert r.status_code == 413 and "1 MB" in r.json()["detail"]
    assert not list((tmp_path / "sessions").rglob("uploaded_*"))


def test_the_default_limit_is_20_mb_and_upper_case_xlsx_is_accepted(tmp_path, monkeypatch):
    from backend import config
    assert config.MAX_UPLOAD_BYTES == 20 * 1024 * 1024
    c = _teacher(tmp_path, monkeypatch)
    r = c.post(f"{API}/teacher/upload/validate", files={"file": ("CLASS.XLSX", b"not a workbook")})
    assert r.status_code == 400 and "could not be opened" in r.json()["detail"]      # damaged: a clear answer, no crash
