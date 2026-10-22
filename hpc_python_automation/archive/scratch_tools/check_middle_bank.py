import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def check_middle_bank():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Opening Activity Bank...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
        time.sleep(2)

        # Select Middle in Stage dropdown
        stage_dd = page.locator(".custom-dropdown-header:has-text('Foundational')").first
        if stage_dd.is_visible():
            stage_dd.click()
            time.sleep(1)
            opt = page.locator(".custom-dropdown-item:has-text('Middle')").first
            if opt.is_visible():
                opt.click()
                time.sleep(1)

        # Click Search
        search_btn = page.locator("button:has-text('Search'), svg.MuiSvgIcon-root").first
        search_btn.click()
        time.sleep(2)

        # Check Global Activities button (the second orange button at top next to +)
        btn2 = page.locator("button, a").filter(has=page.locator("svg, img")).all()
        page.screenshot(path='audit_evidence/middle_bank_search.png')

        rows = page.locator("table tbody tr").all()
        print(f"My Activity Bank rows: {len(rows)}")
        for idx, r in enumerate(rows):
            print(f"  [{idx}]: {r.inner_text().strip().replace(chr(10), ' | ')}")

        ctx.close()

if __name__ == '__main__':
    check_middle_bank()
