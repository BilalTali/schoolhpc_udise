import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_part_c_and_credit():
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

        # Click top stepper directly or click Continue
        # Check if stepper icons are clickable
        step_c = page.locator(".stepper-item:has-text('C'), div[class*='step']:has-text('C'), span:has-text('C')").first
        print("Clicking Part C stepper...")
        # Or let's click Continue from A1 -> A2 -> A3 -> A4 -> B -> C -> Credit
        for s in range(5):
            btn = page.locator("button:has-text('Continue')").first
            if btn.is_visible():
                btn.click()
                time.sleep(2)

        print("Now on:", page.locator("h2, h3, h4, div[class*='title']").all_inner_texts()[:3])
        page.screenshot(path='audit_evidence/middle_step_6_part-C.png')

        # Check Part C inputs
        c_inputs = page.locator("input:visible, textarea:visible").all()
        print(f"Part C visible inputs: {len(c_inputs)}")
        for i, inp in enumerate(c_inputs[:10]):
            print(f"  inp[{i}]: placeholder={repr(inp.get_attribute('placeholder'))}, val={repr(inp.input_value())}")

        # Click Continue to HPC Credit
        btn = page.locator("button:has-text('Continue')").first
        if btn.is_visible():
            btn.click()
            time.sleep(2)

        print("Now on Credit:", page.locator("h2, h3, h4, div[class*='title']").all_inner_texts()[:3])
        page.screenshot(path='audit_evidence/middle_step_7_hpc-credit.png')

        credit_inputs = page.locator("input:visible").all()
        print(f"HPC Credit visible inputs: {len(credit_inputs)}")
        for i, inp in enumerate(credit_inputs):
            print(f"  credit_inp[{i}]: val={repr(inp.input_value())}, ro={inp.get_attribute('readonly')}")

        ctx.close()

if __name__ == '__main__':
    inspect_part_c_and_credit()
