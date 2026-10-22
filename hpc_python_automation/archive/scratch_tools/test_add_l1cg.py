import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    
    # 1. Click Add Activity
    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)
    
    # 2. Pick from Activity Bank
    page.locator("text='Pick from Activity Bank'").first.click()
    time.sleep(0.5)
    page.locator(".modal button:has-text('Continue')").first.click()
    time.sleep(1)
    
    # 3. Click Global Activities tab
    page.locator("text='Global Activities'").first.click()
    time.sleep(1)
    
    # 4. Find L1CG1 , C-1.2 or L1CG 1 (C-1.2)
    item = page.locator(".modal label:has-text('L1CG1 , C-1.2'), .modal label:has-text('L1CG 1 (C-1.2)'), .modal label:has-text('L1CG 1, C 1.1')").first
    print("Item found:", item.inner_text() if item.is_visible() else "None")
    if item.is_visible():
        item.click()
        time.sleep(0.5)
    else:
        # Click first checkbox
        page.locator(".modal input[type=checkbox]").first.click()
        
    page.locator(".modal button:has-text('Use Activity')").first.click()
    time.sleep(3)
    page.screenshot(path='audit_evidence/after_adding_l1cg.png')
    
    # Check Step 2 on the newly added activity
    page.locator("text='Subject, CG & Competencies'").first.click()
    time.sleep(1)
    page.screenshot(path='audit_evidence/new_activity_step2.png')
    
    # Check partBDomainSelect
    dd = page.locator("#partBDomainSelect").first
    print("partBDomainSelect disabled?", "dropdown-disabled" in (dd.get_attribute("class") or ""))
    dd.click()
    time.sleep(1)
    page.screenshot(path='audit_evidence/new_activity_step2_dd_open.png')

    ctx.close()
