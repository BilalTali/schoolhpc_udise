import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:250] if 'json' in r.headers.get('content-type', '') else '') if 'hpc' in r.url else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Finish Activity button visible:", fa_btn.is_visible())
    fa_btn.click()
    time.sleep(2)

    # Check for modals
    modals = page.locator(".modal, [role=dialog]").all()
    print("Modals count:", len(modals))
    for m in modals:
        if m.is_visible():
            print("Modal visible text:", m.inner_text().replace('\n', ' | '))
            btn = m.locator("button:has-text('Yes'), button:has-text('Confirm'), button:has-text('OK')").first
            if btn.is_visible():
                print("Clicking confirm in modal:", btn.inner_text())
                btn.click()
                time.sleep(3)

    page.screenshot(path='audit_evidence/after_finish_clicked_clean.png')
    ctx.close()
