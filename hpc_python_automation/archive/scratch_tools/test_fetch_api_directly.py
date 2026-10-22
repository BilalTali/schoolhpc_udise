import json
import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    auth_token = None
    def intercept_req(req):
        global auth_token
        auth = req.headers.get('authorization')
        if auth and auth.startswith('Bearer eyJ'):
            auth_token = auth

    page.on('request', intercept_req)
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
    time.sleep(2)

    print("Captured Token:", auth_token[:30] if auth_token else "NONE")

    res = page.evaluate("""async (token) => {
        const sessRes = await fetch('/api/auth/session');
        const sess = await sessRes.json();
        const u = sess.user;
        const url = `/api/proxy/states/${u.state_code_internal}/districts/${u.district_id}/schools/${u.school_id}/teachers/${u.staff_id}/hpc/MIDDLE?page_no=1&page_size=50`;
        const resp = await fetch(url, {
            headers: { 'Authorization': token }
        });
        return await resp.json();
    }""", auth_token)

    records = res.get('data', {}).get('records', [])
    print(f"MIDDLE STUDENTS RETURNED ({len(records)}):")
    for r in records[:5]:
        print(f"  ID: {r.get('id')} | Name: {r.get('full_name')} | Adm: {r.get('school_admission_number')} | Status: {r.get('hpc_status')}")

    # Also test PREPARATORY
    res_prep = page.evaluate("""async (token) => {
        const sessRes = await fetch('/api/auth/session');
        const sess = await sessRes.json();
        const u = sess.user;
        const url = `/api/proxy/states/${u.state_code_internal}/districts/${u.district_id}/schools/${u.school_id}/teachers/${u.staff_id}/hpc/PREPARATORY?page_no=1&page_size=50`;
        const resp = await fetch(url, {
            headers: { 'Authorization': token }
        });
        return await resp.json();
    }""", auth_token)

    prep_records = res_prep.get('data', {}).get('records', [])
    print(f"\nPREPARATORY STUDENTS RETURNED ({len(prep_records)}):")
    for r in prep_records[:5]:
        print(f"  ID: {r.get('id')} | Name: {r.get('full_name')} | Status: {r.get('hpc_status')}")

    ctx.close()
