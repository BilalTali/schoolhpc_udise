import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
from excel.importer import import_preparatory_workbook
from portal.uploader import parse_record_to_model
from pathlib import Path

excel_path = Path('data') / 'temp_upload_hpc_preparatory_students_filled (10).xlsx'
records = import_preparatory_workbook(excel_path)
student = parse_record_to_model(records[0])
raw = student.raw_data

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

    print('[1] Step 1: Activity Details')
    switch_step('Activity Details')
    inp1 = page.locator("input[placeholder*='Activity Name'], input[name*='name']:not([readonly])").first
    if inp1.is_visible() and not inp1.input_value():
        inp1.fill("TWCG 1 , C-1.2")

    print('[2] Step 2: Subject, CG & Competencies')
    switch_step('Subject, CG & Competencies')
    time.sleep(1)

    print('[3] Step 3: Activity & Assessment Qs')
    switch_step('Activity & Assessment Qs')
    for ta in page.locator('textarea').all():
        if ta.is_visible() and not ta.input_value():
            ta.fill("Guided inquiry, nature exploration, and creative presentation.")

    print('[4] Step 4: Assessment Rubric')
    switch_step('Assessment Rubric')
    page.evaluate('''() => {
        ['awrActive', 'senActive', 'creActive'].forEach(name => {
            const rad = document.querySelector(`input[type=radio][name='${name}'][value='proficient']`);
            if (rad && !rad.checked) rad.click();
        });
        document.querySelectorAll('textarea').forEach(ta => {
            if (!ta.value) ta.value = "Consistent conceptual clarity, empathy, and collaborative effort.";
        });
    }''')
    time.sleep(1)

    print('[5] Step 5: Observational Notes')
    switch_step('Observational Notes')
    for ta in page.locator('textarea').all():
        if ta.is_visible() and not ta.input_value():
            ta.fill("Exhibits strong engagement in group tasks and connects concepts across subjects.")
    time.sleep(1)

    print('[6] Step 6: Self Assessment')
    switch_step('Self Assessment')
    page.evaluate('''() => {
        document.querySelectorAll('li.assessment-smiley-yes, .assessment-smiley-yes').forEach(el => {
            el.click();
        });
    }''')
    time.sleep(1)

    print('[7] Clicking Finish Activity...')
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)

    # Click modal confirm if modal opened
    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('.modal button, [role=dialog] button, .activation-tab-lists button'));
        const b = btns.find(x => x.innerText.includes('Yes') || x.innerText.includes('Confirm'));
        if (b) b.click();
    }''')
    time.sleep(2)

    # Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print('Clicked Save as Draft')
        time.sleep(3)

    # Click Continue to Part-C
    cont = page.locator("button:has-text('Continue')").first
    if cont.is_visible():
        cont.click()
        print('Clicked Continue')
        time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_b_complete_success.png')
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Part - ")')
    print('Header after Part-B continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
