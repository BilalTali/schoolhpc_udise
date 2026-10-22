import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:200] if 'json' in r.headers.get('content-type', '') else '') if 'activit' in r.url else None)

    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(2)

    btn = page.locator("button[title*='Global'], button:has-text('Import from Global')").first
    btn.click()
    time.sleep(2)

    modal = page.locator(".modal, [role=dialog]").first
    cbs = modal.locator("input[type=checkbox]").all()
    print(f"Selecting {len(cbs)} checkboxes in modal...")
    for cb in cbs:
        cb.evaluate("(el) => { if (!el.checked) el.click(); }")

    time.sleep(1)
    import_btn = modal.locator("button:has-text('Import')").first
    print("Clicking Import button...")
    import_btn.click()
    time.sleep(4)

    page.screenshot(path='audit_evidence/after_import_50_activities.png')
    ctx.close()
