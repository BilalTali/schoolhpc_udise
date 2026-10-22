import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(3)
    
    # Click each activity on the sidebar to see its details
    activity_items = page.locator("div[class*='cursor-pointer']").all()
    print(f"Found {len(activity_items)} cursor-pointer items")
    
    # Or let's see how many activities are listed on the left
    left_panel = page.locator("div:has-text('ACTIVITIES -')").first.locator("..").inner_text()
    print("Left Panel Content:\n", left_panel)

    # Let's inspect the activities available in the Activity Bank modal!
    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(2)
    
    bank_modal = page.locator(".modal, [role='dialog']").first
    print("Bank Modal Text:\n", bank_modal.inner_text())

    # Let's see what tabs or categories exist in the modal
    modal_tabs = bank_modal.locator("button, a, .nav-link, select").all_inner_texts()
    print("Modal interactive elements:", modal_tabs)

    ctx.close()
