import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url[:120], r.text()[:250] if 'json' in r.headers.get('content-type', '') else '') if any(k in r.url for k in ['hpc', 'save', 'complete', 'finish']) else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text="Teacher's Feedback").first.click()
    time.sleep(2)

    # Fill all text inputs and textareas in Step 7
    page.evaluate("""() => {
        // Uncheck 'Any Other' or fill their inputs
        document.querySelectorAll("input[type=text]").forEach(inp => {
            if (inp.offsetParent !== null && !inp.disabled) {
                inp.value = "Consistent performance";
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        document.querySelectorAll("textarea").forEach(ta => {
            if (ta.offsetParent !== null && !ta.disabled) {
                ta.value = "Student demonstrates strong conceptual understanding, actively participates in group tasks, and shows consistent academic enthusiasm. Recommendations include continuous practice with real-world problems and active participation in peer learning.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # Save as Draft
    page.locator("button:has-text('Save as Draft')").first.click()
    time.sleep(3)
    page.screenshot(path='audit_evidence/middle_step7_filled_ready.png')

    # Click Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Clicking Finish Activity, visible:", fa_btn.is_visible())
    fa_btn.click()
    time.sleep(2)

    page.screenshot(path='audit_evidence/middle_finish_modal_opened.png')

    # Look for confirm button in modal
    modal_btns = page.locator(".modal button, [role=dialog] button, div.modal-content button, .swal2-confirm").all()
    print(f"Found {len(modal_btns)} modal buttons")
    for b in modal_btns:
        txt = b.inner_text().strip()
        print("  Modal btn:", txt)
        if any(w in txt.lower() for w in ["yes", "confirm", "finish", "ok"]):
            print(f"  --> Clicking modal confirm: '{txt}'")
            b.click()
            time.sleep(4)
            break

    page.screenshot(path='audit_evidence/middle_after_finish_confirmed_success.png')

    # Now check Continue button
    cont = page.locator("button:has-text('Continue')").first
    print("Continue button visible:", cont.is_visible())
    if cont.is_visible():
        cont.click()
        time.sleep(3)
        print("URL after Continue:", page.url)

    ctx.close()
