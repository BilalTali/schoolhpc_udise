import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    if fa_btn.is_visible():
        print("Clicking Finish Activity...")
        fa_btn.click()
        time.sleep(2)

        # Confirm dialog if any
        modal_btn = page.locator(".modal button, [role=dialog] button").all()
        for b in modal_btn:
            print("Modal btn:", b.inner_text().strip())
            if any(w in b.inner_text().lower() for w in ["yes", "confirm", "finish", "ok"]):
                print("Clicking confirm in finish modal...")
                b.click()
                time.sleep(3)
                break

    page.screenshot(path='audit_evidence/middle_after_finish_activity.png')

    # Continue to Part C
    cont_b = page.locator("button:has-text('Continue')").first
    if cont_b.is_visible():
        print("Continuing to Part C...")
        cont_b.click()
        time.sleep(3)

    # On Part C: continue to HPC Credit
    print("On Part C, URL:", page.url)
    cont_c = page.locator("button:has-text('Continue')").first
    if cont_c.is_visible():
        print("Continuing to HPC Credit...")
        cont_c.click()
        time.sleep(3)

    print("On HPC Credit, URL:", page.url)
    page.screenshot(path='audit_evidence/middle_credit_reached_after_domain_fix.png')

    # Now let's try MARK AS COMPLETE!
    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:250] if 'json' in r.headers.get('content-type', '') else ''))

    cb = page.locator('input[type=checkbox]').last
    cb.evaluate('(el) => { if (!el.checked) el.click(); }')
    time.sleep(1)

    mark_btn = page.locator("button:has-text('Mark as Complete')").first
    if mark_btn.is_visible():
        print("Clicking Mark as Complete...")
        mark_btn.click(force=True)
        time.sleep(2)

        modal_yes = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), button:has-text('Confirm')").first
        if modal_yes.is_visible():
            print("Modal Yes visible! Text:", modal_yes.inner_text())
            modal_yes.click(force=True)
            time.sleep(4)

    page.screenshot(path='audit_evidence/middle_final_status_after_mark_complete.png')

    # Check live roster
    print("\nNavigating to Middle Stage live roster...")
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
    time.sleep(3)
    rows = page.locator("table tbody tr").all()
    for r in rows:
        txt = r.inner_text().strip().replace('\n', ' | ')
        if 'ARBAZ' in txt.upper():
            print(f">>> LIVE STATUS FOR ARBAZ: {txt} <<<")

    ctx.close()
