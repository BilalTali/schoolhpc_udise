import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_action():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Navigating to Middle Stage roster...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(3)

        row0 = page.locator("table tbody tr").first
        print("Row 0 text:", repr(row0.inner_text().replace('\n', ' | ')))

        # Inspect all interactive elements in row 0
        last_cell = row0.locator("td").last
        print("Last cell HTML:", repr(last_cell.inner_html()))

        # Click the action button / icon in row 0
        action_trigger = last_cell.locator("svg, button, div, span").first
        if action_trigger.is_visible():
            print("Clicking action trigger...")
            action_trigger.click()
            time.sleep(2)
            page.screenshot(path='audit_evidence/middle_row0_action_menu.png')

            # Check what popover/menu items appeared
            popovers = page.locator(".dropdown-menu, [role=menu], ul.menu, .popover, div[class*='menu']").all()
            print(f"Found {len(popovers)} menu containers")
            for p_idx, pop in enumerate(popovers):
                if pop.is_visible():
                    print(f"Menu[{p_idx}]:", repr(pop.inner_text().replace('\n', ' | ')))

            # Also check all visible links that just appeared
            links = page.locator("a:visible").all()
            for lnk in links:
                href = lnk.get_attribute("href")
                if href and ("hpc" in href or "middle" in href):
                    print(f"Visible HPC Link: text='{lnk.inner_text().strip()}', href='{href}'")

        ctx.close()

if __name__ == '__main__':
    inspect_action()
