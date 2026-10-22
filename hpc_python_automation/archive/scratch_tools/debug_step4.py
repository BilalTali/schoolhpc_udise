import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    # Click Step 4
    page.locator("div.step-item, div:has-text('Assessment Rubric')").last.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/step4_rubric.png')
    
    # Check inputs in Step 4
    radios = page.locator("input[type=radio]").all()
    print('Step 4 radios:', len(radios))
    for r in radios:
        print('  RADIO:', r.get_attribute('name'), r.get_attribute('value'), r.is_checked())
    ctx.close()
