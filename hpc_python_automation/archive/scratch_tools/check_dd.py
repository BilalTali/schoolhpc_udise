import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)
    page.locator("text='Pick from Activity Bank'").first.click()
    time.sleep(0.5)
    page.locator(".modal button:has-text('Continue')").first.click()
    time.sleep(1)
    
    # Click Subject(s) dropdown
    sub_dd = page.locator(".modal div:has-text('All')").first
    sub_dd.click()
    time.sleep(1)
    page.screenshot(path='audit_evidence/modal_subject_dropdown_open.png')
    
    # Check what items opened
    opts = page.locator(".custom-dropdown-item, .dropdown-menu, li, div[class*='option']").all_inner_texts()
    print("Options:", [o.strip() for o in opts if o.strip()][:25])

    ctx.close()
