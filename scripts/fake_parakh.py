"""
A fake PARAKH HPC API for trying the app end to end without the real portal. Made-up school, teachers
and students only; everything lives in memory and is gone when it stops.

    python scripts/fake_parakh.py [port]          (default 8765)

Run the app against it with scripts/run_with_fake_parakh.py, which also blocks every other outside
connection. Any captcha answer and OTP is accepted. Login IDs starting with "school" get a school
account (no class mapping); any other ID gets a teacher who is class teacher of the classes below.

It answers the requests backend/hpc/portal.py and Lookups make, in the shapes the real portal uses.
GET /_fake/saves lists every PATCH received (for checking what the app sent).
"""
import base64
import copy
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATE, AY, DISTRICT, SCHOOL = "jk", "2627", 2, 1
PNG_1PX = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")).decode()

GRADES = {"FOUNDATIONAL": [{"id": 3, "grade_code": "bv3", "grade_caption": "Balvatika 3"},
                           {"id": 4, "grade_code": "grd1", "grade_caption": "Grade 1"}],
          "PREPARATORY": [{"id": 8, "grade_code": "grd5", "grade_caption": "Grade 5"}],
          "MIDDLE": [{"id": 9, "grade_code": "grd6", "grade_caption": "Grade 6"}]}
DOMAINS = {"FOUNDATIONAL": list(zip(range(1, 7), ["FSDOM1", "FSDOM2", "FSDOM3", "FSDOM4", "FSDOM5", "FSDOM51"])),
           "PREPARATORY": [(88 + i, f"PSLS{i + 1}") for i in range(7)],
           "MIDDLE": list(zip(range(269, 280), ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"]))}
BANK_ID = {"FOUNDATIONAL": 200, "PREPARATORY": 85, "MIDDLE": 1}
CONTENT = {"gl": ["L1CG1"], "cpt": ["L1C1.1"], "desc": ["Pairs act out a short conversation.", "What did you say?"],
           "awr": ["Uses simple phrases.", "Uses clear sentences.", "Uses complete sentences confidently.", ""],
           "sen": ["Some politeness.", "Polite and responsive.", "Shows clear empathy.", ""],
           "cre": ["Adds a line.", "Changes the dialogue.", "Invents new situations.", ""],
           "approaches": [1], "any-other": ""}
PARTS = {"FOUNDATIONAL": ["part_a1", "part_a2", "part_b", "part_c", "hpc_credit"],
         "PREPARATORY": ["part_a1", "part_a2", "part_a3", "part_b", "part_c", "hpc_credit"],
         "MIDDLE": ["part_a1", "part_a2", "part_a3", "part_b", "part_c", "hpc_credit"]}
# class teacher of: Grade 1 A (Foundational), Grade 5 A (Preparatory), Grade 6 A (Middle)
TEACHER_MAPPING = [{"ct": 1, "grd": 4, "sec": 1}, {"ct": 1, "grd": 8, "sec": 1}, {"ct": 1, "grd": 9, "sec": 1}]
CLASSES = {"FOUNDATIONAL": (4, 4), "PREPARATORY": (8, 6), "MIDDLE": (9, 5)}   # grade id, number of students


def _students():
    out, sid = {}, 900001
    for stage, (grade, count) in CLASSES.items():
        for n in range(1, count + 1):
            record = {"hpc_id": str(sid), "std_reg_id": f"FAKE{sid}", "school_id": str(SCHOOL), "district_id": str(DISTRICT),
                      "current_part": None, "hpc_status": "PENDING",
                      "stu_info": {"student_name": f"FAKE {stage[:4]} STUDENT {n:02d}", "std_apaar_id": f"{sid:012d}",
                                   "teacher_code": "TC1", "dob": "2016-01-01", "gender": "MALE" if n % 2 else "FEMALE",
                                   "school_admission_number": f"0{n:03d}", "grade_id": grade, "section_id": 1},
                      "sch_info": {"school_name": "Fake Public School", "school_city": "Faketown", "state_name": "Fake State",
                                   "school_pincode": "000000", "school_udise": "00000000000", "district_name": "Fake District"}}
            out[(stage, str(sid))] = {"record": record, "parts": {p: None for p in PARTS[stage]}}
            sid += 1
    # one student PARAKH lists to the teacher but the teacher may not open (another class)
    other = copy.deepcopy(out[("FOUNDATIONAL", "900001")])
    other["record"]["hpc_id"] = "909999"
    other["record"]["stu_info"].update(student_name="FAKE OTHER CLASS", grade_id=3)
    out[("FOUNDATIONAL", "909999")] = other
    return out


STUDENTS = _students()
SAVES = []
LOCK = threading.Lock()
TOKENS = {}                     # access token -> staff details


def _staff(login_id):
    school = login_id.lower().startswith("school")
    return {"staff_id": 70001 if school else 70002, "id": 70001 if school else 70002, "name": "Fake School Admin" if school else "Fake Teacher",
            "role": "SCHOOL" if school else "TEACHER", "school_id": SCHOOL, "district_id": DISTRICT, "state_code_internal": STATE,
            "school_cur_ay_code": AY, "school_name": "Fake Public School", "hpc_stage": list(CLASSES),
            "grade_section_mapping": [] if school else TEACHER_MAPPING}


def _login_data(login_id):
    token = f"fake-access-{len(TOKENS) + 1}"
    TOKENS[token] = _staff(login_id)
    return {"access_token": token, "refresh_token": f"fake-refresh-{login_id}", "staff_details": TOKENS[token]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):            # ids only: the paths hold student ids, never names
        sys.stderr.write("[fake-parakh] " + fmt % args + "\n")

    def _send(self, code, body=None):
        raw = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _staff_or_401(self):
        token = (self.headers.get("Authorization") or "").removeprefix("Bearer ").strip()
        staff = TOKENS.get(token)
        if staff is None:
            self._send(401, {"success": False, "message": "Unauthorized"})
        return staff

    def do_GET(self):
        url = urlparse(self.path)
        path, q = url.path.removeprefix("/api/proxy"), {k: v[0] for k, v in parse_qs(url.query).items()}
        if path == "/captcha":
            return self._send(200, {"success": True, "data": {"captcha_id": "fake-cap", "image_base64": PNG_1PX}})
        if path == "/_fake/saves":
            with LOCK:
                return self._send(200, SAVES)
        staff = self._staff_or_401()
        if staff is None:
            return
        if path == "/categories/MED_INST,LOCATION":
            return self._send(200, {"success": True, "data": {
                "MED_INST": [{"id": 3, "catg_item_code": "MED_INST_1", "catg_item_caption": "English"},
                             {"id": 4, "catg_item_code": "MED_INST_2", "catg_item_caption": "Hindi"}],
                "LOCATION": [{"id": 1, "catg_item_code": "LOC_RURAL", "catg_item_caption": "Rural"},
                             {"id": 2, "catg_item_code": "LOC_URBAN", "catg_item_caption": "Urban"}]}})
        if path == "/categories/STU_INTRST":
            return self._send(200, {"success": True, "data": [
                {"id": 5, "catg_item_code": "STU_INTRST_READING", "catg_item_caption": "Reading"},
                {"id": 10, "catg_item_code": "STU_INTRST_ART", "catg_item_caption": "Art"}]})
        if path == f"/states/{STATE}/grades":
            stage = q.get("stage")
            return self._send(200, {"success": True, "data": GRADES.get(stage, []) if stage else GRADES})
        if re.fullmatch(rf"/states/{STATE}/districts/\d+/schools/\d+/sections", path):
            return self._send(200, {"success": True, "data": {"records": [{"id": 1, "section_caption": "A"}]}})
        m = re.fullmatch(r"/hpc/activity-categories/(\w+)", path)
        if m:
            return self._send(200, {"success": True, "data": [{"id": i, "ent_code": c, "ent_caption": c} for i, c in DOMAINS[m[1]]]})
        if path == "/country/activities":
            stages = [q["hpc_stage"]] if q.get("hpc_stage") else list(DOMAINS)
            records = [{"id": BANK_ID[s], "activity_caption": f"Fake activity for {s.title()}", "hpc_stage": s,
                        "domain_ids": [DOMAINS[s][0][0]], "activity_data_json": json.dumps({"dt": CONTENT})} for s in stages]
            return self._send(200, {"success": True, "data": {"records": records, "count": len(records)}})
        if re.fullmatch(rf"/states/{STATE}/districts/\d+/schools/\d+/{AY}/\w+/\d+/activities", path):
            return self._send(200, {"success": True, "data": {"records": [], "count": 0}})
        m = re.fullmatch(rf"/states/{STATE}/districts/\d+/schools/\d+/teachers/\d+/hpc/(\w+)", path)
        if m:
            page, size = int(q.get("page_no", 1)), int(q.get("page_size", 50))
            rows = [{"id": int(sid), "full_name": e["record"]["stu_info"]["student_name"], "grade_id": e["record"]["stu_info"]["grade_id"],
                     "section_id": 1, "hpc_status": e["record"]["hpc_status"], "std_reg_id": e["record"]["std_reg_id"],
                     "std_apaar_id": e["record"]["stu_info"]["std_apaar_id"], "student_stage": st}
                    for (st, sid), e in STUDENTS.items() if st == m[1]]
            chunk = rows[(page - 1) * size: page * size]
            return self._send(204) if not chunk else self._send(200, {"success": True, "data": {"records": chunk, "count": len(rows)}})
        m = re.fullmatch(rf"/states/{STATE}/hpc/{AY}/(\w+)/(\d+)", path)
        if m:
            entry = STUDENTS.get((m[1], m[2]))
            if entry is None:
                return self._send(404, {"success": False, "message": "Not found"})
            grade = entry["record"]["stu_info"]["grade_id"]
            if staff["grade_section_mapping"] and not any(x["grd"] == grade for x in staff["grade_section_mapping"]):
                return self._send(403, {"success": False, "message": "Forbidden"})
            with LOCK:
                data = copy.deepcopy(entry["record"])
                if q.get("hpc_col"):
                    data["formdata"] = copy.deepcopy(entry["parts"].get(q["hpc_col"]))
            return self._send(200, {"success": True, "data": data})
        return self._send(404, {"success": False, "message": f"fake PARAKH has no {path}"})

    def do_POST(self):
        path, body = urlparse(self.path).path.removeprefix("/api/proxy"), self._body()
        if path == "/captcha/verify":
            return self._send(200, {"success": True, "data": {"captcha_token": "fake-captcha-token"}})
        if path == "/auth/login":
            return self._send(200, {"success": True, "data": _login_data(str(body.get("staff_id", "teacher")))})
        if path == "/auth/verify-otp":
            return self._send(200, {"success": True, "data": _login_data(str(body.get("staff_id", "teacher")))})
        if path == "/auth/refresh-token":
            refresh = (self.headers.get("Authorization") or "").removeprefix("Bearer ").removeprefix("fake-refresh-")
            return self._send(200, {"success": True, "data": _login_data(refresh or "teacher")})
        return self._send(404, {"success": False, "message": f"fake PARAKH has no {path}"})

    def do_PATCH(self):
        path, body = urlparse(self.path).path.removeprefix("/api/proxy"), self._body()
        staff = self._staff_or_401()
        if staff is None:
            return
        m = re.fullmatch(rf"/states/{STATE}/hpc/{AY}/(\w+)/(\d+)", path)
        entry = STUDENTS.get((m[1], m[2])) if m else None
        if entry is None:
            return self._send(404, {"success": False, "message": "Not found"})
        with LOCK:
            SAVES.append({"stage": m[1], "student_id": m[2], "hpc_col": body.get("hpc_col"), "payload": body})
            entry["parts"][body.get("hpc_col")] = body.get("formdata")
            entry["record"]["current_part"] = body.get("current_part")
            if body.get("hpc_status"):
                entry["record"]["hpc_status"] = body["hpc_status"]
        return self._send(200, {"success": True, "data": {}})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"[fake-parakh] listening on http://127.0.0.1:{port}/api/proxy ({len(STUDENTS)} made-up students)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
