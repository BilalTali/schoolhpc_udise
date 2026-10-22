import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    add_btn = page.locator("button:has-text('Add Activity')").first
    add_btn.click()
    time.sleep(1.5)

    pick_btn = page.locator("button:has-text('Pick from Activity Bank')").first
    pick_btn.click()
    time.sleep(1)

    cont_btn = page.locator(".modal button:has-text('Continue'), [role=dialog] button:has-text('Continue')").first
    cont_btn.click()
    time.sleep(2)

    # Switch to Global Activities
    page.evaluate('''() => {
        const tabs = Array.from(document.querySelectorAll('*')).filter(el => 
            el.textContent.trim() === 'Global Activities'
        );
        if (tabs.length > 0) tabs[tabs.length - 1].click();
    }''')
    time.sleep(2)

    page.screenshot(path='audit_evidence/modal_global_activities.png')
    
    # Print all buttons on page
    btns = page.locator('button').all()
    print('ALL BUTTONS ON PAGE:')
    for b in btns:
        if b.is_visible():
            print('  BTN:', b.inner_text().strip())

    ctx.close()
