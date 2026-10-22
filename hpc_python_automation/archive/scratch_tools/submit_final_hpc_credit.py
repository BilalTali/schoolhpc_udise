import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Navigating to Part-C...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-C', wait_until='networkidle')
        time.sleep(3)
        page.screenshot(path='audit_evidence/on_part_c.png')

        # Click Continue on Part-C
        print("[2] Clicking Continue on Part-C...")
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)
        print("Current URL:", page.url)
        page.screenshot(path='audit_evidence/now_on_hpc_credit.png')

        # We should now be on HPC Credit!
        print("[3] Filling 12 marks inputs on HPC Credit...")
        inputs = page.locator("table").last.locator("input[type=number], input[type=text]").all()
        visible_inputs = [inp for inp in inputs if inp.is_visible() and inp.is_enabled()]
        print(f"Found {len(visible_inputs)} active inputs on HPC Credit")

        # Fill 12 inputs (6 pairs of 33, 28)
        for i in range(0, len(visible_inputs), 2):
            visible_inputs[i].triple_click()
            visible_inputs[i].fill("33")
            time.sleep(0.1)
            if i + 1 < len(visible_inputs):
                visible_inputs[i+1].triple_click()
                visible_inputs[i+1].fill("28")
                time.sleep(0.1)

        # Check declaration checkbox
        print("[4] Checking Declaration checkbox...")
        page.evaluate("""() => {
            document.querySelectorAll("input[type='checkbox']").forEach(cb => {
                if (!cb.checked) cb.click();
            });
        }""")
        time.sleep(1)

        # Click Save as Draft
        print("[5] Clicking Save as Draft...")
        page.locator("button:has-text('Save as Draft')").first.click()
        time.sleep(2)
        page.screenshot(path='audit_evidence/credit_draft_saved.png')

        # Click Mark as Complete!
        print("[6] Clicking Mark as Complete...")
        page.locator("button:has-text('Mark as Complete')").first.click()
        time.sleep(2)

        # Confirm modal if any
        modal_btn = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), .modal button:has-text('Confirm'), .modal button:has-text('Complete')").first
        if modal_btn.is_visible():
            modal_btn.click()
            print("Clicked confirmation dialog button!")
            time.sleep(3)

        page.screenshot(path='audit_evidence/final_after_mark_complete.png')

        # Check final roster
        print("\n[7] Checking Live Roster status...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage', wait_until='networkidle')
        time.sleep(3)
        page.screenshot(path='audit_evidence/live_roster_celebration.png')

        rows = page.locator("table tbody tr").all()
        for r in rows:
            t = r.inner_text().strip().replace('\n', ' | ')
            if 'ARKAN' in t.upper():
                print(f'\n>>> FINAL LIVE ROSTER STATUS: {t} <<<\n')

        ctx.close()

if __name__ == '__main__':
    run()
