import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def check_middle_activities():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Opening Activity Bank directly...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
        time.sleep(2)

        # Check stage dropdown on Activity Bank
        # Switch to Middle Stage if there is a stage dropdown
        stage_sel = page.locator(".custom-dropdown-header, select").first
        print("Stage selector text:", stage_sel.inner_text().replace('\n', ' | '))

        page.screenshot(path='audit_evidence/middle_activity_bank_direct.png')

        # Check Global Activities tab
        global_tab = page.locator("button:has-text('Global'), div:has-text('Global Activities'), a:has-text('Global')").first
        if global_tab.is_visible():
            print("Clicking Global Activities tab...")
            global_tab.click()
            time.sleep(2)
            page.screenshot(path='audit_evidence/middle_global_activities_tab.png')

            cards = page.locator(".activity-card, div[class*='card'], table tr").all()
            print(f"Activities found: {len(cards)}")
            for idx, c in enumerate(cards[:15]):
                txt = c.inner_text().strip().replace('\n', ' | ')
                if txt:
                    print(f"  [{idx}] {txt[:80]}")

        ctx.close()

if __name__ == '__main__':
    check_middle_activities()
