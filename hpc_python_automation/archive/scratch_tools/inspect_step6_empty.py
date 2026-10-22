import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Step 6
    page.locator('li').filter(has_text='Peer Feedback').first.click()
    time.sleep(2)

    empty_step6 = page.evaluate("""() => {
        const empty = [];
        document.querySelectorAll('input, textarea, select').forEach(el => {
            if (el.offsetParent !== null) { // visible
                if ((el.type === 'text' || el.tagName === 'TEXTAREA') && !el.value.trim()) {
                    empty.push({ tag: el.tagName, placeholder: el.placeholder, name: el.name, id: el.id });
                }
            }
        });
        return empty;
    }""")
    print("Empty visible inputs in Step 6:", len(empty_step6), empty_step6)

    ctx.close()
