import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Inspect Step 5
    page.locator('li').filter(has_text='Self Reflection').first.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/step5_detail_top.png')

    # Scroll down container
    page.evaluate("() => { const c = document.querySelector('.activation-tab-content') || window; c.scrollTop = 500; window.scrollTo(0, 500); }")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step5_detail_mid.png')

    page.evaluate("() => { const c = document.querySelector('.activation-tab-content') || window; c.scrollTop = 1200; window.scrollTo(0, 1200); }")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step5_detail_bottom.png')

    # Also inspect all inputs/elements inside step 5
    info5 = page.evaluate("""() => {
        const inps = Array.from(document.querySelectorAll('input, textarea, button, select, [role=radio], li.assessment-smiley-yes, li.assessment-smiley-something, li.assessment-smiley-no'));
        return inps.map(el => ({
            tag: el.tagName,
            type: el.type,
            name: el.name,
            id: el.id,
            className: el.className,
            value: el.value,
            checked: el.checked,
            disabled: el.disabled,
            visible: el.offsetParent !== null,
            text: el.innerText ? el.innerText.trim().substring(0, 40) : ''
        }));
    }""")
    print(f"Step 5 elements ({len(info5)}):")
    for item in info5:
        if item['visible']:
            print(" ", item)

    # Now inspect Step 7
    page.locator('li').filter(has_text="Teacher's Feedback").first.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/step7_detail_top.png')
    page.evaluate("() => { const c = document.querySelector('.activation-tab-content') || window; c.scrollTop = 500; window.scrollTo(0, 500); }")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step7_detail_mid.png')
    page.evaluate("() => { const c = document.querySelector('.activation-tab-content') || window; c.scrollTop = 1200; window.scrollTo(0, 1200); }")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step7_detail_bottom.png')

    info7 = page.evaluate("""() => {
        const inps = Array.from(document.querySelectorAll('input, textarea, button, select, [role=radio]'));
        return inps.map(el => ({
            tag: el.tagName,
            type: el.type,
            name: el.name,
            id: el.id,
            className: el.className,
            value: el.value,
            checked: el.checked,
            disabled: el.disabled,
            visible: el.offsetParent !== null,
            text: el.innerText ? el.innerText.trim().substring(0, 40) : ''
        }));
    }""")
    print(f"\nStep 7 elements ({len(info7)}):")
    for item in info7:
        if item['visible']:
            print(" ", item)

    ctx.close()
