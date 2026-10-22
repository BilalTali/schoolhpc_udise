import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Sub-step 5: Student's Self Reflection
    page.evaluate("""() => {
        const ps = Array.from(document.querySelectorAll('p, div, span')).filter(p => p.innerText && p.innerText.includes('Self Reflection'));
        if (ps.length > 0) ps[0].click();
    }""")
    time.sleep(2)

    page.screenshot(path='audit_evidence/middle_step5_unfilled.png')

    # What elements are in step 5? smileys? radios? inputs?
    smileys = page.locator("li.assessment-smiley-yes, .assessment-smiley-yes, img[src*='smiley']").all()
    print("Smileys found:", len(smileys))
    radios = page.locator("input[type=radio]").all()
    print("Radios found:", len(radios))
    tas = page.locator("textarea").all()
    print("Textareas found:", len(tas))

    ctx.close()
