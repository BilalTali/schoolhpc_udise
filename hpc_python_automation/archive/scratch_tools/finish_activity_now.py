import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Found Finish Activity button:", fa_btn.is_visible())
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)
        modals = page.locator(".modal, [role=dialog]").all()
        print("Modals found:", len(modals))
        for m in modals:
            if m.is_visible():
                print("Modal text:", m.inner_text().replace('\n', ' | '))
                btn = m.locator("button:has-text('Yes'), button:has-text('Confirm'), button:has-text('OK')").first
                if btn.is_visible():
                    print("Clicking confirm...")
                    btn.click()
                    time.sleep(3)
                    break

    page.screenshot(path='audit_evidence/middle_after_finish_btn_clicked.png')
    ctx.close()
