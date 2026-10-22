import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(3)
    
    # Check what activities Abid has
    items = page.locator("div.step-item, div[class*='activity']").all()
    print(f"Total items: {len(items)}")

    # Let's inspect step 2
    step2 = page.locator("text='Subject, CG & Competencies'").first
    if step2.is_visible():
        step2.click()
        time.sleep(2)
        page.screenshot(path='audit_evidence/abid_step2.png')
        print("Captured step 2 screenshot")
    
    # Also inspect HPC Credit of Abid!
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/hpc-credit', wait_until='networkidle')
    time.sleep(3)
    page.screenshot(path='audit_evidence/abid_hpc_credit.png')
    print("Captured Abid HPC credit screenshot")

    ctx.close()
