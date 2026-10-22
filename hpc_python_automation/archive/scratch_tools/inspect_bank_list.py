import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    
    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)
    
    # Click Pick from Activity Bank radio
    page.locator("label:has-text('Pick from Activity Bank'), input[value*='bank'], input[type=radio]").last.click()
    time.sleep(1)
    page.locator("button:has-text('Continue')").last.click()
    time.sleep(2)
    
    # Take screenshot of the activity bank list
    page.screenshot(path='audit_evidence/activity_bank_list.png')
    
    # Print all activities shown in the bank
    cards = page.locator(".modal table tr, .modal .card, .modal .list-group-item, .modal div[class*='activity']").all_inner_texts()
    print("Found cards:", len(cards))
    for c in cards[:15]:
        print("--- CARD ---")
        print(c.strip())

    ctx.close()
