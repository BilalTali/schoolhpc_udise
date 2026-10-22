import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text='Self Reflection').first.click()
    time.sleep(2)

    # Let's inspect the entire DOM structure of Step 5
    dom_summary = page.evaluate("""() => {
        const pane = document.querySelector('div.scrolled-outer, div.outer-white, .step-content') || document.body;
        // Find all headings, selects, tabs
        const headings = Array.from(pane.querySelectorAll('h1, h2, h3, h4, h5, h6, select, div[class*="select"], div[class*="tab"], div[role="tab"]')).map(e => ({
            tag: e.tagName,
            cls: e.className,
            text: e.innerText ? e.innerText.trim().slice(0, 100) : ''
        }));
        return headings;
    }""")
    print("Headings/tabs/selects in Step 5:")
    for h in dom_summary:
        print(" ", h)

    ctx.close()
