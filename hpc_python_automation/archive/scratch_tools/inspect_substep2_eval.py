import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Click via evaluate
    print("Clicking Sub-step 2 via evaluate...")
    page.evaluate("""() => {
        const ps = Array.from(document.querySelectorAll('p, div, span')).filter(p => p.innerText && p.innerText.trim() === 'Subject, CG & Competencies');
        if (ps.length > 0) ps[0].click();
    }""")
    time.sleep(2)
    page.screenshot(path='audit_evidence/middle_step2_view.png')

    # Also inspect what subjects/domains dropdown or checkboxes exist
    labels = page.locator("label, select, div[class*='select']").all()
    print("Labels/selects in Step 2:", len(labels))
    for l in labels[:15]:
        print("  Label:", l.inner_text().strip().replace(chr(10), ' | '))

    ctx.close()
