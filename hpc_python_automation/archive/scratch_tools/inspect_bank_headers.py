import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_req(req):
        if 'activities?' in req.url:
            print("REQ URL:", req.url)
            print("REQ HEADERS:", req.headers)

    page.on('request', on_req)
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(3)
    ctx.close()
