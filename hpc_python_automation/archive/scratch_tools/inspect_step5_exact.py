import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Step 5
    page.locator("div, p, span").filter(has_text="Student's Self Reflection").last.click(force=True)
    time.sleep(2)

    page.screenshot(path='audit_evidence/step5_exact_view.png')

    # What elements are inside the step container?
    elements = page.evaluate("""() => {
        const pane = document.querySelector('.step-content, div[class*="content"]');
        if (!pane) return [];
        return Array.from(pane.querySelectorAll('input, textarea, p, span, h4, h5, div')).map(e => ({
            tag: e.tagName,
            type: e.type,
            className: e.className,
            text: e.innerText ? e.innerText.trim().slice(0, 50) : ''
        })).filter(x => x.text || x.tag === 'INPUT' || x.tag === 'TEXTAREA');
    }""")
    print("Found elements in Step 5:", len(elements))
    for el in elements[:30]:
        print(" ", el)

    ctx.close()
