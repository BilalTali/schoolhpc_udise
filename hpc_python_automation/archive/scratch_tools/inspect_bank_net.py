import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.on('response', lambda r: print('API:', r.status, r.url) if 'hpc' in r.url or 'activit' in r.url else None)
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(3)
    page.screenshot(path='audit_evidence/activity_bank_network.png')
    ctx.close()
