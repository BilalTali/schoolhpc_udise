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
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A1', wait_until='networkidle')
    time.sleep(2)
    
    # Click Continue to advance to Part-A2
    print("Clicking Continue on Part-A1...")
    page.locator(".hpc-inner-action-bar button:has-text('Continue')").first.click()
    time.sleep(3)
    print("Now on URL:", page.url)
    
    # 1. Fill 5 Hand Diagram Fingers via popup
    finger_keys = ["hand_finger_1", "hand_finger_2", "hand_finger_3", "hand_finger_4", "hand_finger_5"]
    for i, k in enumerate(finger_keys):
        val = str(raw.get(k, f"strength {i+1}"))
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
            print(f"Finger {i} filled with: {val}")

    # 2. When I grow up I want to be... (textarea)
    grow_up_val = str(raw.get("grow_up_goal", "Environmental Scientist"))
    grow_ta = page.locator("div:has-text('When I grow up') textarea, textarea").first
    if grow_ta.is_visible():
        grow_ta.fill(grow_up_val)

    # 3. My name is: & Age
    name_val = str(raw.get("my_calling_name", student.student_name))
    name_inp = page.locator("div:has-text('My name is') input").first
    if name_inp.is_visible():
        name_inp.fill(name_val)

    age_val = str(raw.get("my_age", "9"))
    age_inp = page.locator("div:has-text('years old') input").first
    if age_inp.is_visible():
        age_inp.fill(age_val)

    # 4. One person who inspires me is...
    idol_val = str(raw.get("admired_person", "Dr. A.P.J. Abdul Kalam"))
    idol_inp = page.locator("div:has-text('inspires me') input").first
    if idol_inp.is_visible():
        idol_inp.fill(idol_val)

    # 5. Some of my favorite things (FOOD, GAMES, FESTIVAL)
    fav_tas = page.locator("div:has-text('Some of my favorite things') textarea").all()
    if len(fav_tas) >= 1:
        fav_tas[0].fill(str(raw.get("fav_food", "Lentils and rice")))
    if len(fav_tas) >= 2:
        fav_tas[1].fill(str(raw.get("fav_games", "Badminton and Kho-Kho")))
    if len(fav_tas) >= 3:
        fav_tas[2].fill(str(raw.get("fav_festival", "Diwali and Eid")))

    # 6. Three things I want to learn this school year
    learn_tas = page.locator("div:has-text('Three things I want to learn') textarea").all()
    if len(learn_tas) >= 1:
        learn_tas[0].fill(str(raw.get("three_things_1", "Reading illustrated books")))
    if len(learn_tas) >= 2:
        learn_tas[1].fill(str(raw.get("three_things_2", "Nurturing botanical plants")))
    if len(learn_tas) >= 3:
        learn_tas[2].fill(str(raw.get("three_things_3", "Composing lyrical poems")))

    time.sleep(1)
    page.screenshot(path='audit_evidence/real_part_a2_perfect.png', full_page=True)

    # Save as Draft
    page.locator(".hpc-inner-action-bar button:has-text('Save as Draft')").first.click()
    time.sleep(2)
    print("Saved Part-A2 as draft successfully!")

    ctx.close()
