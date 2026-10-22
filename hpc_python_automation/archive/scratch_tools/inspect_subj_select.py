import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    page.evaluate("""() => {
        const ps = Array.from(document.querySelectorAll('p, div, span')).filter(p => p.innerText && p.innerText.trim() === 'Subject, CG & Competencies');
        if (ps.length > 0) ps[0].click();
    }""")
    time.sleep(1)

    print("Clicking #subjectSelect...")
    page.locator("#subjectSelect").click()
    time.sleep(1)

    items = page.evaluate("""() => {
        const dd = document.querySelector('#subjectSelect');
        const list = document.querySelectorAll('.custom-dropdown-list-item, li, div[role=option]');
        return Array.from(list).map(x => x.innerText.trim()).filter(Boolean);
    }""")
    print("Found items in subjectSelect:", items)

    ctx.close()
