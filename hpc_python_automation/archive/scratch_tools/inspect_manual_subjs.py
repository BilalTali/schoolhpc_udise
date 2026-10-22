import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Sub-step 2
    page.evaluate("""() => {
        const ps = Array.from(document.querySelectorAll('p, div, span')).filter(p => p.innerText && p.innerText.trim() === 'Subject, CG & Competencies');
        if (ps.length > 0) ps[0].click();
    }""")
    time.sleep(1)

    # Click #subjectSelect
    page.locator("#subjectSelect").click()
    time.sleep(1)

    items = page.evaluate("""() => {
        const list = document.querySelectorAll('.custom-dropdown-list-item, li, div[role=option], div[class*=\"dropdown\"] div');
        return Array.from(list).map(x => x.innerText.trim()).filter(Boolean);
    }""")
    print("Found items in subjectSelect for manual activity:", [x for x in items if any(s in x for s in ['Language', 'Math', 'Science', 'Social', 'Art', 'Physical', 'Skill', 'Vocational', 'Select'])][:25])

    page.screenshot(path='audit_evidence/middle_manual_step2_subjects.png')
    ctx.close()
