import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Let's inspect all items in the vertical sub-step menu
    steppers = page.evaluate("""() => {
        // Find the stepper container
        const items = document.querySelectorAll('div, li, button');
        const found = [];
        items.forEach(el => {
            if (el.innerText && el.innerText.startsWith('5') && el.innerText.includes('Reflection')) {
                found.push({
                    tag: el.tagName,
                    className: el.className,
                    text: el.innerText
                });
            }
        });
        return found;
    }""")
    print("Found Step 5 candidates:", steppers)

    # Click the exact Step 5
    page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('div, li, button, p'));
        const s5 = els.find(e => e.innerText && e.innerText.trim().startsWith('5') && e.innerText.includes('Reflection'));
        if (s5) s5.click();
    }""")
    time.sleep(2)
    page.screenshot(path='audit_evidence/step5_exact_view.png')

    ctx.close()
