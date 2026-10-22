import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_add_from_bank():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        # Click + Add Activity
        add_btn = page.locator("button:has-text('Add Activity')").first
        add_btn.click()
        time.sleep(2)

        # In modal: Pick from Activity Bank radio
        bank_radio = page.locator("label:has-text('Pick from Activity Bank'), input[value*='bank']").first
        page.evaluate("(el) => el.click()", bank_radio)
        time.sleep(0.5)

        # Click Continue in modal
        cont_btn = page.locator(".modal button:has-text('Continue'), [role=dialog] button:has-text('Continue')").first
        cont_btn.click()
        time.sleep(3)

        page.screenshot(path='audit_evidence/middle_after_pick_bank_cont.png')

        # Check what appears: My Activity Bank list / Global Activities tab
        modal2 = page.locator(".modal, [role=dialog], div[class*='modal']").first
        print("Modal 2 visible:", modal2.is_visible())
        if modal2.is_visible():
            print("Modal 2 text:", modal2.inner_text().replace('\n', ' | ')[:300])

            # Select an activity checkbox / radio
            cbs = modal2.locator("input[type=checkbox], input[type=radio]").all()
            print(f"Found {len(cbs)} activity selectors in bank modal")
            if cbs:
                page.evaluate("(el) => el.click()", cbs[0])
                time.sleep(1)

            # Click Use Activity / Add Activity / Continue
            use_btn = modal2.locator("button:has-text('Use'), button:has-text('Add'), button:has-text('Continue')").last
            if use_btn.is_visible():
                print(f"Clicking '{use_btn.inner_text().strip()}'...")
                use_btn.click()
                time.sleep(3)

        page.screenshot(path='audit_evidence/middle_after_activity_added.png')

        # Check sidebar list of activities
        activities = page.locator(".activity-list-item, div[class*='activity-list'] button, div[class*='activity'] div[class*='title']").all()
        print(f"Activities on student: {len(activities)}")
        for idx, a in enumerate(activities):
            print(f"  [{idx}]: {a.inner_text().strip().replace(chr(10), ' | ')}")

        ctx.close()

if __name__ == '__main__':
    test_add_from_bank()
