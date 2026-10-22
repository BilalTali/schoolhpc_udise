import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Scroll the stepper to reveal step 7
    s7 = page.locator("li").filter(has_text="Teacher's Feedback").first
    s7.scroll_into_view_if_needed()
    time.sleep(1)
    s7.click(force=True)
    time.sleep(2)

    page.screenshot(path='audit_evidence/middle_step7_opened.png')
    ctx.close()
