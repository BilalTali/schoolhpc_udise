import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank/add', wait_until='networkidle')
    time.sleep(2)

    # Select HPC Stage: Middle
    stage_dd = page.locator("div:has-text('Foundational'), div[id*='stage'], select").first
    print("Clicking stage selector...")
    page.evaluate("""() => {
        const rad = Array.from(document.querySelectorAll('input[type=radio], div[role=button], label')).find(x => x.innerText && x.innerText.includes('Middle'));
        if (rad) rad.click();
        else {
            const dd = document.querySelector('div[class*=\"select\"]');
            if (dd) dd.click();
        }
    }""")
    time.sleep(1)
    page.screenshot(path='audit_evidence/activity_add_middle.png')

    labels = [l.inner_text().strip() for l in page.locator("label").all() if l.is_visible()]
    print("Labels after picking Middle:", labels)

    ctx.close()
