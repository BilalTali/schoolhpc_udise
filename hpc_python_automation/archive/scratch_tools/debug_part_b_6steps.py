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

    def click_step(step_num):
        page.evaluate(f'''() => {{
            const tabs = Array.from(document.querySelectorAll('*')).filter(el => 
                el.innerText && el.innerText.trim().startsWith('{step_num}')
            );
            if (tabs.length > 0) tabs[0].click();
        }}''')
        time.sleep(1)

    # Step 1: Activity Details
    click_step(1)
    act_inp = page.locator("input[placeholder*='Activity Name'], input[name*='name']:not([readonly])").first
    if act_inp.is_visible() and not act_inp.input_value():
        act_inp.fill("TWCG 1 , C-1.2")

    # Step 2: Subject & Competencies
    click_step(2)
    # Check all subjects
    page.evaluate('''() => {
        document.querySelectorAll('input[type=checkbox]').forEach(c => {
            if (!c.checked) c.click();
        });
    }''')

    # Step 3: Activity & Assessment Qs
    click_step(3)
    tas3 = page.locator("textarea").all()
    for ta in tas3:
        if ta.is_visible() and not ta.input_value():
            ta.fill("Field observation and guided inquiry across nature and art.")

    # Step 4: Assessment Rubric
    click_step(4)
    page.evaluate('''() => {
        document.querySelectorAll('input[type=radio][value=\"proficient\"]').forEach(r => {
            if (!r.checked) r.click();
        });
        document.querySelectorAll('textarea').forEach(ta => {
            if (!ta.value) ta.value = "Consistent conceptual understanding and empathetic teamwork.";
        });
    }''')

    # Step 5: Observational Notes
    click_step(5)
    tas5 = page.locator("textarea").all()
    for ta in tas5:
        if ta.is_visible() and not ta.input_value():
            ta.fill("Exhibits strong engagement in group tasks and connects concepts across subjects.")

    # Step 6: Self Assessment (Smiley emojis)
    click_step(6)
    page.evaluate('''() => {
        document.querySelectorAll('li.assessment-smiley-yes, .assessment-smiley-yes').forEach(el => {
            el.click();
        });
    }''')
    time.sleep(1)

    # Click Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    if fa_btn.is_visible():
        fa_btn.click()
        print('Clicked Finish Activity')
        time.sleep(2)

    # Confirm dialog if any
    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('.modal button, [role=dialog] button'));
        const b = btns.find(x => x.innerText.includes('Yes') || x.innerText.includes('Confirm'));
        if (b) b.click();
    }''')
    time.sleep(2)

    # Save as Draft
    page.locator("button:has-text('Save as Draft')").first.click()
    print('Clicked Save as Draft')
    time.sleep(3)

    # Continue to Part-C
    page.locator("button:has-text('Continue')").first.click()
    print('Clicked Continue')
    time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_b_complete.png')
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Part - ")')
    print('Header after Part-B continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
