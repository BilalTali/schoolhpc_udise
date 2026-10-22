import json
import time
from playwright.sync_api import sync_playwright

with open('data/real_patch_payload.json', 'r', encoding='utf-8') as f:
    payload = json.load(f)

# Complete the activity
act = payload['formdata'][0]
dt = act['dt']
dt['slr'] = ["yes", "yes", "yes"]
dt['ml'] = [
    "Learned key scientific principles and multidisciplinary connections.",
    "Conducted hands-on experiments and recorded findings systematically.",
    "Formulating hypotheses and quantitative problem-solving.",
    "Connecting classroom theory to real-world applications."
]
dt['mpa'] = [0, 1, 2]
dt['mps'] = [0, 1, 2]
dt['mpc'] = [0, 1, 2]
dt['spt'] = [
    "Provide advanced problem-solving worksheets and structured project mentoring.",
    "Encourage consistent practice and regular self-reflection."
]

act['is_complete'] = True
act['is_modified'] = True
payload['activity_id'] = act['id']

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

    print("Navigating to Middle Stage Part-B...")
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    print("Captured Auth Token:", auth_token[:30] if auth_token else "NONE")

    res = page.evaluate("""async ({ bodyData, authHeader }) => {
        const resp = await fetch('/api/proxy/states/jk/hpc/2627/MIDDLE/144972', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': authHeader
            },
            body: JSON.stringify(bodyData)
        });
        return { status: resp.status, data: await resp.json() };
    }""", {"bodyData": payload, "authHeader": auth_token})
    print("PATCH API Response:", res)

    # Reload page to check UI state
    print("Reloading Part-B...")
    page.reload(wait_until='networkidle')
    time.sleep(3)
    page.screenshot(path='audit_evidence/middle_part_b_after_real_patch.png')

    # Check if Finish Activity / Finished indicator exists
    finished_indicator = page.locator(".nofity-finished, .hpc-activity-item--finished").all()
    print(f"Finished indicators on student: {len(finished_indicator)}")

    ctx.close()
