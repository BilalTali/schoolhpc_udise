import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(2)

    btn = page.locator("button[title*='Global'], button:has-text('Import from Global')").first
    btn.click()
    time.sleep(2)

    # In modal: check the Subject(s)* dropdown options
    # Or check what checkboxes exist in the modal
    modal = page.locator(".modal, [role=dialog]").first
    cbs = modal.locator("input[type=checkbox]").all()
    print("Checkboxes in modal:", len(cbs))

    # Let's check how many rows/activities are listed
    rows = modal.locator(".modal-body tr, .modal-body li, div[class*='item'], label").all()
    print("Items found:", len(rows))
    
    page.screenshot(path='audit_evidence/global_modal_details.png')
    ctx.close()
