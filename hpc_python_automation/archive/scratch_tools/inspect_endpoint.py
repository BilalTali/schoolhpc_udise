import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('request', lambda r: print("REQ:", r.method, r.url, list(r.headers.keys())) if 'hpc' in r.url and r.method in ('POST', 'PUT', 'PATCH') else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Make form dirty
    page.locator('li').filter(has_text="Teacher's Feedback").first.click()
    time.sleep(1)
    ta = page.locator('textarea').last
    ta.fill("Student shows great enthusiasm and participation.")
    time.sleep(1)

    # Click Save as Draft to see exact HTTP request
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        time.sleep(3)

    ctx.close()
