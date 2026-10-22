import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Click Sub-step 2: Subject, CG & Competencies
    s2 = page.locator("div, p, span").filter(has_text="Subject, CG & Competencies").last
    print("Clicking Sub-step 2...")
    s2.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/middle_step2_view.png')

    ctx.close()
