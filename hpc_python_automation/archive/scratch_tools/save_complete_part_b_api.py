import json
import time
from playwright.sync_api import sync_playwright

# Load the current payload
with open('data/current_student_part_b.json', 'r', encoding='utf-8') as f:
    student_data = json.load(f)['data']

# Populate the missing completion fields in the first activity
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
dt['tf'] = ["2", "2", "2"] # Proficient across all 3
dt['spt'] = ["Provide advanced problem-solving worksheets and structured project mentoring.", "Consistent follow-up on assignments."]
act['is_complete'] = True
act['is_modified'] = True

# Also ensure all 11 domains are present in domain list
dt['domain'] = ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"]

payload = {
    "hpc_col": "part_b",
    "data": student_data
}

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    print("Posting completed Part-B payload to API...")
    res = page.evaluate("""async (bodyData) => {
        const sessRes = await fetch('/api/auth/session');
        const sess = await sessRes.json();
        const token = sess.token || (sess.user && sess.user.token) || sess.accessToken;
        console.log("Found token:", token ? token.substring(0, 15) : "none");

        const resp = await fetch('/api/proxy/states/jk/hpc/2627/MIDDLE/144972', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(bodyData)
        });
        return { status: resp.status, data: await resp.json() };
    }""", payload)
    print("API Response:", res)

    # Reload page to verify UI state
    print("Reloading Part-B...")
    page.reload(wait_until='networkidle')
    time.sleep(3)
    page.screenshot(path='audit_evidence/middle_part_b_after_complete_api_save.png')

    # Check if Finish Activity or Continue is ready
    cont = page.locator("button:has-text('Continue')").first
    print("Continue button visible:", cont.is_visible())
    if cont.is_visible():
        cont.click()
        time.sleep(3)
        print("URL after Continue:", page.url)

    ctx.close()
