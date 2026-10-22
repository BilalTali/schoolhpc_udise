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

    # Click Step 5
    s5 = page.locator("li").filter(has_text="Self Reflection").first
    s5.click()
    time.sleep(2)

    # Let's scroll .activation-tab-content
    page.evaluate("""() => {
        const pane = document.querySelector('.activation-tab-content');
        if (pane) pane.scrollTop = 400;
    }""")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step5_scrolled_middle.png')

    page.evaluate("""() => {
        const pane = document.querySelector('.activation-tab-content');
        if (pane) pane.scrollTop = 1000;
    }""")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step5_scrolled_bottom.png')

    ctx.close()
