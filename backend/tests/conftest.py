"""
Shared test fixtures: a fake portal (no network) with realistic lookups and synthetic students.
"""
import copy
import json
import os
import tempfile
from pathlib import Path

import pytest

# The tests use a throwaway SQLite database, data folder, backup folder and keys - never the real ones.
# Set before backend.config loads .env (which only fills in what is not set already).
_SCRATCH = Path(tempfile.mkdtemp(prefix="teacherassist-tests-"))
os.environ["HPC_DATABASE_URL"] = "sqlite:///" + str(_SCRATCH / "test.db")
os.environ["HPC_SCHOOL_APPROVAL"] = "false"     # tests sign schools in right after registering
os.environ["HPC_DATA_DIR"] = str(_SCRATCH / "data")
os.environ["HPC_BACKUP_DIR"] = str(_SCRATCH / "backups")
os.environ["HPC_BACKUP_KEY_FILE"] = str(_SCRATCH / "keys" / "backup.key")
for _name in ("HPC_JWT_SECRET", "HPC_SECRET_KEY"):     # generated into the scratch data folder instead
    os.environ.pop(_name, None)

from backend import config as _config  # noqa: E402

if any(str(p).lower().replace("\\", "/").startswith("c:/teacherassist")
       for p in (_config.DATA_DIR, _config.BACKUP_DIR, _config.BACKUP_KEY_FILE)):
    pytest.exit("Tests must not use the real data folder (C:\\TeacherAssist).", returncode=2)

from backend.hpc.stages.common import Lookups  # noqa: E402
from backend.hpc.sync import StudentData       # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

BANK_CONTENT = {"gl": ["L1CG1"], "cpt": ["L1C1.1"], "desc": ["Pairs act out a short conversation.", "What did you say?"],
                "awr": ["Uses simple phrases.", "Uses clear sentences.", "Uses complete sentences confidently.", ""],
                "sen": ["Some politeness.", "Polite and responsive.", "Shows clear empathy.", ""],
                "cre": ["Adds a line.", "Changes the dialogue.", "Invents new situations.", ""],
                "approaches": [1], "any-other": ""}

STAGE_SETUP = {
    "FOUNDATIONAL": {"grades": [{"id": 3, "grade_code": "bv3", "grade_caption": "Balvatika 3"}],
                     "domains": list(zip(range(1, 7), ["FSDOM1", "FSDOM2", "FSDOM3", "FSDOM4", "FSDOM5", "FSDOM51"])),
                     "bank_id": 200, "grade_id": 3},
    "PREPARATORY": {"grades": [{"id": 8, "grade_code": "grd5", "grade_caption": "Grade 5"}],
                    "domains": [(88 + i, f"PSLS{i + 1}") for i in range(7)], "bank_id": 85, "grade_id": 8},
    "MIDDLE": {"grades": [{"id": 9, "grade_code": "grd6", "grade_caption": "Grade 6"}],
               "domains": list(zip(range(269, 280), ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"])),
               "bank_id": 1, "grade_id": 9},
}


class FakePortal:
    """Stands in for backend.hpc.portal.Portal: serves stored records, records saves."""
    state = "jk"
    ay = "2627"

    def roster(self, stage):
        from backend.hpc.portal import stage_code
        out = []
        for (code, sid), entry in self.students.items():
            if code == stage_code(stage):
                stu = entry["record"]["stu_info"]
                out.append({"id": sid, "full_name": stu["student_name"], "grade_id": stu["grade_id"],
                            "section_id": stu["section_id"], "hpc_status": "IN_PROGRESS"})
        return out

    def __init__(self, students=None):
        self.students = students or {}       # (stage_code, id) -> {"record": {...}, "parts": {col: formdata}}
        self.saved = []                      # (stage_code, id, payload)

    def student(self, stage, student_id, hpc_col=None):
        from backend.hpc.portal import stage_code
        entry = self.students[(stage_code(stage), str(student_id))]
        data = copy.deepcopy(entry["record"])
        if hpc_col:
            data["formdata"] = copy.deepcopy(entry["parts"].get(hpc_col))
        return data

    def save_part(self, stage, student_id, payload):
        from backend.hpc.portal import stage_code
        self.saved.append((stage_code(stage), str(student_id), copy.deepcopy(payload)))
        entry = self.students[(stage_code(stage), str(student_id))]
        entry["parts"][payload["hpc_col"]] = payload["formdata"]
        entry["record"]["current_part"] = payload["current_part"]
        return {"success": True}


def make_lookups(stage_code: str, portal=None) -> Lookups:
    setup = STAGE_SETUP[stage_code]
    lk = Lookups.__new__(Lookups)
    lk.portal = portal or FakePortal()
    lk.medium = [{"id": 3, "catg_item_code": "MED_INST_1", "catg_item_caption": "English"},
                 {"id": 4, "catg_item_code": "MED_INST_2", "catg_item_caption": "Hindi"}]
    lk.location = [{"id": 1, "catg_item_code": "LOC_RURAL", "catg_item_caption": "Rural"},
                   {"id": 2, "catg_item_code": "LOC_URBAN", "catg_item_caption": "Urban"}]
    lk.interests = [{"id": 5, "catg_item_code": "STU_INTRST_READING", "catg_item_caption": "Reading"},
                    {"id": 10, "catg_item_code": "STU_INTRST_ART", "catg_item_caption": "Art"}]
    lk.grades = setup["grades"]
    lk.sections = [{"id": 1, "section_caption": "A"}]
    lk.domains = [{"id": i, "ent_code": code, "ent_caption": code} for i, code in setup["domains"]]
    lk.activities = {setup["bank_id"]: {"id": setup["bank_id"], "activity_caption": "Conversation in pairs",
                                        "domain_ids": [setup["domains"][0][0]], "content": {"dt": BANK_CONTENT}}}
    return lk


def blank_student(stage_code: str, student_id: str = "1001") -> StudentData:
    record = {"hpc_id": student_id, "std_reg_id": "SREG1001", "school_id": "1", "district_id": "2",
              "current_part": None,
              "stu_info": {"student_name": "TEST STUDENT", "std_apaar_id": "000000000000", "teacher_code": "TC1",
                           "dob": "2015-01-01", "gender": "MALE", "school_admission_number": "A1",
                           "grade_id": STAGE_SETUP[stage_code]["grade_id"], "section_id": 1},
              "sch_info": {"school_name": "Test School", "school_city": "Town", "state_name": "State",
                           "school_pincode": "000000", "school_udise": "00000000000", "district_name": "District"}}
    from backend.hpc.stages import get_stage
    parts = {p.col: None for p in get_stage(stage_code).PARTS}
    return StudentData(student_id, record, parts)


def filled_row(stage_code: str) -> dict:
    """Every required workbook cell filled with valid values."""
    row = {"a1_mother_tongue": "Kashmiri", "a1_medium": "English", "a1_rural_urban": "Rural",
           "a1_guardian_relation": "Father", "a1_guardian_name": "Test Parent", "a1_interests": "Reading, Art"}
    for i in range(1, 13):
        row[f"a1_working_{i}"], row[f"a1_present_{i}"] = 22, 20
    bank = STAGE_SETUP[stage_code]["bank_id"]
    from backend.hpc.stages import get_stage
    st = get_stage(stage_code)
    for d in st.DOMAINS:                 # the Activities grid: one bank activity, same levels, every subject
        row.update({f"b_act_{d}": f"P{bank}", f"b_lvl_{d}_awareness": "Proficient",
                    f"b_lvl_{d}_sensitivity": "Advanced", f"b_lvl_{d}_creativity": "Beginner"})
    for d in st.DOMAINS if stage_code != "FOUNDATIONAL" else []:
        row.update({f"c_{d}_awareness": "Proficient", f"c_{d}_sensitivity": "Proficient",
                    f"c_{d}_creativity": "Advanced", f"c_{d}_remark": "Works well with others."})
    from backend.hpc import credit
    if stage_code != "FOUNDATIONAL":
        key = "preparatory" if stage_code == "PREPARATORY" else "middle"
        for i, _ in enumerate(credit.subjects(key)):
            if credit.sa_applicable(key, i):
                row[f"d_{i + 1}_max"], row[f"d_{i + 1}_obtained"] = 50, 40
    row["d_declaration"] = "Yes"
    if stage_code == "FOUNDATIONAL":
        for d in st.DOMAINS:
            for k in ("awr", "sen", "cre"):
                row.pop(f"c_{d}_{k}", None)
            row.update({f"c_{d}_awr": "Proficient", f"c_{d}_sen": "Proficient", f"c_{d}_cre": "Proficient",
                        f"c_{d}_descriptor": "Plays well with others."})
        row.update({"b_sa_liked": "Yes", "b_sa_easy": "No", "b_sa_needed": "Teachers, Books"})
        row["a1_working_12"] = row["a1_present_12"] = ""    # March left blank: Foundational stores it as 0
        return row
    if stage_code == "PREPARATORY":
        row.update({f"a3_feel_{i}": "Yes" for i in range(1, 8)})
        row.update({f"b_self_{i}": "Yes" for i in range(1, 9)})
    else:
        row.update({"b_reflect_awareness": "Yes", "b_reflect_sensitivity": "To an extent", "b_reflect_creativity": "No",
                    "b_grid_awareness": "Learnt something new", "b_grid_sensitivity": "Helped others",
                    "b_grid_creativity": "Curious to explore", "b_learnt": "Teamwork", "b_interesting": "Role play",
                    "b_need_practice": "Speaking", "b_need_help": "Vocabulary", "b_strengths": "Collaboration",
                    "b_barriers": "None", "b_help_progress": "More speaking practice"})
    return row


@pytest.fixture(autouse=True)
def no_real_sdms_sign_out(monkeypatch, request):
    """Disconnect / Connect sign the SDMS session out on SDMS's server: never from a test (made-up cookies must not
    reach the real site). The test of the sign-out itself mocks the network instead."""
    if "real_sign_out" not in request.keywords:
        from backend.services import udise_sessions
        monkeypatch.setattr(udise_sessions, "sign_out_remote", lambda school_id: None)


@pytest.fixture(autouse=True)
def fresh_login_limits():
    """Wrong passwords in one test never slow down the logins of the next."""
    from backend.services import login_limits
    login_limits.reset()
    yield
    login_limits.reset()


@pytest.fixture(autouse=True)
def snapshots_in_tmp(monkeypatch, tmp_path):
    """Tests never write snapshots into the real data folder."""
    from backend.services import snapshots
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", tmp_path / "snapshots")


@pytest.fixture(autouse=True)
def own_activities_in_tmp(monkeypatch, tmp_path):
    """Tests never write the record of the app's own manual activities into the real data folder."""
    from backend.services import own_activities
    monkeypatch.setattr(own_activities, "OWN_DIR", tmp_path / "own_activities")


@pytest.fixture(autouse=True)
def cards_in_tmp(monkeypatch, tmp_path):
    """Each test has its own empty stored copy of cards, never the real data folder."""
    from backend.services import card_store
    monkeypatch.setattr(card_store, "CARDS_DIR", tmp_path / "cards")
    # the background check against PARAKH is tested on its own (test_card_store.py); elsewhere it stays off
    monkeypatch.setattr(card_store, "start_check", lambda *args, **kwargs: None)
    card_store._checks.clear()
    card_store._checked_at.clear()


@pytest.fixture
def credit_cases():
    return json.loads((FIXTURES / "credit_cases.json").read_text(encoding="utf-8"))


def session_headers(identifier: str, password: str = "secret123"):
    """Signs in the way the web app does (cookie session, M-2) and returns (headers carrying that session,
    the login answer). The headers work on any test client, so one client can act as several users."""
    from fastapi.testclient import TestClient
    from backend.main import app
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    assert r.status_code == 200, r.text
    return {"Cookie": f"ta_access={c.cookies.get('ta_access')}", "X-Requested-With": "TeacherAssist"}, r.json()
