import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    
    res = page.evaluate("""async () => {
        const r = await fetch('/api/proxy/states/jk/districts/2/schools/7971/2627/TEACHER/T7AFCD2/activities?page_no=1&page_size=50&hpc_stage=MIDDLE');
        return await r.json();
    }""")
    print("Teacher's Middle activities res:", json.dumps(res, indent=2)[:500])
    rows = res.get('data', {}).get('rows', [])
    for r in rows[:10]:
        print(f"  ID: {r.get('id')} | Name: {r.get('act_name')} | Subject: {r.get('subject_name') or r.get('domain_name')}")

    ctx.close()
