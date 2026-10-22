import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def pick_middle_global_activities():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Opening Activity Bank...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
        time.sleep(2)

        # Click the 2nd button (Global Activity Bank)
        top_btns = page.locator(".content-header button, div.d-flex button, div:has-text('My Activity Bank') button").all()
        top_btns[1].click()
        time.sleep(2)

        modal = page.locator(".modal, [role=dialog], div[class*='modal']").first
        print("Modal visible:", modal.is_visible())

        # Select Stage = Middle in the modal
        stage_dd = modal.locator(".custom-dropdown-header:has-text('Foundational')").first
        if stage_dd.is_visible():
            stage_dd.click()
            time.sleep(1)
            opt = page.locator(".custom-dropdown-item:has-text('Middle')").first
            if opt.is_visible():
                opt.click()
                time.sleep(2)

        page.screenshot(path='audit_evidence/modal_middle_activities.png')

        # Check the checklist of activities in the modal
        labels = modal.locator("label").all_inner_texts()
        print("Middle Global Activities:", labels)

        # Check all checkboxes in modal and click Import
        cbs = modal.locator("input[type=checkbox]").all()
        print(f"Total activity checkboxes: {len(cbs)}")
        for cb in cbs:
            if not cb.is_checked():
                cb.check()

        import_btn = modal.locator("button:has-text('Import')").first
        if import_btn.is_visible():
            print("Clicking Import...")
            import_btn.click()
            time.sleep(3)
            page.screenshot(path='audit_evidence/after_import_middle_activities.png')

        ctx.close()

if __name__ == '__main__':
    pick_middle_global_activities()
