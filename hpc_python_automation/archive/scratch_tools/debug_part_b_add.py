import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    page.locator("button:has-text('Add Activity')").first.click()
    time.sleep(1)
    page.locator("button:has-text('Pick from Activity Bank')").first.click()
    time.sleep(1)
    page.locator(".modal button:has-text('Continue')").first.click()
    time.sleep(2)

    # Click Global Activities tab
    page.evaluate('''() => {
        const tabs = Array.from(document.querySelectorAll('*')).filter(el => el.textContent.trim() === 'Global Activities');
        if (tabs.length > 0) tabs[tabs.length - 1].click();
    }''')
    time.sleep(2)

    # Click checkbox for C-1.2
    chk_res = page.evaluate('''() => {
        const chks = Array.from(document.querySelectorAll('.modal input[type=checkbox], [role=dialog] input[type=checkbox]'));
        if (chks.length > 0) {
            // Find one with C-1.2 or pick first
            const c12 = chks.find(c => {
                const p = c.closest('label') || c.parentElement;
                return p && p.innerText && (p.innerText.includes('C-1.2') || p.innerText.includes('C 1.2'));
            });
            const target = c12 || chks[0];
            target.click();
            const parent = target.closest('label') || target.parentElement;
            return parent ? parent.innerText.trim() : 'clicked';
        }
        return 'no checkboxes';
    }''')
    print('Check result:', chk_res)
    time.sleep(1)

    use_btn = page.locator("button:has-text('Use Activity')").first
    print('Use Activity disabled:', use_btn.is_disabled())
    use_btn.click()
    time.sleep(3)

    page.screenshot(path='audit_evidence/after_use_activity.png')
    print('Done screenshot saved!')
    ctx.close()
