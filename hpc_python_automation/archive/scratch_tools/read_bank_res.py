import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_res(res):
        if 'activities?' in res.url and 'hpc_stage=MIDDLE' in res.url:
            data = res.json()
            print("MIDDLE ACTIVITIES RESPONSE:")
            print(json.dumps(data, indent=2)[:1000])

    page.on('response', on_res)
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(3)
    ctx.close()
