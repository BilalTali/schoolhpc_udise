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
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A1', wait_until='networkidle')

    def pick_dropdown(label_text, choice):
        lbl = page.locator('label', has_text=label_text).first
        if lbl.is_visible():
            wrap = lbl.locator('xpath=ancestor::div[contains(@class, "custom-input-label")]').first
            header = wrap.locator('.custom-dropdown-header').first
            cur = header.inner_text().strip()
            if choice.lower() not in cur.lower():
                header.click()
                time.sleep(0.5)
                opt = page.locator(f'.custom-dropdown-item:has-text("{choice}")').first
                if opt.is_visible():
                    opt.click()
                    time.sleep(0.3)

    pick_dropdown("Medium of Instruction", "English")
    pick_dropdown("Rural/Urban", "Rural")
    pick_dropdown("Mother / Father / Guardian", "Mother")

    # Mother Tongue
    mt_inp = page.locator("label", has_text="Mother Tongue").locator("xpath=ancestor::div[contains(@class, 'custom-input-label')]//input").first
    if mt_inp.is_visible():
        mt_inp.fill("Kashmiri")

    # Guardian Name
    g_inp = page.locator("input[placeholder*='Guardian']").first
    if g_inp.is_visible():
        g_inp.fill("iqbal")

    # 12 months attendance
    months = ["apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "jan", "feb", "mar"]
    table = page.locator("table").first
    if table.is_visible():
        rows = table.locator("tr").all()
        if len(rows) >= 3:
            w_inputs = rows[1].locator("input:not([readonly])").all()
            for idx, m in enumerate(months):
                if idx < len(w_inputs):
                    w_inputs[idx].fill(str(raw.get(f"{m}_working_days", "22")))

            p_inputs = rows[2].locator("input:not([readonly])").all()
            for idx, m in enumerate(months):
                if idx < len(p_inputs):
                    p_inputs[idx].fill(str(raw.get(f"{m}_present_days", "22")))

    # Low attendance reason
    reason_box = page.locator("textarea").first
    if reason_box.is_visible():
        reason_box.fill("Short seasonal viral indisposition")

    # Absent count
    abs_inp = page.locator("input[placeholder*='absent']:not([readonly])").first
    if abs_inp.is_visible():
        abs_inp.fill("0")

    # Interests
    page.evaluate('''() => {
        document.querySelectorAll('input[type=checkbox]').forEach(c => {
            if (!c.checked) c.click();
        });
    }''')

    time.sleep(1)
    
    # Save as Draft first
    draft_btn = page.query_selector("button:has-text('Save as Draft')")
    if draft_btn and draft_btn.is_visible():
        draft_btn.click()
        print("Clicked Save as Draft")
        time.sleep(3)

    # Click Continue
    cont_btn = page.query_selector("button:has-text('Continue')")
    if cont_btn and cont_btn.is_visible():
        cont_btn.click()
        print("Clicked Continue")
        time.sleep(4)

    print("URL after Continue:", page.url)

    # Check for any validation error
    for el in page.query_selector_all('.error-msg, .alert, p, span'):
        txt = (el.inner_text() or '').strip()
        if any(w in txt.lower() for w in ('required', 'field is required', 'fill all', 'mandatory')):
            if el.is_visible() and len(txt) < 80:
                print('VALIDATION MSG:', txt)

    page.screenshot(path='audit_evidence/test_full_part_a1.png')
    ctx.close()
