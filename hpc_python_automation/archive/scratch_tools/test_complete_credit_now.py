import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url[:110], r.text()[:250] if 'json' in r.headers.get('content-type', '') else '') if any(k in r.url for k in ['hpc', 'save', 'complete']) else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Continue to Part C
    cont_b = page.locator("button:has-text('Continue')").first
    print("Clicking Continue from Part B to Part C...")
    cont_b.click()
    time.sleep(3)

    print("Arrived on Part C, URL:", page.url)
    page.screenshot(path='audit_evidence/middle_credit_step1_part_c.png')

    # Click Continue on Part C to reach HPC Credit
    cont_c = page.locator("button:has-text('Continue')").first
    print("Clicking Continue from Part C to HPC Credit...")
    cont_c.click()
    time.sleep(3)

    print("Arrived on HPC Credit, URL:", page.url)
    page.screenshot(path='audit_evidence/middle_credit_step2_credit.png')

    # Click declaration checkbox
    cb = page.locator("input[type=checkbox]").last
    cb.evaluate("(el) => { if (!el.checked) el.click(); }")
    time.sleep(1)

    # Click Mark as Complete!
    mark_btn = page.locator("button:has-text('Mark as Complete')").first
    print("Mark as Complete button visible:", mark_btn.is_visible())
    mark_btn.click(force=True)
    time.sleep(2)

    page.screenshot(path='audit_evidence/middle_credit_step3_modal.png')

    # Modal Yes
    modal_btns = page.locator(".modal button, [role=dialog] button, .swal2-confirm, div.modal-footer button").all()
    print(f"Modal buttons count: {len(modal_btns)}")
    for b in modal_btns:
        txt = b.inner_text().strip()
        print("  Modal btn:", txt)
        if any(w in txt.lower() for w in ["yes", "confirm", "complete", "ok"]):
            print(f"  --> Clicking: '{txt}'")
            b.click(force=True)
            time.sleep(5)
            break

    page.screenshot(path='audit_evidence/middle_credit_step4_final.png')

    # Check live roster
    print("\nChecking Middle Stage live roster...")
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
    time.sleep(3)
    rows = page.locator("table tbody tr").all()
    for r in rows:
        txt = r.inner_text().strip().replace('\n', ' | ')
        if 'ARBAZ' in txt.upper():
            print(f">>> LIVE STATUS FOR ARBAZ: {txt} <<<")

    ctx.close()
