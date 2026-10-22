import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_middle_part_c():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-C"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        headings = page.locator("h3, h4, h5, .subject-title, div[class*='subject']").all()
        print(f"Headings count: {len(headings)}")
        for h in headings:
            t = h.inner_text().strip()
            if t:
                print("  Subject:", repr(t))

        # Check all textareas
        textareas = page.locator("textarea").all()
        print(f"Total textareas on Part C: {len(textareas)}")

        # Check all checkboxes / radio inputs
        inputs = page.locator("input[type=checkbox], input[type=radio]").all()
        print(f"Total checkbox/radio inputs on Part C: {len(inputs)}")

        ctx.close()

if __name__ == '__main__':
    inspect_middle_part_c()
