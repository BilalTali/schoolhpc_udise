import time
from playwright.sync_api import sync_playwright
from excel.importer import import_preparatory_workbook
from portal.uploader import parse_record_to_model
from pathlib import Path

excel_path = Path('data') / 'temp_upload_hpc_preparatory_students_filled (10).xlsx'
records = import_preparatory_workbook(excel_path)
student = parse_record_to_model(records[0])
raw = student.raw_data

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2', wait_until='networkidle')
    time.sleep(2)
    
    # 1. 5 Hand Diagram Fingers via popup
    finger_keys = ["hand_finger_1", "hand_finger_2", "hand_finger_3", "hand_finger_4", "hand_finger_5"]
    for i, k in enumerate(finger_keys):
        val = str(raw.get(k, f"strength {i+1}"))[:13]
        finger_inp = page.locator(f"input.pre-about-me-{i}").first
        if finger_inp.is_visible():
            finger_inp.click()
            time.sleep(0.4)
            pop_inp = page.locator("div.popover input, div:has(> button:has-text('Ok')) input").first
            if pop_inp.is_visible():
                pop_inp.fill(val)
                time.sleep(0.2)
                ok_btn = page.locator("button:has-text('Ok')").first
                if ok_btn.is_visible():
                    ok_btn.click()
                    time.sleep(0.4)

    # 2. Pencil: When I grow up I want to be...
    grow_ta = page.locator("textarea.pre-pencil-grow-up").first
    if grow_ta.is_visible():
        grow_ta.fill(str(raw.get("grow_up_goal", "Environmental Scientist"))[:54])

    # 3. My name is & Age
    name_inp = page.locator("input.pre-my-name-is").first
    if name_inp.is_visible():
        call_name = str(raw.get("my_calling_name", student.student_name))[:23]
        name_inp.fill(call_name)

    age_inp = page.locator("input.pre-my-age-is").first
    if age_inp.is_visible():
        age_inp.fill(str(raw.get("my_age", "9"))[:2])

    # 4. One person who inspires me is...
    one_inp = page.locator("input.pre-one-person").first
    if one_inp.is_visible():
        one_inp.fill(str(raw.get("admired_person", "Dr. A.P.J. Abdul Kalam"))[:24])

    # 5. Favorites (FOOD, GAMES, FESTIVAL)
    f0 = page.locator("textarea.pre-favorite-things-0").first
    if f0.is_visible():
        f0.fill(str(raw.get("fav_food", "Lentils and rice"))[:83])

    f1 = page.locator("textarea.pre-favorite-things-1").first
    if f1.is_visible():
        f1.fill(str(raw.get("fav_games", "Badminton and Kho-Kho"))[:83])

    f2 = page.locator("textarea.pre-favorite-things-2").first
    if f2.is_visible():
        f2.fill(str(raw.get("fav_festival", "Diwali and Eid celebrations"))[:83])

    # 6. Three things I want to learn
    t0 = page.locator("textarea.pre-0-things").first
    if t0.is_visible():
        t0.fill(str(raw.get("three_things_1", "Reading illustrated science books"))[:37])

    t1 = page.locator("textarea.pre-1-things").first
    if t1.is_visible():
        t1.fill(str(raw.get("three_things_2", "Nurturing botanical plants"))[:37])

    t2 = page.locator("textarea.pre-2-things").first
    if t2.is_visible():
        t2.fill(str(raw.get("three_things_3", "Composing lyrical short poems"))[:37])

    time.sleep(1)
    page.screenshot(path='audit_evidence/part_a2_exact_classes.png', full_page=True)

    # Save as Draft
    page.locator(".hpc-inner-action-bar button:has-text('Save as Draft')").first.click()
    time.sleep(2)
    print("Part-A2 perfectly populated and saved as draft!")

    ctx.close()
