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
    
    # Check options in Subject(s) dropdown
    # Let's inspect the select elements in the modal
    selects = page.locator(".modal select").all()
    print(f"Found {len(selects)} select elements in modal")
    for s in selects:
        opts = s.locator("option").all_inner_texts()
        print("Select options:", opts)

    ctx.close()
