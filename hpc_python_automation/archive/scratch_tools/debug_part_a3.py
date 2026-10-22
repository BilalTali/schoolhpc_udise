import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A3', wait_until='networkidle')

    # Click all 'Yes' options
    clicked = page.evaluate('''() => {
        let count = 0;
        document.querySelectorAll('li').forEach(li => {
            const p = li.querySelector('p');
            if (p && p.innerText.trim() === 'Yes') {
                li.click();
                count++;
            }
        });
        return count;
    }''')
    print('Clicked Yes count:', clicked)

    # Fill peer names
    inps = page.query_selector_all('input[type=text]:not([readonly])')
    print('Text inputs on Part-A3:', len(inps))
    for i, inp in enumerate(inps):
        if inp.is_visible():
            inp.fill("Aarav" if i % 2 == 0 else "Zaid")

    # Check resources checkboxes
    page.evaluate('''() => {
        document.querySelectorAll('input[type=checkbox]').forEach(c => {
            if (!c.checked) c.click();
        });
    }''')

    time.sleep(1)

    # Click Save as Draft
    sd = page.query_selector("button:has-text('Save as Draft')")
    if sd:
        sd.click()
        print('Clicked Save as Draft on Part-A3')
        time.sleep(3)

    # Click Continue
    cont = page.query_selector("button:has-text('Continue')")
    if cont:
        cont.click()
        print('Clicked Continue on Part-A3')
        time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_a3_continue.png')
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Part - B")')
    print('Header after A3 continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
