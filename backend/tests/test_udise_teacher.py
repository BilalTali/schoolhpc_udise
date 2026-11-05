"""UDISE+ Teacher module workbook: read (background), where each person stands, workbook, check, save (switched off
until checked on real data). A made-up Teacher service - nothing here reaches UDISE+."""
import copy
import io
import json

import pytest
from openpyxl import load_workbook

from backend.services import udise_teacher as ut
from backend.udise import teacher_forms as tf

FORM1 = {"empName": "ASHA DEVI", "gender": 2, "dob": "1985-04-12", "empCodeState": None, "socialCat": 1, "qualAcad": 5,
         "trade": 11, "qualProf": 3, "mathUpto": 3, "scienceUpto": 3, "englishUpto": 4, "socStudyUpto": 3, "langStudyUpto": 3,
         "mobile": "9000000001", "mobileYN": False, "email": None, "disabilityType": 1, "uidMasking": "1234", "natTchId": "T1"}
FORM2 = {"tchType": 1, "classTaught": 2, "appointedLevel": None, "apptSub": 7, "subTaught1": 7, "subTaught2": None,
         "tchDeputation": 2, "tchFromOtherSchool": 2, "natureOfAppt": 1, "dojService": "2010-06-01", "dojPs": "2018-04-01",
         "docPh": "2010-06-01"}
FORM3 = {k: 1 for k in ("trainedCwsn", "trainedComp", "trgNishtha", "trSsaYn", "cyberSafetyYn", "psySocAspectYn",
                        "receTrainingSupportCwsnYn", "isCapableVc")}
FORM3.update(trngRcvd=1, trngNeeded=None, nontchDays=5, mainLang1=19, mainLang2=None, mainLang3=None, isCtetStet=2, ctetStet=None)


class FakeTeacher:
    store, posts = {}, []

    def __init__(self, *a):
        self.region_id, self.token = 77, {"userStateId": 101}

    def get(self, path, params=None):
        if "teacher-details/77/1" in path:
            return {"teacherDetails": [{"empStaffId": 5, "empName": "ASHA DEVI", "nationalCode": "T1", "formFlag": 2}]}
        if "teacher-details" in path:
            return {"teacherDetails": []}
        if "dropdown/all" in path:
            return {"genders": [{"id": 1, "name": "Male"}, {"id": 2, "name": "Female"}],
                    "qualificationLevels": [{"id": i, "name": f"Level {i}"} for i in range(1, 7)],
                    "degree": [{"id": 11, "name": "B.A."}], "professionalQualifications": [{"id": 3, "name": "B.Ed."}],
                    "disabilities": [{"id": 1, "name": "Not applicable"}], "natureOfAppointments": [{"id": 1, "name": "Regular"}],
                    "teacherTypes": [{"id": 1, "name": "Head Teacher"}], "classesTaught": [{"id": 2, "name": "Primary"}]}
        if "social-category" in path:
            return [{"socialCategoryId": 1, "socialCategoryName": "General"}]
        if "training-received" in path:
            return [{"id": 1, "desc": "Subject knowledge"}]
        if "languages" in path:
            return [{"languageId": 19, "languageName": "English"}]
        if "by-class-and-state" in path:
            return [{"subjectId": 7, "subjectName": "Mathematics"}]
        for k, v in FakeTeacher.store.items():
            if k in path:
                return copy.deepcopy(v)
        return {}

    def post(self, path, body, method="POST"):
        FakeTeacher.posts.append((path, copy.deepcopy(body)))
        form = "form1" if "form1" in path else "form2" if "form2" in path else "form3"
        FakeTeacher.store[f"{form}/"].update({k: v for k, v in body.items() if k in FakeTeacher.store[f"{form}/"]})
        return {"status": "SUCCESS"}


@pytest.fixture
def fake(monkeypatch):
    FakeTeacher.store = {"form1/": dict(FORM1), "form2/": dict(FORM2), "form3/": dict(FORM3)}
    FakeTeacher.posts = []
    monkeypatch.setattr(ut, "_service", lambda school_id: FakeTeacher())
    monkeypatch.setattr(ut.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    assert ut.start("s9")["started"]
    assert ut.JOBS["s9"]["status"] == "COMPLETED", ut.JOBS["s9"]
    return FakeTeacher


def _wb():
    content, _ = ut.excel("s9")
    return load_workbook(io.BytesIO(content))


def _bytes(wb):
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _col(key, staff_type=1, new=False):
    keys = [k for _, k, _, _ in tf.columns(staff_type, new=new)]
    return (1 if new else ut.VISIBLE_FIRST) + 1 + keys.index(key)


def test_status_lists_each_empty_field_with_its_cell(fake):
    st = ut.status("s9")
    assert st["groups"][0]["staff"] == 1 and st["groups"][0]["complete"] == 0
    fields = {n["field"]: n for n in st["needed"]}
    assert "3.2.12 Email" in fields and "If yes, year of qualifying CTET/STET" not in fields      # CTET: answered No
    email = fields["3.2.12 Email"]
    assert email["sheet"] == "Teaching staff" and email["row"] == 5
    wb = _wb()
    assert wb["Teaching staff"].cell(row=3, column=_col("email")).value == "3.2.12 Email"
    assert f"{email['column']}{email['row']}" == wb["Teaching staff"].cell(row=5, column=_col("email")).coordinate


def test_workbook_shows_words_and_dates(fake):
    ws = _wb()["Teaching staff"]
    assert ws.cell(row=5, column=2).value == "ASHA DEVI"
    assert ws.cell(row=5, column=_col("gender")).value == "2 - Female"
    assert ws.cell(row=5, column=_col("dob")).value == "12/04/1985"
    assert ws.cell(row=5, column=_col("subTaught1")).value == "7 - Mathematics"


def test_check_finds_changes_problems_and_new_staff(fake):
    wb = _wb()
    ws = wb["Teaching staff"]
    ws.cell(row=5, column=_col("email")).value = "asha@example.com"
    ws.cell(row=5, column=_col("dojPs")).value = "01/04/2019"
    ws.cell(row=5, column=_col("mobile")).value = "12345"
    new = wb["New staff"]
    new.cell(row=5, column=1).value = "1"
    new.cell(row=5, column=_col("empName", new=True)).value = "RAVI KUMAR"
    new.cell(row=5, column=_col("referenceKey", new=True)).value = "123412341234"
    plan = ut.validate("s9", _bytes(wb), "t.xlsx")
    person = next(p for p in plan["people"] if not p["new"])
    assert {c["key"]: c["new"] for c in person["changes"]} == {"email": "asha@example.com", "dojPs": "01/04/2019"}
    assert person["changes"][0]["cell"].endswith("5") and "Mobile" in person["problems"][0]
    newbie = next(p for p in plan["people"] if p["new"])
    assert any("needed for a new staff member" in m for m in newbie["problems"])
    assert all("1234" not in str(c["new"]) or c["new"].startswith("xxxx") for c in newbie["changes"])
    assert not fake.posts


def test_save_is_off_until_checked_on_real_data(fake):
    wb = _wb()
    wb["Teaching staff"].cell(row=5, column=_col("email")).value = "asha@example.com"
    ut.validate("s9", _bytes(wb), "t.xlsx")
    assert not ut.save("s9")["ok"] and not fake.posts


def test_save_sends_the_page_fields_in_the_date_style_read(fake, monkeypatch):
    monkeypatch.setattr(ut, "SAVE_ENABLED", True)
    wb = _wb()
    ws = wb["Teaching staff"]
    ws.cell(row=5, column=_col("email")).value = "asha@example.com"
    ws.cell(row=5, column=_col("dojPs")).value = "01/04/2019"
    ut.validate("s9", _bytes(wb), "t.xlsx")
    result = ut.save("s9")
    assert [r["status"] for r in result["results"]] == ["saved", "saved"]
    (p1, b1), (p2, b2) = fake.posts
    assert p1.endswith("/emp-staff/form1/77/saveOrUpdate") and b1["email"] == "asha@example.com"
    assert b1["empStaffId"] == 5 and b1["createdFlag"] is False and b1["empName"] == "ASHA DEVI"
    assert "referenceKey" not in b1 and "empNamePerUid" not in b1
    assert p2.endswith("/emp-staff/form2/77/saveOrUpdate") and b2["dojPs"] == "2019-04-01" and b2["empType"] == 1
    hist = ut.status("s9")["updated"]
    assert {h["field"] for h in hist} == {"3.2.12 Email", "Date of joining in present school (DD/MM/YYYY)"}


def test_lists_of_any_shape():
    assert tf.as_options([{"socialCategoryId": 1, "socialCategoryName": "General"}]) == {1: "General"}
    assert tf.as_options({"2": "Rented"}) == {2: "Rented"}
    assert tf.as_options([{"value": 3, "label": "Three"}]) == {3: "Three"}
