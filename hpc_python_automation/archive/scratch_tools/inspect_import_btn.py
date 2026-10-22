import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(2)

    # The buttons next to My Activity Bank
    btns = page.locator("div.activity-bank-header button, div[class*='header'] button, button").all()
    for b in btns:
        if b.is_visible():
            print("Button:", b.inner_text().strip(), b.get_attribute("title") or b.get_attribute("aria-label"))

    # Let's find the import button (the second orange button)
    import_btn = page.locator("button:has(svg), button").nth(3) # Let's find it by icon or class
    # Or find all buttons near My Activity Bank
    page.evaluate("""() => {
        const header = Array.from(document.querySelectorAll('*')).find(x => x.innerText && x.innerText.trim() === 'My Activity Bank');
        if (header && header.parentElement) {
            const btns = header.parentElement.querySelectorAll('button');
            console.log('Header buttons count:', btns.length);
            if (btns.length > 1) btns[1].click(); // click the second button!
        }
    }""")
    time.sleep(2)
    page.screenshot(path='audit_evidence/after_click_bank_import.png')
    print("URL after click:", page.url)
    
    ctx.close()
