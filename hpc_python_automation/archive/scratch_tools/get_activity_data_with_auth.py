import json
import time
from playwright.sync_api import sync_playwright

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
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    res = page.evaluate("""async (auth) => {
        const resp = await fetch('/api/proxy/states/jk/hpc/2627/MIDDLE/144972?hpc_col=part_b', {
            headers: { 'Authorization': auth }
        });
        const json = await resp.json();
        return json;
    }""", auth_token)

    with open('data/live_part_b_state.json', 'w', encoding='utf-8') as f:
        json.dump(res, f, indent=2)

    data = res.get('data') or {}
    formdata = data.get('formdata') or []
    print(f"Activities in DB: {len(formdata)}")
    if formdata:
        act = formdata[0]
        print("Activity 0 name:", act.get('nm'))
        print("Activity 0 is_complete:", act.get('is_complete'))
        print("Activity 0 dt keys:", list(act.get('dt', {}).keys()))
        dt = act.get('dt', {})
        for k in ['domain', 'gl', 'cpt', 'activity', 'ast', 'bar', 'tf', 'desc', 'spt', 'awr', 'sen', 'cre', 'slr', 'ml', 'mpa', 'mps', 'mpc']:
            print(f"  {k}: {dt.get(k)}")

    ctx.close()
