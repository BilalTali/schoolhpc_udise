import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Click Sub-step 2
    page.evaluate("""() => {
        const ps = Array.from(document.querySelectorAll('p, div, span')).filter(p => p.innerText && p.innerText.trim() === 'Subject, CG & Competencies');
        if (ps.length > 0) ps[0].click();
    }""")
    time.sleep(1)

    # Click the Subject dropdown
    subj_dd = page.locator("div:has-text('Science'), select, div[class*='select']").filter(has_text="Science").last
    print("Clicking Subject dropdown...")
    subj_dd.click()
    time.sleep(1)
    page.screenshot(path='audit_evidence/middle_step2_subj_dropdown.png')

    # Print any dropdown options or menu that appeared
    options = page.locator("div[class*='option'], div[class*='menu'], ul[role='listbox'] li, div[role='option']").all()
    print("Dropdown options count:", len(options))
    for o in options:
        print("  Option:", o.inner_text().strip())

    ctx.close()
