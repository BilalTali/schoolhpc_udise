import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_part_b_step2():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        # Click Step 2: Subject, CG & Competencies
        step2 = page.locator("div.step-item, button, div:has-text('Subject, CG & Competencies')").last
        if step2.is_visible():
            print("Clicking Step 2...")
            step2.click()
            time.sleep(2)
            page.screenshot(path='audit_evidence/middle_part_b_step2.png')

            # Inspect all dropdowns and checkboxes on Step 2
            dds = page.locator(".custom-dropdown-wrapper").all()
            print(f"Dropdowns on Step 2: {len(dds)}")
            for d in dds:
                print("  Dropdown:", d.inner_text().replace('\n', ' | '))

            # Check subjects available in dropdown
            # Click Subject dropdown
            subj_dd = page.locator("label:has-text('Subject')").first
            if subj_dd.is_visible():
                cont = subj_dd.locator("xpath=ancestor::div[contains(@class, 'custom-dropdown-wrapper') or contains(@class, 'custom-input-label')]").first
                header = cont.locator(".custom-dropdown-header").first
                if header.is_visible():
                    header.click()
                    time.sleep(1)
                    items = page.locator(".custom-dropdown-item").all_inner_texts()
                    print("Available Subjects in Step 2:", items)

        ctx.close()

if __name__ == '__main__':
    inspect_part_b_step2()
