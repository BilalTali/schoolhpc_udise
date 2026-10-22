import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    def switch_step(name):
        page.evaluate(f'''() => {{
            const ps = Array.from(document.querySelectorAll('p')).filter(p => p.innerText.trim() === '{name}');
            if (ps.length > 0) ps[0].click();
        }}''')
        time.sleep(1)

    # 1. Step 4 Assessment Rubric
    print('Filling Step 4...')
    switch_step('Assessment Rubric')
    page.evaluate('''() => {
        ['awrActive', 'senActive', 'creActive'].forEach(name => {
            const rad = document.querySelector(`input[type=radio][name='${name}'][value='proficient']`);
            if (rad && !rad.checked) rad.click();
        });
        document.querySelectorAll('textarea').forEach(ta => {
            if (!ta.value) ta.value = "Consistent conceptual understanding, empathy, and collaborative effort.";
        });
    }''')
    time.sleep(1)

    # 2. Step 5 Observational Notes
    print('Filling Step 5...')
    switch_step('Observational Notes')
    for ta in page.locator('textarea').all():
        if ta.is_visible() and not ta.input_value():
            ta.fill("Exhibits strong engagement in group tasks and connects concepts across subjects.")
    time.sleep(1)

    # 3. Step 6 Self Assessment
    print('Filling Step 6...')
    switch_step('Self Assessment')
    page.evaluate('''() => {
        document.querySelectorAll('li.assessment-smiley-yes, .assessment-smiley-yes').forEach(el => el.click());
    }''')
    time.sleep(1)

    # 4. Click Finish Activity
    print('Clicking Finish Activity...')
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    fa_btn.click()
    time.sleep(2)

    # 5. In modal dialog, click 'Finish'
    print('Confirming Finish modal...')
    modal_finish = page.locator(".modal button:has-text('Finish'), [role=dialog] button:has-text('Finish')").first
    if modal_finish.is_visible():
        modal_finish.click()
        print('Clicked modal Finish button!')
        time.sleep(2)

    # 6. Click Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print('Clicked Save as Draft')
        time.sleep(3)

    # 7. Click Continue to Part-C
    cont = page.locator("button:has-text('Continue')").first
    if cont.is_visible():
        cont.click()
        print('Clicked Continue to Part-C')
        time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_b_finish_success.png')
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Part - ")')
    print('Header after Part-B continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
