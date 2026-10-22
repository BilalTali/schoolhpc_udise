import json
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_req(req):
        if 'hpc_col=part_b' in req.url or ('hpc/2627/MIDDLE/' in req.url and req.method in ('POST', 'PUT')):
            print("REQ METHOD:", req.method, req.url)
            try:
                post_data = req.post_data
                if post_data:
                    data = json.loads(post_data)
                    print("POST DATA KEYS:", list(data.keys()))
                    with open('data/part_b_saved_payload.json', 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2)
                    print("Saved payload to data/part_b_saved_payload.json!")
            except Exception as e:
                print("Error reading post data:", e)

    page.on('request', on_req)
    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        time.sleep(3)

    ctx.close()
