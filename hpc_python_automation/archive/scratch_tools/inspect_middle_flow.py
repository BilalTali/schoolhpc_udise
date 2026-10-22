import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_all_middle_steps():
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

        steps = ["part-A1", "part-A2", "part-A3", "part-A4", "part-B", "part-C", "hpc-credit"]

        for step_idx in range(len(steps)):
            time.sleep(2)
            cur_title = page.locator("h2, h3, h4, .title, div[class*='title']").all_inner_texts()
            cur_step_title = [t.strip() for t in cur_title if "part" in t.lower() or "credit" in t.lower() or "middle" in t.lower()]
            print(f"\n--- STEP {step_idx+1}: {steps[step_idx]} ---")
            print("  Title segments:", cur_step_title[:3])
            page.screenshot(path=f'audit_evidence/middle_step_{step_idx+1}_{steps[step_idx]}.png')

            # Check form elements on this step
            inputs = page.locator("input:visible, textarea:visible, select:visible").all()
            print(f"  Visible inputs count: {len(inputs)}")
            buttons = [b.inner_text().strip() for b in page.locator("button:visible").all()]
            print(f"  Visible buttons: {buttons}")

            # Advance to next step if not last
            if step_idx < len(steps) - 1:
                cont_btn = page.locator("button:has-text('Continue'), button:has-text('Next')").first
                if cont_btn.is_visible():
                    print("  Clicking Continue...")
                    cont_btn.click()
                    time.sleep(3)
                else:
                    print("  Continue button NOT visible! Trying Save as Draft or looking for tabs...")
                    break

        ctx.close()

if __name__ == '__main__':
    inspect_all_middle_steps()
