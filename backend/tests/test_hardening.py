"""The hardening of the final review: zip bombs, formulas in downloads, security headers."""
import io
import zipfile

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from backend.hpc import xl
from backend.routers.teachers import _csv_text


def _xlsx() -> bytes:
    wb = Workbook()
    wb.active["A1"] = "TEST"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_a_small_upload_that_unpacks_to_gigabytes_is_refused():
    assert xl.unpacked_size_ok(_xlsx())
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/big.xml", b"0" * (xl.MAX_UNPACKED + 1))      # compresses to a few hundred KB
    assert len(bomb.getvalue()) < 1024 * 1024 and not xl.unpacked_size_ok(bomb.getvalue())
    assert not xl.unpacked_size_ok(b"not a zip at all")


def test_names_from_outside_stay_text_in_every_download():
    wb = Workbook()
    wb.active["A1"] = "=HYPERLINK(\"http://x\",\"click\")"
    xl.keep_text(wb)
    out = io.BytesIO()
    wb.save(out)
    assert load_workbook(io.BytesIO(out.getvalue())).active["A1"].data_type == "s"
    assert _csv_text("=1+1") == "'=1+1" and _csv_text("@SUM(A1)") == "'@SUM(A1)" and _csv_text("TEST NAME") == "TEST NAME"
    assert _csv_text(7) == 7


def test_pages_cannot_be_framed_and_load_only_their_own_scripts():
    from backend.main import app
    client = TestClient(app)
    api = client.get("/api/health")
    assert api.headers["x-frame-options"] == "DENY" and api.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" not in api.headers                          # API answers: JSON only
    page = client.get("/some/page")
    if page.headers.get("content-type", "").startswith("text/html"):           # only when the web app is built
        policy = page.headers["content-security-policy"]
        assert "frame-ancestors 'none'" in policy and "script-src 'self'" in policy
