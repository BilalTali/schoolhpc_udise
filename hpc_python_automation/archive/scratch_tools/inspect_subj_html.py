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

    html = page.evaluate("""() => {
        const label = Array.from(document.querySelectorAll('label')).find(l => l.innerText.includes('Subject'));
        if (label && label.parentElement) {
            return label.parentElement.outerHTML;
        }
        return 'Not found';
    }""")
    print("Subject dropdown HTML:")
    print(html)

    ctx.close()
