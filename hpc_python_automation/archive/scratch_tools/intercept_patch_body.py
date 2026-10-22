import json
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_req(req):
        if '144972' in req.url and req.method == 'PATCH':
            print("PATCH URL:", req.url)
            print("PATCH HEADERS:", dict(req.headers))
            post_data = req.post_data
            if post_data:
                data = json.loads(post_data)
                with open('data/real_patch_payload.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                print("Saved real PATCH payload to data/real_patch_payload.json!")

    page.on('request', on_req)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text="Teacher's Feedback").first.click()
    time.sleep(1)
    ta = page.locator('textarea').last
    ta.fill("Student shows great enthusiasm and participation in all activities.")
    time.sleep(1)

    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        time.sleep(3)

    ctx.close()
