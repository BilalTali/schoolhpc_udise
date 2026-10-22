import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_step2():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        # The existing activity is on the left sidebar: 'SCCG-1, C1.1'
        act_btn = page.locator(".activity-list-item, div:has-text('SCCG-1, C1.1'), button:has-text('SCCG-1')").first
        if act_btn.is_visible():
            act_btn.click()
            time.sleep(1)

        # Click Sub-step 2: Subject, CG & Competencies
        s2 = page.locator("div.step-item:has-text('Subject'), div:has-text('2'):has-text('Subject')").last
        print("Clicking Sub-step 2...")
        s2.click()
        time.sleep(2)

        page.screenshot(path='audit_evidence/middle_step2_exact.png')

        # Check what elements are in the right pane of Step 2
        right_pane = page.locator(".right-content, .step-content, div[class*='content']").all()
        print(f"Content containers: {len(right_pane)}")
        for i, c in enumerate(right_pane[:5]):
            print(f"  [{i}]:", c.inner_text().replace('\n', ' | ')[:150])

        ctx.close()

if __name__ == '__main__':
    test_step2()
