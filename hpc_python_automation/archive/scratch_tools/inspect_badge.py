import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    res = page.evaluate("""() => {
        const els = Array.from(document.querySelectorAll('*')).filter(e => e.innerText && (e.innerText.trim() === '10' || e.innerText.trim() === '2') && e.children.length === 0);
        return els.map(e => ({
            tag: e.tagName,
            text: e.innerText,
            class: e.className,
            style: e.getAttribute('style'),
            parent: e.parentElement.tagName,
            parentClass: e.parentElement.className,
            parentHTML: e.parentElement.outerHTML.substring(0, 200)
        }));
    }""")
    print("Found badge elements:", res)
    ctx.close()
