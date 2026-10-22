import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const act = btns.find(b => b.innerText.includes('TWCG 1') || b.innerText.includes('1'));
        if (act) act.click();
    }''')
    time.sleep(1)

    page.locator("button:has-text('Finish Activity')").first.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/finish_btn_dialog_test.png')
    
    # Print any elements with role=dialog or class modal
    dialogs = page.evaluate('''() => {
        const ds = Array.from(document.querySelectorAll('[role=dialog], .modal'));
        return ds.map(d => ({
            tag: d.tagName,
            class: d.className,
            text: d.innerText.trim(),
            visible: d.offsetParent !== null
        }));
    }''')
    print('DIALOGS:', dialogs)
    ctx.close()
