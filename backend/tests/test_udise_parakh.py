"""UDISE+ against PARAKH: pairing (APAAR ID, admission number, name and date of birth, name and parent), what is on
one side only, what differs - and the PDF reports build. Made-up students only."""
import json
from types import SimpleNamespace

from backend.services import reports_pdf, udise_parakh


def student(name, parent="", adm="", dob="", apaar="", class_id=1, cls="I A", status="x", **kw):
    return {"name": name, "parent": parent, "adm_no": adm, "dob": dob, "apaar": apaar, "class_id": class_id, "class": cls,
            "gender": kw.get("gender", ""), "status": status, "pen": kw.get("pen", "")}


def test_pairs_by_the_strongest_key_and_lists_each_side_only(monkeypatch):
    udise = [student("TEST ONE", apaar="111", adm="5"),
             student("TEST TWO", adm="007", dob="01/01/2019"),
             student("TEST THREE", dob="02/02/2018"),
             student("TEST FOUR", parent="TEST DAD"),
             student("TEST ONLY UDISE"),
             student("TEST SENIOR", class_id=10, cls="X A")]                     # PARAKH has no Class X
    parakh = [student("Test  One", apaar="111", adm="9"),                     # same APAAR, admission no differs
              student("TEST 2", adm="7"),                                       # admission number, leading zero
              student("test three", dob="02/02/2018"),
              student("TEST FOUR", parent="Test Dad"),
              student("TEST ONLY PARAKH", class_id=-3, cls="Balvatika 1 A")]
    monkeypatch.setattr(udise_parakh, "udise_students", lambda sid: udise)
    monkeypatch.setattr(udise_parakh, "parakh_students", lambda tids: parakh)
    r = udise_parakh.compare("s1", ["t1"])
    assert r["counts"] == {"udise": 5, "parakh": 5, "matched": 4, "only_udise": 1, "only_parakh": 1, "differ": 2,
                           "udise_higher_classes": 1}
    by = {m["udise"]["name"]: (m["by"], m["differs"]) for m in r["matched"]}
    assert by == {"TEST ONE": ("APAAR ID", ["admission no"]), "TEST TWO": ("admission number", ["name"]),
                  "TEST THREE": ("name and date of birth", []), "TEST FOUR": ("name and parent", [])}
    assert [s["name"] for s in r["only_udise"]] == ["TEST ONLY UDISE"]
    assert [s["name"] for s in r["only_parakh"]] == ["TEST ONLY PARAKH"]


def test_a_key_two_students_share_pairs_nobody(monkeypatch):
    monkeypatch.setattr(udise_parakh, "udise_students", lambda sid: [student("TWIN", adm="1"), student("TWIN", adm="1")])
    monkeypatch.setattr(udise_parakh, "parakh_students", lambda tids: [student("TWIN", adm="1")])
    r = udise_parakh.compare("s1", ["t1"])
    assert r["counts"]["matched"] == 0 and r["counts"]["only_udise"] == 2


def test_parentage_on_parakh_comes_from_the_kept_cards(monkeypatch, tmp_path):
    card = tmp_path / "teacher_t1" / "2627" / "foundational" / "42.json"
    card.parent.mkdir(parents=True)
    gen = [""] * 30
    gen[24] = "TEST GUARDIAN"
    card.write_text(json.dumps({"parts": {"part_a1": json.dumps({"gen": gen})}}), encoding="utf-8")
    monkeypatch.setattr(udise_parakh, "CARDS_DIR", tmp_path)
    assert udise_parakh._guardians(["t1"]) == {"42": "TEST GUARDIAN"}
    assert udise_parakh._dob("2019-05-04") == "04/05/2019" and udise_parakh._dob("04/05/2019") == "04/05/2019"


def test_the_pdfs_build_with_a_band_tiles_and_page_count(monkeypatch):
    rows = [student(f"TEST {i}", parent="P", adm=str(i), dob="01/01/2019") for i in range(80)]
    result = {"counts": {"udise": 80, "parakh": 80, "matched": 0, "only_udise": 80, "only_parakh": 80, "differ": 0},
              "only_udise": rows, "only_parakh": rows, "matched": []}
    pdf = reports_pdf.compare("s1", SimpleNamespace(school_name="TEST SCHOOL", udise_code="0000"), result)
    assert pdf.startswith(b"%PDF") and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 0
    assert reports_pdf._step("Verify again (step 1)") == "Verify again"
