import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(3)
    
    # Click each of the 5 activities on the sidebar
    # Find all sidebar activity items
    sidebar_items = page.locator("div.step-item, div:has(> span:has-text('1')), div:has(> span:has-text('2')), div:has(> span:has-text('3')), div:has(> span:has-text('4')), div:has(> span:has-text('5'))").all()
    
    # Or let's use exact selector from DOM
    # Let's inspect the sidebar HTML
    sb_html = page.locator("div:has-text('ACTIVITIES - 5')").first.locator("..").inner_html()
    with open('audit_evidence/abid_sidebar_html.txt', 'w', encoding='utf-8') as f:
        f.write(sb_html)
    print("Saved sidebar html")

    ctx.close()
