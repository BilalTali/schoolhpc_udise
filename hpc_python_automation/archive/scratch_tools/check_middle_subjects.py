import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def import_all_middle_domains():
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
        # Select Stage = Middle
        stage_dd = modal.locator(".custom-dropdown-header:has-text('Foundational')").first
        if stage_dd.is_visible():
            stage_dd.click()
            time.sleep(1)
            opt = page.locator(".custom-dropdown-item:has-text('Middle')").first
            if opt.is_visible():
                opt.click()
                time.sleep(2)

        # Check Subject dropdown in modal
        subj_header = modal.locator("label:has-text('Subject')").locator("xpath=ancestor::div[contains(@class, 'custom-dropdown-wrapper')]").locator(".custom-dropdown-header").first
        if subj_header.is_visible():
            subj_header.click()
            time.sleep(1)
            subjs = page.locator(".custom-dropdown-item").all_inner_texts()
            print("Available Subjects in Middle Global Bank:", subjs)
            subj_header.click() # close

        ctx.close()

if __name__ == '__main__':
    import_all_middle_domains()
