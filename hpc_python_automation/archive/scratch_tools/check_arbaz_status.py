import json
import sys
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

    roster = page.evaluate("""async (auth) => {
        const resp = await fetch('/api/proxy/states/jk/districts/2/schools/7971/teachers/T7AFCD2/hpc/MIDDLE?page_no=1&page_size=50', {
            headers: { 'Authorization': auth }
        });
        return await resp.json();
    }""", auth_token)

    records = roster.get('data', {}).get('records', [])
    for rec in records:
        if 'ARBAZ' in rec.get('full_name', '').upper():
            print("STUDENT RECORD:")
            print(json.dumps(rec, indent=2))

    ctx.close()
