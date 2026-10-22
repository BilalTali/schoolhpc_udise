import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142406/part-B', wait_until='domcontentloaded')
    time.sleep(3)
    print('Current URL:', page.url)

    # Click step 6
    for btn in page.query_selector_all('button, div, li'):
        t = (btn.text_content() or '').strip()
        if 'Self Assessment' in t and len(t) < 30:
            try:
                btn.click()
                print('Clicked tab:', t)
                time.sleep(2)
                break
            except: pass

    # Click emojis
    clicked = page.evaluate('''() => {
        let count = 0;
        document.querySelectorAll('li.assessment-smiley-yes').forEach(el => {
            el.click();
            count++;
        });
        return count;
    }''')
    print('Clicked emojis count:', clicked)
    time.sleep(2)

    # Click Finish Activity
    fin = page.query_selector("button:has-text('Finish Activity')")
    if fin and fin.is_visible():
        fin.click()
        print('Clicked Finish Activity!')
        time.sleep(2)

    # Check for modals
    modals = page.query_selector_all(".modal, [role=dialog]")
    for m in modals:
        if m.is_visible():
            print('Modal text:', (m.inner_text() or '')[:100])
            yes_btn = m.query_selector("button:has-text('Yes'), button:has-text('Confirm'), button:has-text('OK')")
            if yes_btn:
                yes_btn.click()
                print('Clicked modal confirmation!')
                time.sleep(2)

    page.screenshot(path='audit_evidence/test_after_finish_activity.png', full_page=True)
    print('Screenshot saved: test_after_finish_activity.png')

    # Now click Continue
    cont = page.query_selector("button:has-text('Continue')")
    if cont and cont.is_visible():
        cont.click()
        time.sleep(3)
        print('After Continue URL:', page.url)
        page.screenshot(path='audit_evidence/test_after_continue.png', full_page=True)

    ctx.close()
