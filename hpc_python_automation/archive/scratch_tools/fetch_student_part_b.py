import json
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_res(res):
        if 'hpc_col=part_b' in res.url:
            try:
                data = res.json()
                with open('data/current_student_part_b.json', 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                print("Saved current_student_part_b.json!")
            except Exception as e:
                print("Error:", e)

    page.on('response', on_res)
    slug = "MTQ0OTcyLTI2Mjctams="
    page.goto(f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B", wait_until='networkidle')
    time.sleep(2)
    ctx.close()
