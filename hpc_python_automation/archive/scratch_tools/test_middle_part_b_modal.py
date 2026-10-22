import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_middle_part_b_modal():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        add_btn = page.locator("button:has-text('Add Activity')").first
        if add_btn.is_visible():
            print("Clicking Add Activity...")
            add_btn.click()
            time.sleep(2)
            page.screenshot(path='audit_evidence/middle_add_activity_modal.png')

            dialog = page.locator(".modal, [role=dialog], div[class*='modal']").first
            if dialog.is_visible():
                print("Modal text:", dialog.inner_text().replace('\n', ' | '))

        ctx.close()

if __name__ == '__main__':
    test_middle_part_b_modal()
