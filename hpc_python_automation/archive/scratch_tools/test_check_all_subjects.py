import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    page.click("button:has-text('Add Activity')")
    page.click("text=Create Manually")
    page.click("button:has-text('Continue')")
    page.click("text=Subject, CG & Competencies")
    time.sleep(1)

    # Open the Subject(s)* dropdown
    page.click(".scroller-cg-domain #partBDomainSelect")
    time.sleep(1)

    # Check all subject checkboxes
    subjects_to_check = [
        "Language Education (R1)",
        "Language Education (R2)",
        "Mathematics",
        "The World Around Us",
        "Art Education (AE)",
        "Physical Education and Well-being",
        "Other Learning Activities"
    ]
    
    for s in subjects_to_check:
        opt = page.query_selector(f".scroller-cg-domain li:has-text('{s}') input, .scroller-cg-domain li:has-text('{s}')")
        if opt:
            opt.click()
            time.sleep(0.3)
            print(f"Checked: {s}")

    # Close dropdown by clicking header or outside
    page.click("h2:has-text('Subject, CG & Competencies'), .cg-field-label")
    time.sleep(2)
    page.screenshot(path='all_7_subjects_selected.png')

    # Count how many competencies appeared across all 7 subjects!
    comps = page.evaluate("""() => {
        const cbs = document.querySelectorAll("input[type=checkbox][name='cpt']");
        const headings = Array.from(document.querySelectorAll("h3, h4, h5, [class*='subject']")).map(h => h.innerText.trim());
        return {
            totalCheckboxes: cbs.length,
            headings: headings.slice(0, 15)
        };
    }""")
    print("TOTAL COMPETENCIES LOADED:", comps["totalCheckboxes"])
    print("SUBJECT HEADINGS:", comps["headings"])

    ctx.close()
