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
    print('Finish btn visible:', fa_btn.is_visible())
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)
        page.screenshot(path='audit_evidence/after_finish_btn_click.png')
        for b in page.locator('button').all():
            if b.is_visible():
                print('  VISIBLE BTN:', b.inner_text().strip())
    ctx.close()
