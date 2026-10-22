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
    time.sleep(2)
    
    page.screenshot(path='audit_evidence/global_activities_tab.png')
    
    # Print all items listed under Global Activities
    items = page.locator(".modal table tr, .modal div[role=row], .modal tbody tr").all_inner_texts()
    print(f"Total items in Global Activities: {len(items)}")
    for it in items[:15]:
        print("  Item:", it.strip().replace('\n', ' | '))

    ctx.close()
