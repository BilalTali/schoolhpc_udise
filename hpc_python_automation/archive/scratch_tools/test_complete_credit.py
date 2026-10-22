import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:300] if 'json' in r.headers.get('content-type', '') else ''))
    
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/hpc-credit', wait_until='networkidle')
    time.sleep(2)

    # Check declaration
    cb = page.locator('input[type=checkbox]').last
    cb.evaluate('(el) => { if (!el.checked) el.click(); }')
    time.sleep(1)

    print("Locating Mark as Complete button...")
    mark_btn = page.get_by_role("button", name="Mark as Complete")
    print("Is visible:", mark_btn.is_visible())
    print("Clicking Mark as Complete...")
    mark_btn.click(force=True)
    time.sleep(2)

    page.screenshot(path='audit_evidence/middle_after_click_modal.png')

    # Look for confirm dialog / modal
    modal_btn = page.locator(".modal button, [role=dialog] button").all()
    print("Modal buttons:", len(modal_btn))
    for b in modal_btn:
        print("  Modal btn:", b.inner_text().strip())
        if any(w in b.inner_text().lower() for w in ["yes", "confirm", "complete", "ok"]):
            print("  Clicking confirm modal button...")
            b.click(force=True)
            time.sleep(3)
            break

    page.screenshot(path='audit_evidence/middle_after_modal_confirm.png')
    ctx.close()
