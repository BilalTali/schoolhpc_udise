"""UDISE+ School Profile workbook: download, check (nothing sent), save (only edited answers, the page's own fields,
a copy kept first). A made-up Profile service - nothing here reaches UDISE+."""
import copy
import io
import json

import pytest
from openpyxl import load_workbook

from backend.services import udise_profile as up
from backend.udise import bearer
from backend.udise import profile_forms as pf

SCHOOL = {"udiseCode": "01000000001", "schoolName": "TEST SCHOOL", "classFrom": 1, "classTo": 8, "isppsec": 1,
          "smlAcademicYear": "2026-27", "schCategoryId": "2-Primary with Upper Primary"}
META = {"certificationStatus": False, "modifiedBy": "x", "modifiedTime": "2025-10-25 12:54:53", "smlAcademicYear": "2026-27",
        "formStatus": 1}


def _object(form):
    data = {"schoolId": 77, **META}
    for q in pf.questions(form):
        kind = q["kind"]
        data[q["id"]] = (1 if pf.options(kind) is not None and not str(kind).startswith("multi:") else
                         [1] if str(kind).startswith("multi:") else "0" if kind == "classes" else
                         None if kind in ("text", "year") else 0)
    return data


def _table(form):
    return [{"id": {"schoolId": 77, "itemId": item_id}, **{c: 0 for c, _, _ in form["columns"]}, **META}
            for item_id, *_ in form["rows"]]


def _start():
    store = {f["path"]: (_table(f) if f.get("table") else _object(f)) for f in pf.FORMS}
    b = store["facility/form1"]
    b.update(bldStatus=3, bldBlkTot=3, bldBlk=3, noSingleStorey=3, clsrmsPri=2, clsrmsUpr=3, clsrmsPrePri=1, clsrmsGd=6,
             clsrmsNotInst=0, clsrmsInst=6)
    return store


class FakeService:
    store = {}
    posts = []

    def __init__(self, school_id, service, saved):
        self.region_id = 77

    def get(self, path, params=None):
        if path == "/school/77":
            return dict(SCHOOL)
        if path.endswith("options/residential"):
            return {"1": "Ashram (Govt.)", "7": "Model School"}
        if path.endswith("options/schoolBuildingType"):
            return {"2": "Rented", "3": "Government Owned"}
        return copy.deepcopy(FakeService.store[path.replace("/school/77/", "")])

    def post(self, path, body, method="POST"):
        key = path.replace("/school/77/", "")
        FakeService.posts.append((key, copy.deepcopy(body)))
        if isinstance(body, list):
            FakeService.store[key] = [{**r, "modifiedTime": "now"} for r in body]
        else:
            FakeService.store[key] = {**FakeService.store[key], **body}
        return {}


@pytest.fixture
def fake(monkeypatch):
    FakeService.store, FakeService.posts = _start(), []
    monkeypatch.setattr(up, "_service", lambda school_id: FakeService(school_id, "profile", {}))
    return FakeService


def _workbook(school="s1"):
    content, name = up.excel(school)
    return load_workbook(io.BytesIO(content)), name


def _set(wb, form_key, field, value):
    meta = {r[0]: json.loads(r[1]) for r in wb["_meta"].iter_rows(values_only=True)}
    ws = wb[meta["sheets"][form_key]]
    for r in range(5, ws.max_row + 1):
        if ws.cell(row=r, column=5).value == field:
            ws.cell(row=r, column=3).value = value
            return
    raise AssertionError(f"{field} not in the sheet")


def _bytes(wb):
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_workbook_has_every_form_and_only_the_school_classes(fake):
    wb, name = _workbook()
    assert name == "UDISE_School_Profile_01000000001_2026-27.xlsx"
    meta = {r[0]: json.loads(r[1]) for r in wb["_meta"].iter_rows(values_only=True)}
    assert set(meta["sheets"]) == {f["key"] for f in pf.FORMS}
    kpi = wb[meta["sheets"]["kpi"]]
    ids = [kpi.cell(row=r, column=5).value for r in range(5, kpi.max_row + 1)]
    assert "4:c8" in ids and "4:c9" not in ids                       # a class 1-8 school: no class 9-12 columns
    others = wb[meta["sheets"]["others"]]
    row = next(r for r in range(5, others.max_row + 1) if others.cell(row=r, column=5).value == "approachRoadYn")
    assert others.cell(row=row, column=3).value == "1 - Yes"
    assert others.protection.sheet and not others.cell(row=row, column=3).protection.locked


def test_check_lists_changes_and_problems_and_sends_nothing(fake):
    wb, _ = _workbook()
    _set(wb, "others", "approachRoadYn", "2 - No")
    _set(wb, "others", "distancePri", 2.567)
    _set(wb, "tlm", "1:pri", "Yes")
    plan = up.validate("s1", _bytes(wb), "f.xlsx")
    assert plan["ok"] and not fake.posts
    others = next(f for f in plan["forms"] if f["key"] == "others")
    assert [c["item"] for c in others["changes"]] == ["1.37"]
    assert "more than 2 decimals" in others["problems"][0]["message"]
    tlm = next(f for f in plan["forms"] if f["key"] == "tlm")
    assert tlm["changes"][0]["new"] == "1 - Yes" and not tlm["problems"]


def test_save_sends_the_page_fields_with_only_the_edits(fake, monkeypatch):
    monkeypatch.setattr(up, "DATA_DIR", up.DATA_DIR)
    wb, _ = _workbook()
    _set(wb, "others", "approachRoadYn", "2")
    _set(wb, "safety", "stuAtndnc", "1, 3")
    _set(wb, "tlm", "2:uppPri", "5 - May")
    up.validate("s1", _bytes(wb), "f.xlsx")
    result = up.save("s1")
    assert [r["status"] for r in result["results"]] == ["saved", "saved", "saved"]
    sent = dict(fake.posts)
    body = sent["profile/form1"]
    assert body["approachRoadYn"] == 2 and body["schoolId"] == 77
    assert not set(body) & set(pf.NOT_SENT)
    assert {k for k in body if body[k] != _object(pf.BY_KEY["others"]).get(k)} == {"approachRoadYn"}
    assert sent["sch-pgi-details"]["stuAtndnc"] == [1, 3]
    rows = sent["profile/form4"]
    assert next(r for r in rows if r["id"]["itemId"] == 2)["uppPri"] == 5
    assert all("modifiedTime" not in r and "certificationStatus" in r for r in rows)   # rows keep all but the times
    snaps = list((up.DATA_DIR / "snapshots" / "school_s1" / "udise_profile").glob("*_others.json"))
    assert snaps and json.loads(snaps[-1].read_text())["data"]["approachRoadYn"] == 1


def test_an_answer_changed_on_udise_after_download_is_left_alone(fake):
    wb, _ = _workbook()
    _set(wb, "others", "approachRoadYn", "2")
    _set(wb, "others", "cceYn", "2")
    up.validate("s1", _bytes(wb), "f.xlsx")
    fake.store["profile/form1"]["approachRoadYn"] = 9                 # someone changed it on the website meanwhile
    result = up.save("s1")
    body = dict(fake.posts)["profile/form1"]
    assert body["approachRoadYn"] == 9 and body["cceYn"] == 2
    assert result["results"][0]["skipped"] == ["1.37"]


def test_buildings_totals_are_checked_and_filled_like_the_page(fake):
    wb, _ = _workbook()
    _set(wb, "buildings", "noSingleStorey", 4)
    plan = up.validate("s1", _bytes(wb), "f.xlsx")
    assert "storey-wise" in plan["forms"][0]["problems"][0]["message"]
    assert up.save("s1")["results"][0]["status"] == "skipped" and not fake.posts

    wb, _ = _workbook()
    _set(wb, "buildings", "clsrmsPri", 3)
    _set(wb, "buildings", "clsrmsGd", 5)
    _set(wb, "buildings", "clsrmsDptdPucca", 2)
    up.validate("s1", _bytes(wb), "f.xlsx")
    up.save("s1")
    body = dict(fake.posts)["facility/form1"]
    assert body["clsrmsInst"] == 7 and body["clsrmsDptd"] == 2


def test_workbook_for_another_school_or_session_is_refused(fake):
    wb, _ = _workbook()
    SCHOOL["udiseCode"] = "01999999999"
    try:
        assert "is for UDISE code" in up.validate("s1", _bytes(wb), "f.xlsx")["error"]
    finally:
        SCHOOL["udiseCode"] = "01000000001"
    for f in fake.store.values():
        for r in f if isinstance(f, list) else [f]:
            r["smlAcademicYear"] = "2027-28"
    assert "Download a new workbook" in up.validate("s1", _bytes(wb), "f.xlsx")["error"]


def test_answers_in_words_and_back():
    lists = {"building": {3: "Government Owned"}}
    assert up.show("yn", 9, lists) is None and up.show("yn", 0, lists) is None
    assert up.show("opt:building", 3, lists) == "3 - Government Owned"
    assert up.parse("yn3", "Yes, but not functional", lists) == (3, None)
    assert up.parse("classes", "2, 1", lists) == ("1,2", None)
    assert up.parse("num", "-1", lists)[1]
    assert up.parse("year", "2024", lists) == ("2024", None)
    assert up.parse("yn", "  ", lists) == (None, None)


def test_renewed_tokens_are_kept_every_time(monkeypatch):
    kept = []
    monkeypatch.setattr("backend.services.udise_sessions.update_token", lambda s, svc, fresh: kept.append(fresh))
    monkeypatch.setattr("backend.services.udise_sessions.mark_ended", lambda *a: None)
    saved = {"services": {"teacher": {"connected": True, "token": {"accessToken": "old", "refreshToken": "r1",
                                                                    "userRegionId": 5}}}}
    svc = bearer.Service("s1", "teacher", saved)

    class Resp:
        def __init__(self, status, body):
            self.status_code, self._body, self.content, self.ok = status, body, b"x", status < 400

        def json(self):
            return self._body

    calls = []

    def request(method, url, **kw):
        calls.append(kw["headers"]["Authorization"])
        return Resp(401, {"status": "ERROR"}) if len(calls) == 1 else Resp(200, {"ok": 1})

    monkeypatch.setattr(svc.http, "request", request)
    # the Teacher service answers its renewal with status "SUCCESS" (not "success"): the pair is kept all the same
    monkeypatch.setattr(svc.http, "post", lambda *a, **k: Resp(200, {"status": "SUCCESS",
                                                                     "data": {"accessToken": "new", "refreshToken": "r2"}}))
    monkeypatch.setattr(bearer, "PACE", 0)
    assert svc.get("/x") == {"ok": 1}
    assert calls == ["Bearer old", "Bearer new"] and kept == [{"accessToken": "new", "refreshToken": "r2"}]
