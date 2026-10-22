import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Let's inspect the vertical stepper HTML completely!
    stepper_html = page.evaluate("""() => {
        const lis = document.querySelectorAll('li');
        return Array.from(lis).filter(l => l.innerText && l.innerText.includes('Reflection')).map(l => l.outerHTML);
    }""")
    print("Step 5 LI outerHTML:")
    for h in stepper_html:
        print(h)

    # Now let's open Step 5
    page.locator('li').filter(has_text='Self Reflection').first.click()
    time.sleep(2)

    # Inspect all elements with error class or invalid attribute
    errors = page.evaluate("""() => {
        const errs = document.querySelectorAll('.error, .is-invalid, [aria-invalid="true"], .required, .mandatory');
        return Array.from(errs).map(e => ({
            tag: e.tagName,
            cls: e.className,
            text: e.innerText ? e.innerText.trim().slice(0, 50) : '',
            parent: e.parentElement ? e.parentElement.className : ''
        }));
    }""")
    print("Error / invalid elements in Step 5:", len(errors), errors)

    # Inspect all field labels with an asterisk in Step 5
    asterisks = page.evaluate("""() => {
        const pane = document.querySelector('div.scrolled-outer, div.outer-white, .step-content') || document.body;
        const labs = pane.querySelectorAll('label, p, span, h4, h5');
        return Array.from(labs).filter(l => l.innerText && l.innerText.includes('*')).map(l => l.innerText.trim().replace(/\\n/g, ' '));
    }""")
    print("Mandatory fields (with *):", asterisks[:15])

    ctx.close()
