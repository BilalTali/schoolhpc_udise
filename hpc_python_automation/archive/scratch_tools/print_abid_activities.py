import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    
    btns = page.locator(".already-activity-selected ul li button").all()
    print(f"Total activity buttons: {len(btns)}")
    for i, b in enumerate(btns):
        b.click()
        time.sleep(1)
        # read the activated-activity-view text
        view = page.locator(".activated-activity-view").first.inner_text().replace('\n', ' | ')
        print(f"Activity {i+1}: {view}")

    ctx.close()
