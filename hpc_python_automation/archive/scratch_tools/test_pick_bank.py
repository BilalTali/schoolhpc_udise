import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url) if 'hpc' in r.url or 'activit' in r.url else None)
    
    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)

    # Click Pick from Activity Bank
    page.locator("label, div").filter(has_text="Pick from Activity Bank").last.click()
    time.sleep(1)

    # Click Continue
    page.locator(".modal button:has-text('Continue'), [role=dialog] button:has-text('Continue')").first.click()
    time.sleep(3)

    page.screenshot(path='audit_evidence/middle_pick_bank_step2.png')

    modals = page.locator(".modal, [role=dialog]").all()
    for m in modals:
        if m.is_visible():
            print("Visible modal text:", m.inner_text().replace('\n', ' | ')[:300])

    ctx.close()
