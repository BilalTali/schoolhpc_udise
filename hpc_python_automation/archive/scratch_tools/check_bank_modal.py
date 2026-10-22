import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    
    # Check current activities
    print("Opening Add Activity on Arkan Ahmad...")
    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)
    
    # In modal: choose Pick from Activity Bank
    page.locator("text='Pick from Activity Bank'").first.click()
    time.sleep(0.5)
    page.locator(".modal button:has-text('Continue')").first.click()
    time.sleep(2)
    
    page.screenshot(path='audit_evidence/arkan_bank_modal.png')
    
    # Check what activities are in the modal table/list
    rows = page.locator(".modal table tr, .modal div[class*='card'], .modal .activity-bank-item").all_inner_texts()
    print(f"Found {len(rows)} bank rows:")
    for r in rows[:20]:
        print("  ->", r.strip().replace('\n', ' | '))

    ctx.close()
