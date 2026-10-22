import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print('Finish Activity visible:', fa_btn.is_visible())
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)

    # If confirm modal appears
    modal_btn = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), button:has-text('Confirm')").first
    if modal_btn.is_visible():
        modal_btn.click()
        print('Clicked modal confirm')
        time.sleep(2)

    # Save as Draft & Continue
    cont_btn = page.locator("button:has-text('Continue')").first
    cont_btn.click()
    time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_b_continue.png')
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Part - ")')
    print('Header after Part-B continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
