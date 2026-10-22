import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    print('URL:', page.url)

    # Let's inspect all text and elements in the activity sidebar and steps
    page.screenshot(path='audit_evidence/middle_part_b_overview.png')
    
    # Check left sidebar activity items
    activity_items = page.locator("div.activity-tab-lists li, ul.activity-tab-lists li, .activity-list-item, div[class*='activity-item']").all()
    print("Found activity items in sidebar:", len(activity_items))
    for i, item in enumerate(activity_items):
        print(f"  Item {i}: {item.inner_text().strip().replace(chr(10), ' | ')}")

    # Check sub-steps listed
    steps = page.locator("div.step-item, ul.steps li, div[class*='step']").all()
    print("Steps in current activity:", len(steps))
    for i, s in enumerate(steps):
        txt = s.inner_text().strip().replace(chr(10), ' | ')
        if txt:
            print(f"  Step {i}: {txt}")

    ctx.close()
