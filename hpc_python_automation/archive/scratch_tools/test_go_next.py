from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    time.sleep(2)
    print('Initial URL:', page.url)
    
    # Click Next
    next_btn = page.query_selector('button.custom-btn:has-text("Next"), button:has-text("Next")')
    if next_btn:
        print('Found Next button! Clicking it...')
        next_btn.click()
        time.sleep(3)
        print('New URL after Next:', page.url)
        page.screenshot(path='audit_evidence/test_after_next.png')
    else:
        print('Next button not found!')
    ctx.close()
