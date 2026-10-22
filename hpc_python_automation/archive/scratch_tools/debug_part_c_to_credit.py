import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-C', wait_until='networkidle')

    print('[1] Checking all 21 PSLS checkboxes...')
    page.evaluate('''() => {
        document.querySelectorAll('input[type=checkbox][value="2"]').forEach(cb => {
            if (!cb.checked) cb.click();
        });
    }''')
    time.sleep(1)

    print('[2] Filling all textareas via Playwright fill()...')
    tas = page.locator('textarea').all()
    print('Found textareas:', len(tas))
    for ta in tas:
        if ta.is_visible():
            ta.fill("Demonstrates commendable conceptual clarity, consistent teamwork, and enthusiastic inquiry across all learning areas.")
    time.sleep(1)

    # Click Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print('Clicked Save as Draft on Part-C')
        time.sleep(3)

    # Click Continue to HPC Credit
    cont = page.locator("button:has-text('Continue')").first
    if cont.is_visible():
        cont.click()
        print('Clicked Continue on Part-C')
        time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_c_to_credit_success.png')
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Credit")')
    print('Header after Part-C continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
