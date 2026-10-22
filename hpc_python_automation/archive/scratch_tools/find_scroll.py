import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Step 7
    s7 = page.locator("li").filter(has_text="Teacher's Feedback").first
    s7.scroll_into_view_if_needed()
    s7.click(force=True)
    time.sleep(2)

    # Find the scrollable container and scroll it
    scroll_res = page.evaluate("""() => {
        const scrollables = [];
        document.querySelectorAll('*').forEach(el => {
            if (el.scrollHeight > el.clientHeight && el.clientHeight > 100) {
                scrollables.push({
                    tag: el.tagName,
                    cls: el.className,
                    sh: el.scrollHeight,
                    ch: el.clientHeight
                });
                el.scrollTop = 800; // scroll it!
            }
        });
        return scrollables;
    }""")
    print("Scrollable containers found:", scroll_res)
    time.sleep(1)
    page.screenshot(path='audit_evidence/step7_after_real_scroll.png')

    ctx.close()
