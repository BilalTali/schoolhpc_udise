import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/hpc-credit', wait_until='networkidle')

    print('[1] Filling 12 marks inputs...')
    inputs = [inp for inp in page.locator("input[type=text], input[type=number]").all() if inp.is_visible()]
    print(f'Found {len(inputs)} visible inputs on HPC Credit')
    
    # 6 subjects x 2 inputs = 12 inputs (max marks: 33, obtained marks: 28)
    marks_data = [
        ("33", "28"),  # Lang 1
        ("33", "27"),  # Lang 2
        ("33", "30"),  # Math
        ("33", "28"),  # World Around Us
        ("33", "29"),  # Art
        ("33", "30"),  # Physical Ed
    ]
    flat = []
    for mx, got in marks_data:
        flat.extend([mx, got])

    for i, inp in enumerate(inputs):
        val = flat[i] if i < len(flat) else "28"
        inp.fill(val)
        print(f'  Input[{i}] filled with {val}')

    time.sleep(1)

    print('[2] Checking Declaration checkbox...')
    page.evaluate('''() => {
        const cbs = document.querySelectorAll('input[type=checkbox]');
        cbs.forEach(cb => {
            if (!cb.checked) cb.click();
        });
    }''')
    time.sleep(1)

    print('[3] Clicking Save as Draft...')
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print('Clicked Save as Draft')
        time.sleep(3)

    print('[4] Clicking Mark as Complete...')
    mc = page.locator("button:has-text('Mark as Complete')").first
    if mc.is_visible():
        mc.click()
        print('Clicked Mark as Complete!')
        time.sleep(2)

    # Confirm dialog if any
    print('[5] Confirming completion dialog...')
    modal_btn = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), .modal button:has-text('Confirm'), .modal button:has-text('Complete')").first
    if modal_btn.is_visible():
        modal_btn.click()
        print('Clicked confirmation dialog button!')
        time.sleep(3)

    page.screenshot(path='audit_evidence/after_mark_as_complete.png')

    # Step 6: Navigate to live roster and check status of ARKAN AHMAD
    print('\n[6] Checking Live Roster status...')
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage', wait_until='networkidle')
    time.sleep(2)
    page.screenshot(path='audit_evidence/roster_final_verification.png')

    rows = page.locator("table tbody tr").all()
    for r in rows:
        t = r.inner_text().strip().replace('\n', ' | ')
        if 'ARKAN' in t.upper():
            print(f'\n>>> FINAL LIVE STATUS: {t} <<<\n')

    ctx.close()
