import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Check all li elements inside the stepper
    lis = page.locator("ul li, div[class*='stepper'] li").all()
    print("Stepper list items count:", len(lis))
    for idx, li in enumerate(lis):
        print(f"  [{idx}]: {li.inner_text().strip().replace(chr(10), ' ')}")

    # Is there a Teacher's Feedback step?
    tf_el = page.locator("li, div").filter(has_text="Teacher's Feedback").first
    print("Teacher's Feedback visible:", tf_el.is_visible())
    if tf_el.is_visible():
        tf_el.click()
        time.sleep(2)
        page.screenshot(path='audit_evidence/middle_step7_tf.png')

    ctx.close()
