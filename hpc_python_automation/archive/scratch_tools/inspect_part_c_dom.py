import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-C', wait_until='networkidle')
    time.sleep(2)

    # Let's see what interactive elements exist in Part C besides textareas
    elements = page.locator("div[role='button'], button, img[src*='gauge'], input").all()
    print("Found interactive elements:", len(elements))
    for el in elements:
        tag = el.evaluate("(e) => ({ tag: e.tagName, className: e.className, text: e.innerText, src: e.getAttribute('src'), id: e.id })")
        if 'gauge' in str(tag) or 'level' in str(tag) or tag.get('tag') == 'BUTTON':
            print("  Element:", tag)

    # Let's test clicking Continue to see what validation error happens or if network request fires
    print("\nClicking Continue...")
    page.on("response", lambda r: print("API:", r.status, r.url, r.text()[:200] if 'json' in r.headers.get('content-type', '') else ''))
    cont_btn = page.locator("button:has-text('Continue')").first
    cont_btn.click()
    time.sleep(3)
    print("URL after Continue:", page.url)

    ctx.close()
