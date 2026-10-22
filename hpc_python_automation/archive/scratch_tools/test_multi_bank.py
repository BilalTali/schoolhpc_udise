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
    
    # Click "Global Activities" tab
    page.locator("text='Global Activities'").first.click()
    time.sleep(1)
    
    # Check all visible checkboxes in the modal!
    chks = page.locator(".modal input[type=checkbox]").all()
    print(f"Found {len(chks)} checkboxes in Global Activities modal")
    for i, chk in enumerate(chks):
        chk.click()
        print(f"Checked checkbox {i}")
        time.sleep(0.3)
        
    page.screenshot(path='audit_evidence/checked_all_bank.png')
    
    use_btn = page.locator(".modal button:has-text('Use Activity')").first
    print("Use Activity enabled?", use_btn.is_enabled())
    if use_btn.is_enabled():
        use_btn.click()
        time.sleep(3)
        page.screenshot(path='audit_evidence/after_use_all_activities.png')
        print("Clicked Use Activity!")

    ctx.close()
