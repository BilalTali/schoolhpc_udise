import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_middle_student():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Opening Middle Stage...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(2)

        # Click Open on row 0 (ARBAZ IQBAL)
        row0 = page.locator("table tbody tr").first
        last_cell = row0.locator("td").last
        action_trigger = last_cell.locator(".custom-dropdown-header, label:has-text('⋮'), svg").first
        action_trigger.click()
        time.sleep(0.5)

        open_opt = page.locator(".custom-dropdown-item:has-text('Open'), li:has-text('Open'), div:has-text('Open')").last
        open_opt.click()
        time.sleep(3)

        print("Current URL:", page.url)
        print("Page title:", page.title())

        # Check all steps in the top navigation bar
        step_items = page.locator(".stepper-item, .step, div[class*='step'], span[class*='step']").all()
        print(f"Step elements: {len(step_items)}")
        for idx, s in enumerate(step_items):
            print(f"  Step[{idx}]:", repr(s.inner_text().strip()))

        # Check all headers/titles
        titles = page.locator("h1, h2, h3, h4, h5, .title, div[class*='title']").all()
        for idx, t in enumerate(titles):
            if t.is_visible():
                print(f"  Title[{idx}]:", repr(t.inner_text().strip()))

        ctx.close()

if __name__ == '__main__':
    inspect_middle_student()
