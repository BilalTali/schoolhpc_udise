import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Sub-step 2: Subject, CG & Competencies
    page.evaluate("""() => {
        const ps = Array.from(document.querySelectorAll('p, div, span')).filter(p => p.innerText && p.innerText.trim() === 'Subject, CG & Competencies');
        if (ps.length > 0) ps[0].click();
    }""")
    time.sleep(1)

    # Open Subject dropdown
    page.locator("#subjectSelect").click()
    time.sleep(1)

    # Check all subjects in dropdown
    print("Checking all subjects in dropdown...")
    res = page.evaluate("""() => {
        const items = document.querySelectorAll('.custom-dropdown-list-item, div[class*=\"dropdown\"] label');
        let clicked = 0;
        items.forEach(it => {
            const cb = it.querySelector('input[type=checkbox]');
            if (cb && !cb.checked) {
                cb.click();
                clicked++;
            }
        });
        return clicked;
    }""")
    print(f"Clicked {res} subject checkboxes!")
    time.sleep(2)

    # Close dropdown by clicking outside or on header
    page.locator("#subjectSelect").click()
    time.sleep(1)

    # Now let's see what competencies appear in the main container
    # For each section, select at least one competency checkbox
    print("Checking competencies for all selected domains...")
    c_res = page.evaluate("""() => {
        // Find all unchecked competency checkboxes in the step content
        const cbs = document.querySelectorAll("div.step-content input[type=checkbox], div[class*='competenc'] input[type=checkbox], input[type=checkbox]");
        let checkedCount = 0;
        cbs.forEach(cb => {
            // Check first competency under each group
            if (!cb.checked) {
                cb.click();
                checkedCount++;
            }
        });
        return checkedCount;
    }""")
    print(f"Checked {c_res} competency checkboxes!")
    time.sleep(2)

    page.screenshot(path='audit_evidence/middle_all_domains_checked.png')

    # Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print("Clicked Save as Draft on Part-B")
        time.sleep(3)

    ctx.close()
