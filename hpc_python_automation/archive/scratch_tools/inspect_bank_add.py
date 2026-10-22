import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank/add', wait_until='networkidle')
    time.sleep(2)
    print("URL:", page.url)
    page.screenshot(path='audit_evidence/activity_bank_add_page.png')

    # Inspect inputs, stages, domains
    labels = [l.inner_text().strip() for l in page.locator("label").all() if l.is_visible()]
    print("Labels on add page:", labels)

    ctx.close()
