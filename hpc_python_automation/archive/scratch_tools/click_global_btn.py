import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(2)

    btn = page.locator("button[title*='Global'], button:has-text('Import from Global')").first
    print("Found btn:", btn.is_visible(), btn.inner_text(), btn.get_attribute('title'))
    btn.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/after_real_global_click.png')

    modals = page.locator(".modal, [role=dialog], div[class*='modal']").all()
    print("Modals found:", len(modals))
    for m in modals:
        if m.is_visible():
            print("Modal text:", m.inner_text().replace('\n', ' | ')[:200])

    ctx.close()
