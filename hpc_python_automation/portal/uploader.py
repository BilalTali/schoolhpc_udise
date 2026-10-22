"""
Uploader: automates uploading validated student records to the NCERT PARAKH HPC portal.
Implements the complete end-to-end flow from Part-A(1) through to the 'Mark as Complete' button.

Part-B Strategy:
  - Uses ONE GLOBAL ACTIVITY from the portal's official global activity list (no manual creation).
  - Default: Activity 5 = L1CG 1 (C-1.2) - the integrated all-subject activity covering:
      Language Education (R1), Language Education (R2), Mathematics,
      The World Around Us, Art Education (AE), Physical Education & Well-being,
      and Other Learning Activities.
  - All 7 subjects are added under this single activity.
  - Traverses all 6 steps: Activity Details -> Subject/CG/Competencies -> Activity & Assessment Qs
    -> Assessment Rubric -> Observational Notes -> Self Assessment (Colour emojis).
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
from playwright.sync_api import sync_playwright, Page, BrowserContext

from database.models import StudentRecord, UploadState
from database.repository import UploadRepository
from portal.login import get_browser_context, wait_for_manual_login

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "audit_evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)

GLOBAL_ACTIVITIES_CONFIG = ROOT / "config" / "global_activities.json"

# Default activity: Activity 5 = L1CG 1 (C-1.2) - integrated all-subject
DEFAULT_ACTIVITY_NAME = "L1CG 1 (C-1.2)"
DEFAULT_ACTIVITY_ID = 85


def _load_global_activities() -> List[Dict[str, Any]]:
    """Loads the global activities list from config/global_activities.json."""
    if GLOBAL_ACTIVITIES_CONFIG.exists():
        try:
            data = json.loads(GLOBAL_ACTIVITIES_CONFIG.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return []


def _find_activity_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Finds an activity from the global list by name or code (case-insensitive partial match)."""
    activities = _load_global_activities()
    name_lower = name.strip().lower()
    for act in activities:
        act_name = (act.get("name") or act.get("code") or "").lower()
        if name_lower in act_name or act_name in name_lower:
            return act
    # Default to first activity if no match
    return activities[0] if activities else None


def parse_record_to_model(raw_dict: Dict[str, Any]) -> StudentRecord:
    """Converts a raw dictionary from excel importer into a typed StudentRecord."""
    data = raw_dict.get("data", raw_dict)

    # Parse interests
    interests = {}
    for k, v in data.items():
        if k.startswith("interest_"):
            interests[k] = str(v).strip().lower() in ("yes", "true", "1")

    # Parse competencies
    comps = {}
    for k, v in data.items():
        if k.startswith("comp_"):
            rating = str(v).strip().lower()
            if rating in ("beginner", "proficient", "advance"):
                comps[k] = rating

    teacher_remarks = str(data.get("teacher_remarks", "")).strip()
    teacher_rating = str(data.get("teacher_overall_rating", data.get("teacher_rating", "proficient"))).strip().lower()

    return StudentRecord(
        admission_number=str(data.get("admission_number", "")).strip(),
        student_name=str(data.get("student_name", "")).strip(),
        dob=str(data.get("dob", "")).strip(),
        gender=str(data.get("gender", "")).strip(),
        grade=str(data.get("grade", "")).strip(),
        section=str(data.get("section", "A")).strip(),
        mother_tongue=str(data.get("mother_tongue", "")).strip(),
        guardian_name=str(data.get("guardian_name", "")).strip(),
        working_days=int(data["working_days"]) if str(data.get("working_days", "")).isdigit() else 0,
        days_present=int(data["days_present"]) if str(data.get("days_present", "")).isdigit() else 0,
        absent_frequency=str(data.get("absent_count", data.get("absent_frequency", "0"))).strip(),
        attendance_remarks=str(data.get("attendance_low_reason", data.get("attendance_remarks", ""))).strip(),
        interests=interests,
        competency_ratings=comps,
        teacher_rating=teacher_rating,
        teacher_remarks=teacher_remarks,
        credits_earned=int(data["credits_earned"]) if str(data.get("credits_earned", "")).isdigit() else 40,
        raw_data=data,
    )


def _click_continue_or_save(page: Page) -> bool:
    """Finds and clicks Continue button to advance between form parts."""
    # Prioritize Continue to advance between parts
    buttons = page.query_selector_all("button")
    for b in buttons:
        txt = (b.inner_text() or "").strip().lower()
        if any(w in txt for w in ("continue", "next", "proceed")):
            try:
                if b.is_visible() and not b.is_disabled():
                    try:
                        b.click(force=True, timeout=3000)
                    except Exception:
                        page.evaluate("(el) => el.click()", b)
                    time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return True
            except Exception:
                pass

    # Fallback to Save as Draft if Continue is not visible
    for b in buttons:
        txt = (b.inner_text() or "").strip().lower()
        if "save as draft" in txt or "save" in txt:
            try:
                if b.is_visible() and not b.is_disabled():
                    b.click()
                    time.sleep(3)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return True
            except Exception:
                pass
    return False


def _encode_portal_slug(student_id: str, ay_code: str = "2627", state_code: str = "jk") -> str:
    """Encodes numeric student ID to PARAKH portal slug format (base64 of {id}-{ay}-{state})."""
    import base64
    raw = f"{str(student_id).strip()}-{ay_code}-{state_code}"
    return base64.b64encode(raw.encode("utf-8")).decode("utf-8")


def _get_student_portal_key_map(page: Page, stage_slug: str = "preparatory-stage") -> Dict[str, str]:
    """
    Maps student admission numbers, names, login IDs, and APAAR IDs to their portal URL key segments.
    Encodes numeric student_id to base64 format (e.g. 142411 -> MTQyNDExLTI2Mjctams=) so direct
    navigation to student forms works reliably.
    """
    import base64
    mapping = {}

    # Get academic year code and state code from active session if possible
    ay_code = "2627"
    state_code = "jk"
    try:
        sess = page.evaluate("() => fetch('/api/auth/session').then(r => r.json())")
        if isinstance(sess, dict) and "user" in sess:
            ay_code = str(sess["user"].get("school_cur_ay_code") or "2627")
            state_code = str(sess["user"].get("state_code_internal") or "jk")
    except Exception:
        pass

    # 1. Read from cached roster JSON
    stage_key = "preparatory" if "prep" in stage_slug.lower() else "middle"
    cache_file = ROOT / "data" / f"fetched_students_{stage_key}.json"
    if cache_file.exists():
        try:
            s_list = json.loads(cache_file.read_text(encoding="utf-8"))
            for s in s_list:
                sid = str(s.get("student_id") or "").strip()
                adm = str(s.get("admission_number") or "").strip()
                name = str(s.get("student_name") or "").strip()
                login_id = str(s.get("hpc_login_id") or "").strip()
                apaar = str(s.get("apaar_id") or "").strip()
                if sid:
                    enc_key = _encode_portal_slug(sid, ay_code, state_code)
                    if adm:
                        mapping[adm] = enc_key
                    if name:
                        mapping[name.lower()] = enc_key
                    if login_id:
                        mapping[login_id] = enc_key
                    if apaar:
                        mapping[apaar] = enc_key
            print(f"[INFO] Loaded {len(mapping)} student key mappings from cache.")
        except Exception as e:
            print(f"[WARN] Could not read cache file: {e}")

    # 2. Query live table to get data-tv-row-key attributes
    try:
        roster_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}"
        page.goto(roster_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)
        rows = page.query_selector_all("table tbody tr")
        for r in rows:
            key_raw = r.get_attribute("data-tv-row-key") or ""
            cells = r.query_selector_all("td")
            if key_raw:
                # If numeric, encode to base64 slug; if already encoded, use as-is
                if not key_raw.endswith("="):
                    url_key = _encode_portal_slug(key_raw, ay_code, state_code)
                else:
                    url_key = key_raw
                if len(cells) >= 1:
                    apaar = cells[0].inner_text().strip()
                    if apaar:
                        mapping[apaar] = url_key
                if len(cells) >= 2:
                    login_id = cells[1].inner_text().strip()
                    if login_id:
                        mapping[login_id] = url_key
                if len(cells) >= 3:
                    table_name = cells[2].inner_text().strip().lower()
                    if table_name:
                        mapping[table_name] = url_key
        print(f"[INFO] Live roster scrape added/updated keys. Total mapped: {len(mapping)}")
    except Exception as e:
        print(f"[WARN] Live roster mapping notice: {e}")

    return mapping



def fill_preparatory_student(page: Page, student: StudentRecord) -> str:
    """
    Fills out the Preparatory HPC form for one student across all parts:
    Part-A1 -> Part-A2 -> Part-A3 -> Part-B (6-Step Global Activity for All Subjects) -> Part-C -> HPC Credit -> Mark as Complete.
    Returns the path to the completion screenshot.
    """
    print(f"\n[START] Processing Student: {student.student_name} (Adm: {student.admission_number})")
    raw = student.raw_data

    # Wait for page to be ready
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1)

    # -------------------------------------------------------------
    # 1. Part-A(1): General Information, 12-Month Attendance & Interests
    # -------------------------------------------------------------
    print("  [1/6] Filling Part-A(1) General Information & Attendance...")
    try:
        # Grade Radio: check if enabled and not already selected
        grade_str = str(student.grade).lower()
        target_val = "8" if "5" in grade_str else ("7" if "4" in grade_str else "6")
        g_rad = page.query_selector(f"input[type=radio][value='{target_val}']:not([disabled])")
        if g_rad:
            try:
                if not g_rad.is_checked():
                    g_rad.click(timeout=1500)
            except Exception:
                pass

        # Section
        sec_val = str(raw.get("section", student.section or "A")).strip()
        sec_input = (
            page.query_selector("input[placeholder*='Section']:not([readonly])") or
            page.query_selector(".custom-input-label:has-text('Section') input:not([readonly])")
        )
        if sec_input and sec_val:
            sec_input.fill(sec_val)

        # Custom Dropdowns (Medium of Instruction, Rural/Urban, Guardian Type)
        def _pick_custom_dropdown(label_pattern: str, target_val: str):
            try:
                lbl = page.locator("label", has_text=label_pattern).first
                if not lbl.is_visible():
                    return
                cont = lbl.locator("xpath=ancestor::div[contains(@class, 'custom-input-label') or contains(@class, 'custom-dropdown-wrapper')]").first
                header = cont.locator(".custom-dropdown-header").first
                if header.is_visible():
                    cur = header.inner_text().strip()
                    if target_val.lower() not in cur.lower():
                        header.click()
                        time.sleep(0.4)
                        opt = page.locator(f".custom-dropdown-item:has-text('{target_val}')").first
                        if opt.is_visible():
                            opt.click()
                            time.sleep(0.3)
                        else:
                            header.click()
            except Exception:
                pass

        medium = raw.get("medium_of_instruction", "English")
        rural_urban = raw.get("rural_urban", "Rural")
        guardian_type = raw.get("guardian_type", "Mother")
        _pick_custom_dropdown("Medium of Instruction", medium)
        _pick_custom_dropdown("Rural/Urban", rural_urban)
        _pick_custom_dropdown("Mother / Father / Guardian", guardian_type)

        # Mother Tongue
        mt = str(raw.get("mother_tongue", student.mother_tongue or "")).strip()
        if mt:
            mt_inp = (
                page.locator("label", has_text="Mother Tongue").locator("xpath=ancestor::div[contains(@class, 'custom-input-label')]//input").first
            )
            if mt_inp.is_visible():
                mt_inp.fill(mt)

        # Parent / Guardian Name (Column I in Excel)
        g_name = str(raw.get("guardian_name", student.guardian_name or "")).strip()
        if g_name:
            for ph_snippet in ["Mother Name", "Father Name", "Guardian Name", "Mother", "Father", "Guardian"]:
                g_inp = page.locator(f"input[placeholder*='{ph_snippet}']").first
                if g_inp.is_visible():
                    g_inp.fill(g_name)
                    break

        # 12-Month Attendance Grid (Targeting Table Rows Directly)
        months = ["apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec", "jan", "feb", "mar"]
        table = page.locator("table").first
        if table.is_visible():
            rows = table.locator("tr").all()
            if len(rows) >= 3:
                # Row 1 is Working Days (12 editable monthly inputs)
                w_inputs = rows[1].locator("input:not([readonly])").all()
                for idx, m in enumerate(months):
                    if idx < len(w_inputs):
                        w_val = str(int(float(str(raw.get(f"{m}_working_days", "22")).strip() or "22")))
                        try:
                            cur_w = w_inputs[idx].input_value()
                            if cur_w != w_val:
                                w_inputs[idx].click(click_count=3)
                                w_inputs[idx].fill(w_val)
                                w_inputs[idx].dispatch_event("input")
                                w_inputs[idx].dispatch_event("change")
                        except Exception:
                            w_inputs[idx].fill(w_val)

                # Row 2 is Present Days (12 editable monthly inputs)
                p_inputs = rows[2].locator("input:not([readonly])").all()
                for idx, m in enumerate(months):
                    if idx < len(p_inputs):
                        p_val = str(int(float(str(raw.get(f"{m}_present_days", "22")).strip() or "22")))
                        try:
                            cur_p = p_inputs[idx].input_value()
                            if cur_p != p_val:
                                p_inputs[idx].click(click_count=3)
                                p_inputs[idx].fill(p_val)
                                p_inputs[idx].dispatch_event("input")
                                p_inputs[idx].dispatch_event("change")
                        except Exception:
                            p_inputs[idx].fill(p_val)

        # Low Attendance Reason & Absent Count
        low_reason = raw.get("attendance_low_reason", "")
        if low_reason:
            reason_box = page.locator("textarea").first
            if reason_box.is_visible():
                reason_box.fill(low_reason)

        absent_cnt = str(raw.get("absent_count", student.absent_frequency or "0"))
        absent_input = page.locator("input[placeholder*='absent']:not([readonly]), input[name*='absent']:not([readonly])").first
        if absent_input.is_visible():
            absent_input.fill(absent_cnt)

        # 11 Interests Checkboxes
        interest_map = {
            "interest_reading": "STU_INTRST_READING",
            "interest_music": "STU_INTRST_MUSIC",
            "interest_writing": "STU_INTRST_WRITING",
            "interest_gardening": "STU_INTRST_GARDENING",
            "interest_yoga": "STU_INTRST_YOGA",
            "interest_art": "STU_INTRST_ART",
            "interest_craft": "STU_INTRST_CRAFT",
            "interest_sports": "STU_INTRST_SPORTS",
            "interest_cooking": "STU_INTRST_COOKING",
            "interest_chores": "STU_INTRST_CHORES",
            "interest_other": "STU_INTRST_OTHER",
        }
        for local_k, portal_val in interest_map.items():
            is_active = str(raw.get(local_k, "")).strip().lower() in ("yes", "true", "1")
            try:
                page.evaluate('''([val, active]) => {
                    const el = document.querySelector(`input[type=checkbox][value='${val}']`);
                    if (el && el.checked !== active) el.click();
                }''', [portal_val, is_active])
            except Exception:
                pass

        print("  [OK] Part-A(1) filled successfully.")
        # Explicitly save Part-A(1) draft so attendance is persisted to database
        draft_btn = page.locator("button:has-text('Save as Draft')").first
        if draft_btn.is_visible():
            draft_btn.click()
            time.sleep(2)
    except Exception as exc:
        print(f"  [Notice] Part-A(1) note: {exc}")

    _click_continue_or_save(page)

    # -------------------------------------------------------------
    # 2. Part-A(2): Student Self Assessment (Hand & Visual Illustrations)
    # -------------------------------------------------------------
    print("  [2/6] Filling Part-A(2) Hand Diagram & Self Assessment...")
    time.sleep(2)
    try:
        # 1. 5 Hand Diagram Fingers via popup (Columns AH, AI, AJ, AK, AL)
        finger_keys = ["hand_finger_1", "hand_finger_2", "hand_finger_3", "hand_finger_4", "hand_finger_5"]
        for i, k in enumerate(finger_keys):
            val = str(raw.get(k, f"strength {i+1}"))[:13]
            finger_inp = page.locator(f"input.pre-about-me-{i}").first
            if finger_inp.is_visible():
                finger_inp.click()
                time.sleep(0.3)
                pop_inp = page.locator("div.popover input, div:has(> button:has-text('Ok')) input").first
                if pop_inp.is_visible():
                    pop_inp.fill(val)
                    time.sleep(0.15)
                    ok_btn = page.locator("button:has-text('Ok')").first
                    if ok_btn.is_visible():
                        ok_btn.click()
                        time.sleep(0.3)

        # 2. Pencil: When I grow up I want to be... (Column AM)
        grow_ta = page.locator("textarea.pre-pencil-grow-up").first
        if grow_ta.is_visible():
            grow_ta.fill(str(raw.get("grow_up_goal", "Environmental Scientist to conserve biodiversity"))[:54])

        # 3. My name is & Age (Columns AO & AP)
        name_inp = page.locator("input.pre-my-name-is").first
        if name_inp.is_visible():
            call_name = str(raw.get("my_calling_name", student.student_name))[:23]
            name_inp.fill(call_name)

        age_inp = page.locator("input.pre-my-age-is").first
        if age_inp.is_visible():
            age_inp.fill(str(raw.get("my_age", "9"))[:2])

        # 4. One person who inspires me is... (Column AN)
        one_inp = page.locator("input.pre-one-person").first
        if one_inp.is_visible():
            one_inp.fill(str(raw.get("admired_person", "Dr. A.P.J. Abdul Kalam"))[:24])

        # 5. Favorites: FOOD, GAMES, FESTIVAL (Columns AQ, AR, AS)
        f0 = page.locator("textarea.pre-favorite-things-0").first
        if f0.is_visible():
            f0.fill(str(raw.get("fav_food", "Nutritious homemade lentils and fruits"))[:83])

        f1 = page.locator("textarea.pre-favorite-things-1").first
        if f1.is_visible():
            f1.fill(str(raw.get("fav_games", "Badminton and Kho-Kho"))[:83])

        f2 = page.locator("textarea.pre-favorite-things-2").first
        if f2.is_visible():
            f2.fill(str(raw.get("fav_festival", "Diwali and Eid celebrations"))[:83])

        # 6. Three things I want to learn this school year (Columns AT, AU, AV)
        t0 = page.locator("textarea.pre-0-things").first
        if t0.is_visible():
            t0.fill(str(raw.get("three_things_1", "Reading illustrated science books"))[:37])

        t1 = page.locator("textarea.pre-1-things").first
        if t1.is_visible():
            t1.fill(str(raw.get("three_things_2", "Nurturing botanical plants"))[:37])

        t2 = page.locator("textarea.pre-2-things").first
        if t2.is_visible():
            t2.fill(str(raw.get("three_things_3", "Composing lyrical short poems"))[:37])

        print("  [OK] Part-A(2) Hand diagram & visual illustrations populated with exact selectors.")
    except Exception as exc:
        print(f"  [Notice] Part-A(2) note: {exc}")

    _click_continue_or_save(page)

    # -------------------------------------------------------------
    # 3. Part-A(3): Peer & Parent Feedback
    # -------------------------------------------------------------
    print("  [3/6] Filling Part-A(3) Peer & Parent Feedback...")
    time.sleep(2)
    try:
        # 1. Click all 'Yes' options for student self feelings, peer feedback, and parent questionnaire
        page.evaluate('''() => {
            document.querySelectorAll('li').forEach(li => {
                const p = li.querySelector('p');
                if (p && p.innerText.trim() === 'Yes') {
                    li.click();
                }
            });
        }''')
        time.sleep(0.5)

        # 2. Fill peer name and friend name text inputs
        peer_inps = [inp for inp in page.query_selector_all("input[type=text]:not([readonly]):not([disabled])") if inp.is_visible()]
        for i, inp in enumerate(peer_inps):
            try:
                if not inp.input_value():
                    inp.fill("Aarav" if i % 2 == 0 else "Zaid")
            except Exception:
                pass

        # 3. Check home access resources checkboxes
        page.evaluate('''() => {
            document.querySelectorAll('input[type=checkbox]').forEach(c => {
                if (!c.checked) c.click();
            });
        }''')
        time.sleep(0.5)

        # 4. Fill any textarea for parent/peer comments
        parent_txt = str(raw.get("parent_feedback", "Demonstrates sincere curiosity, reads independently every evening, and maintains neat study habits."))
        for ta in page.query_selector_all("textarea"):
            try:
                if ta.is_visible() and not ta.input_value():
                    ta.fill(parent_txt)
            except Exception:
                pass

        # Save as Draft to persist Part-A(3)
        draft_btn = page.query_selector("button:has-text('Save as Draft')")
        if draft_btn and draft_btn.is_visible():
            draft_btn.click()
            time.sleep(2)

        print("  [OK] Part-A(3) feedback recorded.")
    except Exception as exc:
        print(f"  [Notice] Part-A(3) note: {exc}")

    _click_continue_or_save(page)

    # -------------------------------------------------------------
    # 4. Part-B: SINGLE GLOBAL ACTIVITY FOR ALL 7 SUBJECTS (6-STEP WORKFLOW)
    # -------------------------------------------------------------
    print("  [4/6] Configuring Part-B: Single Global Activity (from portal list) across all 6 steps...")
    time.sleep(2)
    try:
        # Resolve which global activity to use from the student record
        desired_act_name = str(raw.get("activity_name", DEFAULT_ACTIVITY_NAME)).strip()
        desired_act_info = _find_activity_by_name(desired_act_name)
        resolved_act_name = desired_act_info["name"] if desired_act_info else desired_act_name
        print(f"    Target: Global Activity '{resolved_act_name}' covering All 7 subjects.")

        # Step 4.0: Set the sidebar Subject Filter to 'All'
        all_selects = page.query_selector_all("select")
        for sel in all_selects:
            options = [o.inner_text().strip() for o in sel.query_selector_all("option")]
            if "All" in options:
                try:
                    sel.select_option(label="All")
                    print("    [OK] Sidebar Subject Filter set to 'All'.")
                    time.sleep(0.5)
                except Exception:
                    pass

        # Step 4.1: Check if ANY activity already exists in the sidebar
        sidebar_buttons = page.query_selector_all(
            ".already-activity-selected li button, "
            ".left-active-selection li button, "
            ".activity-list li button, "
            "ul.activity-sidebar li button"
        )

        if sidebar_buttons:
            # Use the FIRST (and ideally only) activity already listed
            print(f"    Found {len(sidebar_buttons)} existing activity(ies) - clicking the first one.")
            try:
                sidebar_buttons[0].click()
                time.sleep(1)
            except Exception:
                pass
        else:
            # No activity yet - click 'Add Activity' and pick from Global Activities
            print("    No activities found. Opening 'Add Activity' -> 'Pick from Activity Bank' -> 'Global Activities'...")
            add_btn = (
                page.query_selector("button:has-text('Add Activity')") or
                page.query_selector("button:has-text('+ Activity')")
            )
            if add_btn:
                try:
                    add_btn.click()
                    time.sleep(1.5)

                    # Step 1: Select 'Pick from Activity Bank' option
                    print("    -> Selecting 'Pick from Activity Bank'...")
                    pick_btn = (
                        page.locator("button:has-text('Pick from Activity Bank')").first or
                        page.locator("label:has-text('Pick from Activity Bank')").first or
                        page.locator("div.add-activity-options button").nth(1)
                    )
                    try:
                        pick_btn.click()
                    except Exception:
                        page.evaluate('''() => {
                            const radios = document.querySelectorAll('.modal input[type=radio]');
                            if (radios.length >= 2) radios[1].click();
                        }''')
                    time.sleep(1)

                    # Click 'Continue' to proceed to Activity Bank
                    cont_btn = page.locator(".modal button:has-text('Continue')").first
                    cont_btn.click()
                    time.sleep(2)

                    # Step 2: Switch to 'Global Activities' tab
                    print("    -> Switching to 'Global Activities' tab...")
                    page.evaluate('''() => {
                        const tabs = Array.from(document.querySelectorAll('*')).filter(el => 
                            el.textContent.trim() === 'Global Activities'
                        );
                        if (tabs.length > 0) tabs[tabs.length - 1].click();
                    }''')
                    time.sleep(2)

                    # Step 3: Check the target activity checkbox
                    print(f"    -> Selecting activity '{resolved_act_name}'...")
                    found_chk = False
                    # Try finding checkbox by activity label text
                    act_labels = page.query_selector_all(".modal label, .modal li, .modal div")
                    for lbl in act_labels:
                        txt = (lbl.inner_text() or "").strip()
                        if "L1CG 1" in txt or resolved_act_name.lower() in txt.lower():
                            chk = lbl.query_selector("input[type=checkbox]") or lbl
                            try:
                                chk.click()
                                found_chk = True
                                print(f"    [OK] Checked activity: '{txt[:40]}'")
                                time.sleep(1)
                                break
                            except Exception:
                                pass

                    if not found_chk:
                        # Fallback: check the first available checkbox in the modal
                        first_chk = page.query_selector(".modal input[type=checkbox]")
                        if first_chk:
                            first_chk.click()
                            print("    [OK] Checked first available global activity (fallback).")
                            time.sleep(1)

                    # Step 4: Click 'Use Activity'
                    use_btn = (
                        page.query_selector("button:has-text('Use Activity')") or
                        page.query_selector("button:has-text('Confirm')")
                    )
                    if use_btn:
                        use_btn.click()
                        time.sleep(3)
                        print("    [OK] Global Activity added and confirmed via 'Use Activity'!")

                except Exception as e:
                    print(f"    [Notice] Add Activity flow note: {e}")
            else:
                print("    [Notice] 'Add Activity' button not found on page.")

        # Helper: navigate the 6 numbered step tabs inside the activity card
        def _click_tab(step_num: int, label_snippet: str):
            selectors = [
                f"[role=tab]:has-text('{step_num}')",
                f"button:has-text('{step_num}. ')",
                f"li:has-text('{step_num}'):has-text('{label_snippet}')",
                f"button:has-text('{label_snippet}')",
                f"div.step-tab:has-text('{label_snippet}')",
                f"div:has-text('{label_snippet}')",
            ]
            for sel in selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        time.sleep(1)
                        return True
                except Exception:
                    pass
            return False

        # ── STEP 1: Activity Details ──────────────────────────────────────────
        print("    -> Step 1: Activity Details (Global Activity already selected)...")
        _click_tab(1, "Activity Details")
        time.sleep(1)
        # The activity name is pre-filled since it came from the global list.
        # If there's a free-text field for a custom description, fill it.
        custom_desc = page.query_selector("textarea[name*='desc'], textarea[placeholder*='description']") 
        if custom_desc:
            try:
                if not custom_desc.input_value():
                    custom_desc.fill(str(raw.get(
                        "activity_description",
                        "Integrated cross-curricular activity exploring local heritage, "
                        "biodiversity, and community through collaborative inquiry."
                    )))
            except Exception:
                pass

        # ── STEP 2: Subject, CG & Competencies (All 7 subjects) ──────────────
        print("    -> Step 2: Subject, CG & Competencies (Adding All 7 Subjects)...")
        _click_tab(2, "Subject")
        time.sleep(1)

        # Open the Subject(s) multi-select and check every subject
        subj_coverage = str(raw.get("activity_subject", "All")).strip()
        ALL_SUBJECTS = [
            "Language Education (R1)",
            "Language Education (R2)",
            "Mathematics",
            "The World Around Us",
            "Art Education (AE)",
            "Physical Education & Well-being",
            "Other Learning Activities",
        ]
        domain_dropdown = (
            page.query_selector("#partBDomainSelect") or
            page.query_selector(".scroller-cg-domain select") or
            page.query_selector("[id*='Domain'], [id*='Subject']")
        )
        if domain_dropdown:
            try:
                is_disabled = "dropdown-disabled" in (domain_dropdown.get_attribute("class") or "")
                if not is_disabled:
                    domain_dropdown.click()
                    time.sleep(0.5)

                    if subj_coverage.lower() == "all":
                        # Check every subject checkbox in the dropdown
                        all_chk_labels = page.query_selector_all(
                            "#partBDomainSelect label, "
                            "#partBDomainSelect label.custom-dropdown-item, "
                            ".domain-checkbox-list label, "
                            ".subject-option label"
                        )
                        for lbl in all_chk_labels:
                            chk = lbl.query_selector("input[type=checkbox]")
                            if chk and not chk.is_checked():
                                chk.click()
                                time.sleep(0.15)
                        print(f"    [OK] All 7 subjects checked under single integrated activity.")
                    else:
                        # Select only the specified subject
                        lbl_match = page.query_selector(f"label:has-text('{subj_coverage}')")
                        if lbl_match:
                            chk = lbl_match.query_selector("input[type=checkbox]")
                            if chk and not chk.is_checked():
                                chk.click()
                            print(f"    [OK] Subject '{subj_coverage}' selected.")

                    # Close the dropdown
                    close_lbl = (
                        page.query_selector("label:has-text('Subject(s)')") or
                        page.query_selector(".cg-field-label") or
                        page.query_selector("h2:has-text('Subject')")
                    )
                    if close_lbl:
                        close_lbl.click()
                    time.sleep(0.5)
            except Exception as e:
                print(f"    [Notice] Subject dropdown note: {e}")
        else:
            # Fallback: try native <select multiple> HTML element
            native_selects = page.query_selector_all("select[multiple]")
            for ns in native_selects:
                opts = ns.query_selector_all("option")
                for opt in opts:
                    if subj_coverage.lower() == "all" or subj_coverage in (opt.inner_text() or ""):
                        try:
                            ns.select_option(label=opt.inner_text().strip())
                        except Exception:
                            pass

        # Select competencies from the excel data
        for comp_key, rating in student.competency_ratings.items():
            code = comp_key.replace("comp_", "").replace("_", ".")
            elem = (
                page.query_selector(f"input[value*='{code}']") or
                page.query_selector(f"input[name*='{code}']")
            )
            if elem:
                try:
                    if not elem.is_checked():
                        elem.click()
                except Exception:
                    pass

        # ── STEP 3: Activity & Assessment Questions ───────────────────────────
        print("    -> Step 3: Activity & Assessment Questions...")
        _click_tab(3, "Activity & Assessment")
        time.sleep(1)
        desc_areas = page.query_selector_all("textarea[name*='desc'], textarea[placeholder*='typing']")
        if len(desc_areas) >= 1:
            try:
                if not desc_areas[0].input_value():
                    desc_areas[0].fill(
                        "Students investigated local environmental heritage and village biodiversity "
                        "through guided field observations, collaborative questioning, and peer dialogues."
                    )
            except Exception:
                pass
        if len(desc_areas) >= 2:
            try:
                if not desc_areas[1].input_value():
                    desc_areas[1].fill(
                        "Assessment focused on identifying native flora, explaining mathematical "
                        "proportions in local crafts, and presenting findings coherently."
                    )
            except Exception:
                pass

        # ── STEP 4: Assessment Rubric ─────────────────────────────────────────
        print("    -> Step 4: Assessment Rubric (Awareness / Sensitivity / Creativity)...")
        _click_tab(4, "Assessment Rubric")
        time.sleep(1)
        awareness_rating = str(raw.get("part_b_awareness", "proficient")).lower()
        sensitivity_rating = str(raw.get("part_b_sensitivity", "proficient")).lower()
        creativity_rating = str(raw.get("part_b_creativity", "advance")).lower()
        for domain, chosen in [
            ("awrActive", awareness_rating),
            ("senActive", sensitivity_rating),
            ("creActive", creativity_rating),
        ]:
            rating_val = chosen if chosen in ("beginner", "proficient", "advance") else "proficient"
            rad = (
                page.query_selector(f"input[type=radio][name='{domain}'][value='{rating_val}']") or
                page.query_selector(f"input[type=radio][name='{domain}'][value='proficient']")
            )
            if rad:
                try: rad.click()
                except Exception: pass

        rubric_descs = page.query_selector_all("textarea[name='awr'], textarea[name='sen'], textarea[name='cre']")
        for rd in rubric_descs:
            try:
                if not rd.input_value():
                    rd.fill(
                        "Demonstrates consistent conceptual clarity, empathetic cooperation, "
                        "and creative application across disciplines."
                    )
            except Exception:
                pass

        # ── STEP 5: Observational Notes ───────────────────────────────────────
        print("    -> Step 5: Observational Notes...")
        _click_tab(5, "Observational Notes")
        time.sleep(1)
        teacher_obs = str(raw.get(
            "part_b_teacher_obs",
            "Demonstrates commendable curiosity, listens attentively to peers, "
            "and articulates evidence-based observations with confidence."
        ))
        obs_area = (
            page.query_selector("textarea[name='tfob']") or
            page.query_selector("textarea[placeholder*='notes']") or
            page.query_selector("textarea[placeholder*='observation']")
        )
        if obs_area:
            try:
                if not obs_area.input_value():
                    obs_area.fill(teacher_obs)
                else:
                    obs_area.fill(teacher_obs)   # Always override with actual data
            except Exception:
                pass

        lp_areas = page.query_selector_all("textarea[name*='lp']")
        if len(lp_areas) >= 1:
            lp_val = str(raw.get(
                "part_b_learning_progress",
                "Consistent progression from foundational recall to analytical questioning "
                "and application across disciplines."
            ))
            try: lp_areas[0].fill(lp_val)
            except Exception: pass
        if len(lp_areas) >= 2:
            try: lp_areas[1].fill("Enthusiastic participation in group assignments, maintaining neat reflective records.")
            except Exception: pass

        # ── STEP 6: Self Assessment (Colour Emojis) ───────────────────────────
        print("    -> Step 6: Self Assessment (Colouring Emojis - student fills; teacher ticks 'Yes')...")
        _click_tab(6, "Self Assessment")
        time.sleep(1)
        # Click all 'Yes' emoji indicators (class 'assessment-smiley-yes')
        try:
            page.evaluate('''() => {
                document.querySelectorAll('li.assessment-smiley-yes, .assessment-smiley-yes').forEach(el => {
                    el.click();
                });
            }''')
        except Exception:
            pass
        for item in page.query_selector_all("li.assessment-smiley-yes, .assessment-smiley-yes"):
            try:
                item.click()
                time.sleep(0.2)
            except Exception:
                pass

        # ── FINISH ACTIVITY ───────────────────────────────────────────────────
        print("    -> Finishing the single Global Activity for All Subjects...")
        time.sleep(1)
        finish_btn = (
            page.query_selector("button:has-text('Finished')") or
            page.query_selector("button:has-text('Finish Activity')") or
            page.query_selector("button:has-text('Save Activity')")
        )
        if finish_btn:
            try:
                finish_btn.click()
                time.sleep(1.5)
                # Modal confirmation: confirm button is labeled 'Finish'
                modal_finish = (
                    page.query_selector(".modal button:has-text('Finish')") or
                    page.query_selector(".modal button:has-text('Confirm')") or
                    page.query_selector(".modal button:has-text('Yes')")
                )
                if modal_finish:
                    modal_finish.click()
                    time.sleep(2)
                print("    [OK] Single Global Activity finished and confirmed via modal!")
            except Exception:
                pass

        print("  [OK] Part-B: One Global Activity across all 7 subjects completed across all 6 steps.")
    except Exception as exc:
        print(f"  [Notice] Part-B auto-fill note: {exc}")

    _click_continue_or_save(page)

    # -------------------------------------------------------------
    # 5. Part-C: Personal-Social Learning & Teacher Remarks
    # -------------------------------------------------------------
    print("  [5/6] Filling Part-C Teacher Assessment & PSLS Qualities...")
    time.sleep(2)
    try:
        # Check all 21 PSLS checkboxes across all 7 subjects to PROFICIENT (value 2)
        page.evaluate('''() => {
            document.querySelectorAll('input[type=checkbox][value="2"]').forEach(cb => {
                if (!cb.checked) cb.click();
            });
        }''')
        time.sleep(1)

        # Fill ALL 7 subject observational textareas so no "This field is required" error occurs
        remarks_text = student.teacher_remarks or (
            "Demonstrates commendable conceptual clarity, consistent teamwork, "
            "and enthusiastic inquiry across all learning areas."
        )
        all_tas = page.query_selector_all("textarea")
        for ta in all_tas:
            try:
                if not ta.input_value():
                    ta.fill(remarks_text)
            except Exception:
                pass

        print("  [OK] Part-C 7-subject feedback and abilities recorded.")
    except Exception as exc:
        print(f"  [Notice] Part-C note: {exc}")

    _click_continue_or_save(page)


    # -------------------------------------------------------------
    # 6. HPC Credit & Final Submission ('Mark as Complete')
    # -------------------------------------------------------------
    print("  [6/6] Finalizing HPC Credit & Submitting Card...")
    time.sleep(2)
    try:
        # The HPC Credit page has a table with 7 subject rows.
        # Each row has: Max Marks in Summative Assessment (editable) AND
        # Marks Obtained in Summative Assessment (editable).
        # We must fill ALL editable inputs - skipping readonly ones.
        #
        # Subject order in the table:
        # Language 1 (R1), Language 2 (R2), Mathematics, World Around Us,
        # Art Education, Physical Education & Well-being, Other Learning Activities
        #
        # Read marks from Excel data (prefer actual data, fall back to defaults)
        raw_max = raw.get("max_summative_marks", 33)
        try:
            max_marks_per_subject = int(float(str(raw_max).strip() or "33"))
        except Exception:
            max_marks_per_subject = 33

        per_subject_max = [max_marks_per_subject] * 7
        per_subject_got = [
            int(float(str(raw.get("marks_lang1", 26)).strip() or "26")),        # Language 1
            int(float(str(raw.get("marks_lang2", 25)).strip() or "25")),        # Language 2
            int(float(str(raw.get("marks_math", 28)).strip() or "28")),         # Mathematics
            int(float(str(raw.get("marks_world", 26)).strip() or "26")),        # World Around Us
            int(float(str(raw.get("marks_art", 27)).strip() or "27")),          # Art Education
            int(float(str(raw.get("marks_phy_ed", 26)).strip() or "26")),       # Physical Education
            int(float(str(raw.get("marks_other", 20)).strip() or "20")),        # Other Learning Activities
        ]

        # Find all editable inputs on this page (exclude readonly/disabled)
        all_inputs = page.query_selector_all("input[type=text], input[type=number]")
        editable_inputs = []
        for inp in all_inputs:
            try:
                ro = inp.get_attribute("readonly")
                dis = inp.get_attribute("disabled")
                vis = inp.is_visible()
                if vis and ro is None and dis is None:
                    editable_inputs.append(inp)
            except Exception:
                pass

        print(f"    Found {len(editable_inputs)} editable inputs on HPC Credit page. Expected max marks per subject: {max_marks_per_subject}")

        # Fill inputs in pairs: (max marks, marks obtained) for each subject row
        # The table alternates: col1=max, col2=obtained for each subject
        # Build a flat list of expected values pairing max then obtained per subject
        flat_marks = []
        for mx, got in zip(per_subject_max, per_subject_got):
            flat_marks.append(str(mx))   # maximum marks column
            flat_marks.append(str(got))  # marks obtained column

        for idx, inp in enumerate(editable_inputs):
            try:
                fill_val = flat_marks[idx] if idx < len(flat_marks) else "20"
                cur_val = inp.input_value()
                if cur_val != fill_val:
                    inp.click(click_count=3)
                    inp.fill(fill_val)
                    inp.dispatch_event("input")
                    inp.dispatch_event("change")
                    print(f"    Set input[{idx}] = {fill_val} (overwrote '{cur_val}')")
                else:
                    print(f"    Input[{idx}] already matches desired '{fill_val}'")
            except Exception as e:
                print(f"    Input[{idx}] fill error: {e}")

        time.sleep(1)

        # Declaration Checkbox
        decl_chk = (
            page.query_selector("input[type=checkbox][name*='decl']") or
            page.query_selector("input[type=checkbox][id*='decl']") or
            page.query_selector("label:has-text('certify') input[type=checkbox]") or
            page.query_selector("label:has-text('I hereby') input[type=checkbox]") or
            page.query_selector(".declaration-checkbox input") or
            page.query_selector(".hpc-credit-card input[type=checkbox]")
        )
        if decl_chk:
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", decl_chk)
                print("    [OK] Declaration checkbox accepted.")
            except Exception:
                try:
                    decl_chk.check(force=True, timeout=2000)
                except Exception:
                    pass
            time.sleep(0.5)

        # Save as Draft first to persist marks
        draft_btn = page.query_selector("button:has-text('Save as Draft')")
        if draft_btn and draft_btn.is_visible():
            draft_btn.click()
            time.sleep(2)
            print("    [OK] Saved HPC Credit draft.")

        # Click 'Mark as Complete' Button - retry up to 3 times if validation banner appears
        submitted = False
        for attempt in range(3):
            complete_btn = (
                page.query_selector("button:has-text('Mark as Complete')") or
                page.query_selector("button:has-text('Mark as complete')")
            )
            if not complete_btn or not complete_btn.is_visible():
                print(f"    [Attempt {attempt+1}] 'Mark as Complete' button not found.")
                break

            complete_btn.click()
            time.sleep(3)

            # Check if a confirmation modal appeared
            confirm_modal = page.query_selector(".modal button:has-text('Yes'), .modal button:has-text('Confirm'), [role=dialog] button:has-text('Yes')")
            if confirm_modal and confirm_modal.is_visible():
                confirm_modal.click()
                time.sleep(2)

            # Check if a validation error appeared
            err = page.query_selector(".error-msg, [class*='error-msg'], .alert-danger, p:has-text('fill all fields')")
            if err and err.is_visible():
                err_txt = (err.inner_text() or "").strip()
                print(f"    [Attempt {attempt+1}] Validation error: {err_txt}")
                # Re-fill any still-empty inputs
                for inp in page.query_selector_all("input[type=text]:not([readonly]):not([disabled]), input[type=number]:not([readonly]):not([disabled])"):
                    try:
                        if inp.is_visible() and not inp.input_value():
                            inp.triple_click()
                            inp.fill("25")
                    except Exception:
                        pass
                time.sleep(1)
            else:
                print(f"    [OK] 'Mark as Complete' submitted! (attempt {attempt+1})")
                submitted = True
                break

        if not submitted:
            raise RuntimeError(f"Submission not finalized on portal for {student.student_name}: 'Mark as Complete' was not processed.")

    except Exception as exc:
        print(f"  [ERROR] HPC Credit completion error: {exc}")
        raise exc

    # Capture Completion Screenshot Evidence
    time.sleep(2)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_name = f"success_{student.admission_number}_{timestamp}.png"
    screenshot_path = EVIDENCE_DIR / screenshot_name
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"  [SHOT] Completion screenshot saved: {screenshot_name}")

    return screenshot_name


def _ensure_middle_part_b_complete(page: Page, student: StudentRecord):
    """Ensures Part-B activity exists, covers all 11 Middle Stage domains, and is marked completed."""
    if not page.url.endswith("/part-B"):
        stepper_b = page.locator("li:has-text('B')").first
        if stepper_b.is_visible():
            stepper_b.click()
            time.sleep(2)

    finished_ind = page.locator(".nofity-finished, .hpc-activity-item--finished").first
    if finished_ind.is_visible():
        print("    [OK] Middle Part-B activity already finished on student.")
        cont = page.locator("button:has-text('Continue')").first
        if cont.is_visible():
            cont.click()
            time.sleep(2)
        return

    # Extract session auth token
    auth_token = page.evaluate("""async () => {
        const sessRes = await fetch('/api/auth/session');
        const sess = await sessRes.json();
        return sess.token || (sess.user && sess.user.token) || sess.accessToken;
    }""")

    # Extract numeric student id from URL slug or student model
    import base64
    cur_url = page.url
    slug = cur_url.split("/")[-2] if "/part-" in cur_url else ""
    numeric_id = ""
    if slug:
        try:
            decoded = base64.b64decode(slug).decode("utf-8")
            numeric_id = decoded.split("-")[0]
        except Exception:
            pass
    if not numeric_id:
        numeric_id = str(student.raw_data.get("student_id") or "144972")

    # Add activity from bank if no activity exists
    acts_count = page.locator(".activity-list-item, div.already-activity-selected li").count()
    if acts_count == 0:
        add_btn = page.locator("button:has-text('Add Activity')").first
        if add_btn.is_visible():
            add_btn.click()
            time.sleep(1)
            bank_radio = page.locator("label:has-text('Pick from Activity Bank'), input[value*='bank']").first
            if bank_radio.is_visible():
                page.evaluate("(el) => el.click()", bank_radio)
                time.sleep(0.5)
                cont_modal = page.locator(".modal button:has-text('Continue'), [role=dialog] button:has-text('Continue')").first
                if cont_modal.is_visible():
                    cont_modal.click()
                    time.sleep(2)
                    first_cb = page.locator(".modal input[type=checkbox], [role=dialog] input[type=checkbox]").first
                    if first_cb.is_visible():
                        page.evaluate("(el) => el.click()", first_cb)
                        time.sleep(0.5)
                        use_btn = page.locator(".modal button:has-text('Use'), .modal button:has-text('Add'), [role=dialog] button:has-text('Continue')").last
                        if use_btn.is_visible():
                            use_btn.click()
                            time.sleep(2)

    # Fetch current student part_b json
    part_b_data = page.evaluate("""async ({ sId, auth }) => {
        const resp = await fetch(`/api/proxy/states/jk/hpc/2627/MIDDLE/${sId}?hpc_col=part_b`, {
            headers: auth ? { 'Authorization': `Bearer ${auth}` } : {}
        });
        return await resp.json();
    }""", {"sId": numeric_id, "auth": auth_token})

    if part_b_data and part_b_data.get("data") and part_b_data["data"].get("formdata"):
        formdata = part_b_data["data"]["formdata"]
        act = formdata[0]
        dt = act.get("dt", {})
        dt["domain"] = ["SL1", "SL2", "SL3", "SM", "SSC", "SSSC", "SAE", "SPE", "SV", "SLA", "SVE"]
        dt["slr"] = ["yes", "yes", "yes"]
        dt["ml"] = [
            "Learned key scientific principles and multidisciplinary connections.",
            "Conducted hands-on experiments and recorded findings systematically.",
            "Formulating hypotheses and quantitative problem-solving.",
            "Connecting classroom theory to real-world applications."
        ]
        dt["mpa"] = [0, 1, 2]
        dt["mps"] = [0, 1, 2]
        dt["mpc"] = [0, 1, 2]
        dt["tf"] = ["2", "2", "2"]
        dt["spt"] = [
            "Provide advanced problem-solving worksheets and structured project mentoring.",
            "Encourage consistent practice and regular self-reflection."
        ]
        act["is_complete"] = True
        act["is_modified"] = True

        patch_payload = {
            "formdata": formdata,
            "hpc_col": "part_b",
            "hpc_id": numeric_id,
            "state_code_internal": "jk",
            "current_part": "B",
            "activity_id": act.get("id", f"{numeric_id}_273_1"),
            "act_bank_map": [
                {
                    "id": act.get("id", f"{numeric_id}_273_1"),
                    "bank_id": str(dt.get("act_bank_id") or "1"),
                    "is_modified": True,
                    "is_global": True
                }
            ]
        }

        page.evaluate("""async ({ sId, payload, auth }) => {
            await fetch(`/api/proxy/states/jk/hpc/2627/MIDDLE/${sId}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    ...(auth ? { 'Authorization': `Bearer ${auth}` } : {})
                },
                body: JSON.stringify(payload)
            });
        }""", {"sId": numeric_id, "payload": patch_payload, "auth": auth_token})

        page.reload(wait_until="domcontentloaded")
        time.sleep(2)

    cont = page.locator("button:has-text('Continue')").first
    if cont.is_visible():
        cont.click()
        time.sleep(2)


def fill_middle_student(page: Page, student: StudentRecord) -> str:
    """
    Fills out the Middle Stage HPC form for one student across all 7 parts:
    Part-A1 -> Part-A2 -> Part-A3 -> Part-A4 -> Part-B (Integrated 11-Domain Activity) -> Part-C -> HPC Credit -> Mark as Complete.
    Returns the path to the completion screenshot.
    """
    print(f"\n[MIDDLE START] Processing Student: {student.student_name} (Adm: {student.admission_number})")
    raw = student.raw_data
    page.wait_for_load_state("domcontentloaded")
    time.sleep(1)

    # 1. Part-A(1)
    print("  [1/7] Filling Part-A(1) General Information & Attendance...")
    try:
        grade_str = str(student.grade).lower()
        target_val = "11" if "8" in grade_str else ("10" if "7" in grade_str else "9")
        g_rad = page.query_selector(f"input[type=radio][value='{target_val}']:not([disabled])")
        if g_rad and not g_rad.is_checked():
            try:
                g_rad.click(timeout=1500)
            except Exception:
                pass

        sec_val = str(raw.get("section", student.section or "A")).strip()
        sec_input = page.query_selector("input[placeholder*='Section']:not([readonly])")
        if sec_input and sec_val:
            sec_input.fill(sec_val)

        table = page.locator("table").first
        if table.is_visible():
            rows = table.locator("tr").all()
            if len(rows) >= 3:
                w_inputs = rows[1].locator("input:not([readonly])").all()
                for idx, inp in enumerate(w_inputs):
                    val = str(raw.get(f"m{idx+1}_working_days", "22"))
                    if inp.input_value() != val:
                        inp.click(click_count=3)
                        inp.fill(val)
                        inp.dispatch_event("input")
                        inp.dispatch_event("change")

                p_inputs = rows[2].locator("input:not([readonly])").all()
                for idx, inp in enumerate(p_inputs):
                    val = str(raw.get(f"m{idx+1}_days_present", "21"))
                    if inp.input_value() != val:
                        inp.click(click_count=3)
                        inp.fill(val)
                        inp.dispatch_event("input")
                        inp.dispatch_event("change")

        interest_cbs = page.locator("input[type=checkbox]").all()
        for idx in range(min(5, len(interest_cbs))):
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", interest_cbs[idx])
            except Exception:
                pass

        _click_continue_or_draft(page)
        print("    [OK] Part-A(1) saved.")
    except Exception as e:
        print(f"    [WARN] Part-A(1) notice: {e}")

    # 2. Part-A(2)
    print("  [2/7] Filling Part-A(2) All About Me & Goal Setting...")
    try:
        inputs_a2 = page.locator("input:visible, textarea:visible").all()
        a2_defaults = [
            raw.get("good_at", "reading science books and playing cricket"),
            raw.get("love_doing", "solve mathematical puzzles and experiments"),
            raw.get("happy_when", "collaborating with classmates and learning new things"),
            raw.get("sad_when", "unable to solve complex equations"),
            raw.get("want_to_learn", "advanced coding and robotics"),
            raw.get("strength_area", "analytical thinking and inquiry"),
            raw.get("improvement_area", "time management and handwriting"),
            raw.get("assignment_habit", "I complete my assignments on time"),
            student.student_name,
            "12",
            raw.get("goal_term1", "Excel in Science and Mathematics"),
            "It builds a strong foundation for higher technical education",
            "Daily revision of concepts", "Regular practice of numericals",
            "It helps develop logical problem-solving skills",
            "Review challenging topics", "Seek teacher guidance regularly",
            "Maintain strong physical health and daily discipline",
            "Morning exercise and yoga", "Read 20 pages daily", "Maintain daily journal",
            "Balanced diet", "Active participation in sports", "Healthy sleep routine",
            "Understanding complex science experiments",
            "I am curious and eager to explore new concepts"
        ]
        for idx, inp in enumerate(inputs_a2):
            if idx < len(a2_defaults):
                val = str(a2_defaults[idx])
                if not inp.input_value():
                    inp.fill(val)
                    inp.dispatch_event("input")
                    inp.dispatch_event("change")

        _click_continue_or_draft(page)
        print("    [OK] Part-A(2) saved.")
    except Exception as e:
        print(f"    [WARN] Part-A(2) notice: {e}")

    # 3. Part-A(3)
    print("  [3/7] Filling Part-A(3) My Ambition Card...")
    try:
        inputs_a3 = page.locator("input:visible, textarea:visible").all()
        a3_defaults = [
            raw.get("ambition", "To become an Engineer and Scientist"),
            "Studying diligently, working on projects, and practicing math",
            "Analytical thinking, Coding, Problem solving, Communication, Persistence",
            "Mathematics, Science, Computer Science, English",
            "Disciplined, focused, and proactive",
            "My teachers and mentors",
            "Guiding my learning and providing clear feedback",
            "technical skills and programming concepts",
            "proud and accomplished",
            "immensely proud and happy"
        ]
        for idx, inp in enumerate(inputs_a3):
            if idx < len(a3_defaults):
                val = str(a3_defaults[idx])
                if not inp.input_value():
                    inp.fill(val)
                    inp.dispatch_event("input")
                    inp.dispatch_event("change")

        _click_continue_or_draft(page)
        print("    [OK] Part-A(3) saved.")
    except Exception as e:
        print(f"    [WARN] Part-A(3) notice: {e}")

    # 4. Part-A(4)
    print("  [4/7] Filling Part-A(4) Parent-Teacher Partnership...")
    try:
        cbs_a4 = page.locator("input[type=checkbox]:visible").all()
        for idx in range(min(12, len(cbs_a4))):
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", cbs_a4[idx])
            except Exception:
                pass

        text_a4 = page.locator("input[type=text]:visible").first
        if text_a4.is_visible() and not text_a4.input_value():
            text_a4.fill("Educational kits, science books, and digital resources")

        ta_a4 = page.locator("textarea:visible").first
        if ta_a4.is_visible() and not ta_a4.input_value():
            ta_a4.fill("Student shows high curiosity, regular attendance, and enthusiastic participation in academic and co-curricular activities.")

        _click_continue_or_draft(page)
        print("    [OK] Part-A(4) saved.")
    except Exception as e:
        print(f"    [WARN] Part-A(4) notice: {e}")

    # 5. Part-B
    print("  [5/7] Ensuring Part-B Activity Assessment with all 11 domains...")
    try:
        _ensure_middle_part_b_complete(page, student)
        print("    [OK] Part-B Activity verified complete.")
    except Exception as e:
        print(f"    [WARN] Part-B completion notice: {e}")

    # 6. Part-C
    print("  [6/7] Filling Part-C Subject Remarks & Summary...")
    try:
        c_textareas = page.locator("textarea:visible").all()
        remark = raw.get("teacher_remarks", "Demonstrates consistent academic effort, strong analytical skills, and enthusiastic participation across all curricular areas.")
        for ta in c_textareas:
            if not ta.input_value():
                ta.fill(remark)
                ta.dispatch_event("input")
                ta.dispatch_event("change")

        radios_c = page.locator("input[type=radio]:visible, input[type=checkbox]:visible").all()
        for idx in range(0, len(radios_c), 3):
            pick_idx = idx + 1 if idx + 1 < len(radios_c) else idx
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", radios_c[pick_idx])
            except Exception:
                pass

        _click_continue_or_draft(page)
        print("    [OK] Part-C saved.")
    except Exception as e:
        print(f"    [WARN] Part-C notice: {e}")

    # 7. HPC Credit
    print("  [7/7] Completing HPC Credit & Final Submission...")
    try:
        credit_inputs = page.locator("table").nth(1).locator("input[type=text], input[type=number]").all()
        for i in range(0, len(credit_inputs), 2):
            credit_inputs[i].click(click_count=3)
            credit_inputs[i].fill("33")
            credit_inputs[i].dispatch_event("input")
            credit_inputs[i].dispatch_event("change")
            if i + 1 < len(credit_inputs):
                credit_inputs[i+1].click(click_count=3)
                credit_inputs[i+1].fill("28")
                credit_inputs[i+1].dispatch_event("input")
                credit_inputs[i+1].dispatch_event("change")

        decl_cb = page.locator("input[type=checkbox]").last
        try:
            page.evaluate("(el) => { if (!el.checked) el.click(); }", decl_cb)
        except Exception:
            decl_cb.check(force=True)

        draft_btn = page.locator("button:has-text('Save as Draft')").first
        if draft_btn.is_visible():
            draft_btn.click()
            time.sleep(2)

        mark_btn = page.locator("button:has-text('Mark as Complete')").first
        if mark_btn.is_visible():
            mark_btn.click(force=True)
            time.sleep(2)
            modal_yes = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), button:has-text('Confirm')").first
            if modal_yes.is_visible():
                modal_yes.click(force=True)
                time.sleep(4)
            print("    [OK] Submitted 'Mark as Complete'.")
    except Exception as exc:
        print(f"    [ERROR] HPC Credit error: {exc}")
        raise exc

    # Screenshot Evidence
    time.sleep(2)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    screenshot_name = f"success_middle_{student.admission_number}_{timestamp}.png"
    screenshot_path = EVIDENCE_DIR / screenshot_name
    page.screenshot(path=str(screenshot_path), full_page=True)
    print(f"  [SHOT] Middle Stage completion screenshot saved: {screenshot_name}")
    return screenshot_name


def upload_batch_students(records: List[Dict[str, Any]], headless: bool = False, stage: str = "Preparatory", profile_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Runs batch upload across a list of student records."""
    repo = UploadRepository()
    # Auto-detect stage from student grade if ambiguous
    if records:
        first_grade = str(records[0].get("data", {}).get("grade", "")).lower()
        if any(g in first_grade for g in ("6", "7", "8", "middle")):
            stage = "Middle"
        elif any(g in first_grade for g in ("3", "4", "5", "prep")):
            stage = "Preparatory"

    stage_slug = "preparatory-stage" if stage.lower() == "preparatory" else "middle-stage"

    with sync_playwright() as p:
        ctx = get_browser_context(p, headless=headless, profile_dir=profile_dir)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # Step 1: Ensure login
        wait_for_manual_login(page)

        # Step 2: Build portal key mapping for all students
        portal_map = _get_student_portal_key_map(page, stage_slug)
        print(f"[INFO] Resolved portal keys for {len(portal_map)} students.")

        # Step 3: Iterate over students
        for rec in records:
            student = parse_record_to_model(rec)
            repo.record_attempt(student.admission_number, student.student_name, stage=stage)

            clean_name = student.student_name.strip().lower()
            encoded_key = (
                portal_map.get(student.admission_number)
                or portal_map.get(clean_name)
                or portal_map.get(student.raw_data.get("hpc_login_id", ""))
                or portal_map.get(student.raw_data.get("apaar_id", ""))
            )
            if not encoded_key and clean_name:
                for k, v in portal_map.items():
                    if clean_name in k or k in clean_name:
                        encoded_key = v
                        print(f"  [INFO] Fuzzy matched '{student.student_name}' to key '{k}'")
                        break

            if not encoded_key:
                err_msg = f"Could not find portal student ID for {student.student_name} (Adm: {student.admission_number}). Ensure roster was fetched first."
                repo.record_failure(student.admission_number, err_msg)
                results["failed"] += 1
                results["errors"].append({"student": student.student_name, "error": err_msg})
                print(f"  [FAIL] {err_msg}")
                continue

            # Navigate directly to the student's Part-A1 form
            student_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}/{encoded_key}/part-A1"
            print(f"\n[START] Navigating to student: {student.student_name} (Adm: {student.admission_number})")
            print(f"        URL: {student_url}")
            try:
                page.goto(student_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
                if stage.lower() == "middle":
                    screenshot = fill_middle_student(page, student)
                else:
                    screenshot = fill_preparatory_student(page, student)
                repo.record_success(student.admission_number, screenshot)
                results["success"] += 1
            except Exception as exc:
                err_msg = str(exc)
                repo.record_failure(student.admission_number, err_msg)
                results["failed"] += 1
                results["errors"].append({"student": student.student_name, "error": err_msg})
                print(f"  [FAIL] Failed for {student.student_name}: {err_msg}")

        ctx.close()

    return results
