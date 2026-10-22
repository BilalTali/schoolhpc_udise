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
    url = 'https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2'
    page.goto(url, wait_until='networkidle')
    print('Loaded URL:', page.url)

    # 1. Fill Part-A2 Hand & Favorites
    a2_inputs = [inp for inp in page.query_selector_all("input[type=text]:not([readonly]):not([disabled])") if inp.is_visible()]
    a2_textareas = [ta for ta in page.query_selector_all("textarea") if ta.is_visible()]
    print(f'A2: {len(a2_inputs)} inputs, {len(a2_textareas)} textareas')

    for f_idx in range(1, 6):
        val = str(raw.get(f"hand_finger_{f_idx}", f"strength {f_idx}"))
        if len(a2_inputs) >= f_idx:
            a2_inputs[f_idx - 1].fill(val)

    if len(a2_textareas) >= 1:
        a2_textareas[0].fill(str(raw.get("grow_up_goal", "Environmental Scientist")))
    if len(a2_inputs) >= 6:
        a2_inputs[5].fill(str(raw.get("admired_person", "Dr. A.P.J. Abdul Kalam")))
    if len(a2_inputs) >= 7:
        a2_inputs[6].fill(str(raw.get("my_calling_name", student.student_name)))
    if len(a2_inputs) >= 8:
        a2_inputs[7].fill(str(raw.get("my_age", "9")))

    if len(a2_textareas) >= 2:
        a2_textareas[1].fill(str(raw.get("fav_food", "Lentils and fruits")))
    if len(a2_textareas) >= 3:
        a2_textareas[2].fill(str(raw.get("fav_games", "Badminton and Kho-Kho")))
    if len(a2_textareas) >= 4:
        a2_textareas[3].fill(str(raw.get("fav_festival", "Diwali and Eid")))
    if len(a2_textareas) >= 5:
        a2_textareas[4].fill(str(raw.get("three_things_1", "Reading science books")))
    if len(a2_textareas) >= 6:
        a2_textareas[5].fill(str(raw.get("three_things_2", "Nurturing plants")))
    if len(a2_textareas) >= 7:
        a2_textareas[6].fill(str(raw.get("three_things_3", "Composing lyrical poems")))

    time.sleep(1)

    # Click Save as Draft
    sd_btn = page.query_selector("button:has-text('Save as Draft')")
    if sd_btn:
        sd_btn.click()
        print('Clicked Save as Draft on Part-A2')
        time.sleep(3)

    # Click Continue
    cont_btn = page.query_selector("button:has-text('Continue')")
    if cont_btn:
        cont_btn.click()
        print('Clicked Continue on Part-A2')
        time.sleep(4)

    page.screenshot(path='audit_evidence/after_part_a2_continue.png')
    
    # Check what page we are on now
    h = page.query_selector('h1, h2, h3, h4, .stepper-item.active, div:has-text("Part - A")')
    print('Header after A2 continue:', h.inner_text().strip().replace('\n', ' ') if h else 'None')
    ctx.close()
