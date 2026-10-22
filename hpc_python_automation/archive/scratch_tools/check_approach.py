import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Click Step 3: Activity
    page.locator('li').filter(has_text='Activity').first.click()
    time.sleep(1)

    # Check Approach checkboxes
    cbs = page.locator('input[type=checkbox]').all()
    print("Checkboxes found:", len(cbs))
    for cb in cbs:
        txt = cb.evaluate("(e) => e.parentElement ? e.parentElement.innerText : ''")
        if any(w in txt for w in ['Art-Integrated', 'Technology-Integrated', 'Sports-Integrated', 'Toy-Based']):
            cb.evaluate("(e) => { if (!e.checked) e.click(); }")
            print("  Checked approach:", txt.strip())
            break

    # Also fill any textareas in Step 3
    for t in page.locator("textarea:visible:not([disabled])").all():
        if not t.input_value():
            t.fill("Scientific inquiry and project presentation.")

    # Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    sd.click()
    time.sleep(2)

    # Now let's try Finish Activity!
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Clicking Finish Activity...")
    fa_btn.click()
    time.sleep(2)

    modals = page.locator(".modal, [role=dialog]").all()
    print("Modals found:", len(modals))
    for m in modals:
        if m.is_visible():
            print("Modal visible:", m.inner_text().replace('\n', ' | '))
            btn = m.locator("button:has-text('Yes'), button:has-text('Confirm'), button:has-text('OK')").first
            if btn.is_visible():
                btn.click()
                print("Confirmed finish!")
                time.sleep(3)

    page.screenshot(path='audit_evidence/middle_after_approach_finish.png')
    ctx.close()
