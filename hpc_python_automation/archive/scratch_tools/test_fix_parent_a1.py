import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A1', wait_until='networkidle')
    time.sleep(2)
    
    # Check parent/guardian input
    parent_inp = page.locator("input[placeholder*='Mother Name'], input[placeholder*='Father Name'], input[placeholder*='Guardian Name'], input[placeholder*='Mother'], input[placeholder*='Father'], input[placeholder*='Guardian']").first
    print("Found parent input:", parent_inp.is_visible())
    print("Current value in parent input:", parent_inp.input_value())
    
    # Fill with iqbal (from Column I)
    parent_inp.fill("iqbal")
    time.sleep(0.5)
    print("New value in parent input:", parent_inp.input_value())
    
    page.screenshot(path='audit_evidence/parent_input_fixed.png')
    
    # Save as Draft
    page.locator("button:has-text('Save as Draft')").first.click()
    time.sleep(2)
    
    ctx.close()
