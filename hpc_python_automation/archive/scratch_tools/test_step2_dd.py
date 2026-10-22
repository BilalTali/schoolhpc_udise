import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    
    # Click Activity 2 on the left
    btns = page.locator(".already-activity-selected ul li button").all()
    print(f"Total activity buttons on Arkan: {len(btns)}")
    if len(btns) >= 2:
        btns[1].click()
        time.sleep(1)
        
    # Go to Step 2: Subject, CG & Competencies
    page.locator("text='Subject, CG & Competencies'").first.click()
    time.sleep(1)
    
    # Check partBDomainSelect
    dd = page.locator("#partBDomainSelect").first
    print("partBDomainSelect visible:", dd.is_visible())
    print("partBDomainSelect class:", dd.get_attribute("class"))
    
    # Click it!
    dd.click()
    time.sleep(1)
    page.screenshot(path='audit_evidence/arkan_step2_dropdown_open.png')
    
    # Print all items inside the dropdown
    items = page.locator("#partBDomainSelect label, #partBDomainSelect input, .dropdown-menu label").all_inner_texts()
    print("Found dropdown items:", items)

    ctx.close()
