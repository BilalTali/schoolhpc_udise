import json
import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_fetch(stage="Middle"):
    stage_upper = "PREPARATORY" if stage.lower() == "preparatory" else "MIDDLE"
    stage_slug = "preparatory-stage" if stage.lower() == "preparatory" else "middle-stage"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        auth_token = None
        def intercept_req(req):
            nonlocal auth_token
            auth = req.headers.get('authorization')
            if auth and auth.startswith('Bearer eyJ'):
                auth_token = auth

        page.on('request', intercept_req)
        page.goto(f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}", wait_until='networkidle')
        time.sleep(2)

        print(f"Captured token for {stage}:", auth_token[:25] if auth_token else "NONE")

        students = page.evaluate("""async ({ stageUpper, token }) => {
            const sessRes = await fetch('/api/auth/session');
            const sess = await sessRes.json();
            const u = sess.user || {};
            const authToken = token || sess.token || u.token || sess.accessToken || '';

            let records = [];
            if (u.staff_id && u.school_id && u.district_id && u.state_code_internal) {
                const rosterUrl = `/api/proxy/states/${u.state_code_internal}/districts/${u.district_id}/schools/${u.school_id}/teachers/${u.staff_id}/hpc/${stageUpper}?page_no=1&page_size=100`;
                const r = await fetch(rosterUrl, {
                    headers: authToken ? { 'Authorization': authToken } : {}
                });
                const json = await r.json();
                records = (json && json.data && json.data.records) || [];
            }

            // Map records
            return records.map(r => {
                let gradeStr = 'Grade 6';
                if (r.grade_id === 9) gradeStr = 'Grade 6';
                else if (r.grade_id === 10) gradeStr = 'Grade 7';
                else if (r.grade_id === 11) gradeStr = 'Grade 8';
                else if (r.grade_id === 6) gradeStr = 'Grade 3';
                else if (r.grade_id === 7) gradeStr = 'Grade 4';
                else if (r.grade_id === 8) gradeStr = 'Grade 5';

                return {
                    id: String(r.id || ''),
                    student_id: String(r.id || ''),
                    admission_number: (r.school_admission_number || r.std_reg_id || '').trim(),
                    student_name: (r.full_name || (r.std_fname + ' ' + (r.std_lname || ''))).trim(),
                    apaar_id: r.std_apaar_id || '',
                    hpc_login_id: r.std_reg_id || '',
                    gender: r.gender || 'Male',
                    grade: gradeStr,
                    section: 'A',
                    status: r.hpc_status || 'PENDING'
                };
            });
        }""", {"stageUpper": stage_upper, "token": auth_token})

        ctx.close()
        return students

if __name__ == '__main__':
    for stg in ["Middle", "Preparatory"]:
        res = test_fetch(stg)
        print(f"[{stg}] Fetched {len(res)} students!")
        for s in res[:3]:
            print(" ", s)
