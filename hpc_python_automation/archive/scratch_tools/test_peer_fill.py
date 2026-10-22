import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text='Peer Feedback').first.click()
    time.sleep(2)

    inps = page.locator("input[placeholder*='Write here']:visible").all()
    print("Found visible inputs in Peer Feedback:", len(inps))
    if len(inps) >= 2:
        inps[0].fill("ARBAZ IQBAL")
        inps[1].fill("MOHAMMAD SAHIL")
        print("Successfully filled names!")

    page.screenshot(path='audit_evidence/peer_names_filled.png')
    ctx.close()
