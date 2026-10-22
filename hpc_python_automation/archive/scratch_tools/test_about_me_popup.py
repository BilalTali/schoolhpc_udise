import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2', wait_until='networkidle')
    time.sleep(2)
    
    # Click the first finger input
    inp0 = page.locator("input.pre-about-me-0").first
    print("Clicking pre-about-me-0...")
    inp0.click()
    time.sleep(1)
    
    page.screenshot(path='audit_evidence/about_me_popup.png')
    
    # Check what opened
    dialog = page.locator(".modal, [role=dialog], .popover").first
    if dialog.is_visible():
        print("Popup Dialog Text:\n", dialog.inner_text())
        print("Popup Inputs:", dialog.locator("input, textarea").all_inner_texts())

    ctx.close()
