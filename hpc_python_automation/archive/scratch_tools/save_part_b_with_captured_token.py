import json
import time
from playwright.sync_api import sync_playwright

# Load student data
with open('data/current_student_part_b.json', 'r', encoding='utf-8') as f:
    student_data = json.load(f)['data']

act = student_data['formdata'][0]
dt = act['dt']
dt['slr'] = ["yes", "yes", "yes"]
dt['mpa'] = [0, 1, 2]
dt['mps'] = [0, 1, 2]
dt['mpc'] = [0, 1, 2]
dt['ml'] = [
    "Learned key multi-disciplinary concepts and applied scientific inquiry.",
    "Hands-on experiments and real-world mathematical applications.",
    "Regular problem-solving and numerical practice.",
    "Formulating complex hypotheses and data analysis."
]
dt['pf'] = [
    "ARBAZ IQBAL",
    "MOHAMMAD SAHIL",
    "yes",
    "yes",
    "Presentation and public speaking.",
    "Time management during experiments."
]
dt['ppa'] = [0, 1]
dt['pps'] = [0, 1]
dt['ppc'] = [0, 1]
dt['tf'] = ["2", "2", "2"] # Proficient
dt['spt'] = ["Provide advanced problem-solving worksheets and structured project mentoring.", "Consistent follow-up on assignments."]
act['is_complete'] = True
act['is_modified'] = True
dt['domain'] = ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"]

payload = {
    "hpc_col": "part_b",
    "data": student_data
}

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

    if auth_token:
        res = page.evaluate("""async ({ bodyData, authHeader }) => {
            const resp = await fetch('/api/proxy/states/jk/hpc/2627/MIDDLE/144972', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': authHeader
                },
                body: JSON.stringify(bodyData)
            });
            return { status: resp.status, data: await resp.json() };
        }""", {"bodyData": payload, "authHeader": auth_token})
        print("API Response:", res)

    # Now reload page to check state
    page.reload(wait_until='networkidle')
    time.sleep(3)
    page.screenshot(path='audit_evidence/middle_part_b_saved_via_real_token.png')

    ctx.close()
