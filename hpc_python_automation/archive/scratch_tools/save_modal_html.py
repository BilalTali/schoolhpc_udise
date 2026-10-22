import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)
    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)
    page.locator("text='Pick from Activity Bank'").first.click()
    time.sleep(0.5)
    page.locator(".modal button:has-text('Continue')").first.click()
    time.sleep(1)
    
    html = page.locator(".modal").first.inner_html()
    with open('audit_evidence/modal_html.txt', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Saved modal HTML, length:', len(html))
    ctx.close()
