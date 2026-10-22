import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def test_full_middle_automation():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams=" # ARBAZ IQBAL
        base_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}"
        print(f"[START] Testing Middle Stage Automation on student: ARBAZ IQBAL ({slug})")

        # -------------------------------------------------------------
        # 1. Part-A1
        # -------------------------------------------------------------
        print("\n[Step 1/7] Filling Part-A1...")
        page.goto(f"{base_url}/part-A1", wait_until='networkidle')
        time.sleep(2)

        # Grade Radio: Grade 6 = "9", Grade 7 = "10", Grade 8 = "11"
        g6_rad = page.locator("input[type=radio][value='9']").first
        if g6_rad.is_visible() and not g6_rad.is_checked():
            g6_rad.click()

        # Section
        sec_inp = page.locator("input[placeholder*='Section']:not([readonly])").first
        if sec_inp.is_visible():
            sec_inp.fill("A")

        # 12-Month Attendance Grid
        table = page.locator("table").first
        if table.is_visible():
            rows = table.locator("tr").all()
            if len(rows) >= 3:
                w_inputs = rows[1].locator("input:not([readonly])").all()
                for idx, inp in enumerate(w_inputs):
                    if inp.input_value() != "22":
                        inp.click(click_count=3)
                        inp.fill("22")
                        inp.dispatch_event("input")
                        inp.dispatch_event("change")

                p_inputs = rows[2].locator("input:not([readonly])").all()
                for idx, inp in enumerate(p_inputs):
                    if inp.input_value() != "21":
                        inp.click(click_count=3)
                        inp.fill("21")
                        inp.dispatch_event("input")
                        inp.dispatch_event("change")

        # Interests: check at least 3 using evaluate to bypass sticky footer
        interest_cbs = page.locator("input[type=checkbox]").all()
        for idx in range(min(5, len(interest_cbs))):
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", interest_cbs[idx])
            except Exception:
                interest_cbs[idx].check(force=True)

        # Continue to Part-A2
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)
        page.screenshot(path='audit_evidence/middle_auto_step1.png')

        # -------------------------------------------------------------
        # 2. Part-A2: All About Me & Goal Setting
        # -------------------------------------------------------------
        print("\n[Step 2/7] Filling Part-A2...")
        inputs_a2 = page.locator("input:visible, textarea:visible").all()
        a2_defaults = [
            "parents", "home", "reading science books and playing cricket",
            "solve mathematical puzzles", "most times",
            "time management and handwriting", "helping peers in study groups",
            "I complete my assignments on time",
            "ARBAZ IQBAL", "11", # Name & Age
            "Excel in Science and Mathematics",
            "It builds a strong foundation for higher education",
            "Daily revision of concepts", "Regular practice of numericals",
            "It helps develop logical problem-solving skills",
            "Review challenging topics", "Seek teacher guidance",
            "Maintain strong physical health and daily discipline",
            "Morning exercise and yoga", "Read 20 pages daily", "Maintain daily journal",
            "Balanced diet", "Active participation in sports", "Healthy sleep routine",
            "Understanding complex science experiments",
            "I am curious and eager to learn new topics"
        ]
        for idx, inp in enumerate(inputs_a2):
            if idx < len(a2_defaults):
                val = a2_defaults[idx]
                if not inp.input_value():
                    inp.fill(val)
                    inp.dispatch_event("input")
                    inp.dispatch_event("change")

        page.screenshot(path='audit_evidence/middle_auto_step2.png')
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)

        # -------------------------------------------------------------
        # 3. Part-A3: My Ambition Card
        # -------------------------------------------------------------
        print("\n[Step 3/7] Filling Part-A3...")
        inputs_a3 = page.locator("input:visible, textarea:visible").all()
        a3_defaults = [
            "To become an Engineer and Scientist",
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
                val = a3_defaults[idx]
                if not inp.input_value():
                    inp.fill(val)
                    inp.dispatch_event("input")
                    inp.dispatch_event("change")

        page.screenshot(path='audit_evidence/middle_auto_step3.png')
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)

        # -------------------------------------------------------------
        # 4. Part-A4: Parent-Teacher Partnership Card
        # -------------------------------------------------------------
        print("\n[Step 4/7] Filling Part-A4...")
        cbs_a4 = page.locator("input[type=checkbox]:visible").all()
        for idx in range(min(12, len(cbs_a4))):
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", cbs_a4[idx])
            except Exception:
                cbs_a4[idx].check(force=True)

        text_a4 = page.locator("input[type=text]:visible").first
        if text_a4.is_visible() and not text_a4.input_value():
            text_a4.fill("Educational kits and science reference books")

        ta_a4 = page.locator("textarea:visible").first
        if ta_a4.is_visible() and not ta_a4.input_value():
            ta_a4.fill("Student shows high curiosity, regular attendance, and good collaboration with peers.")

        page.screenshot(path='audit_evidence/middle_auto_step4.png')
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)

        # -------------------------------------------------------------
        # 5. Part-B: Activity
        # -------------------------------------------------------------
        print("\n[Step 5/7] Checking Part-B Activity...")
        # Check if Activity already finished or needs finish
        finish_btn = page.locator("button:has-text('Finish Activity')").first
        if finish_btn.is_visible():
            print("  Found Finish Activity button! Finishing activity...")
            finish_btn.click()
            time.sleep(1)
            # Confirm modal if any
            confirm_btn = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), button:has-text('Finish')").last
            if confirm_btn.is_visible():
                confirm_btn.click()
                time.sleep(2)

        page.screenshot(path='audit_evidence/middle_auto_step5.png')
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)

        # -------------------------------------------------------------
        # 6. Part-C: Teacher Remarks & Summary
        # -------------------------------------------------------------
        print("\n[Step 6/7] Filling Part-C...")
        # Fill all textareas
        c_textareas = page.locator("textarea:visible").all()
        print(f"  Filling {len(c_textareas)} subject remark textareas...")
        remark = "Demonstrates consistent academic effort, strong analytical skills, and enthusiastic participation across all curricular areas."
        for ta in c_textareas:
            if not ta.input_value():
                ta.fill(remark)
                ta.dispatch_event("input")
                ta.dispatch_event("change")

        # Select Proficient/Advanced for all radio groups if unselected
        radios_c = page.locator("input[type=radio]:visible, input[type=checkbox]:visible").all()
        for idx in range(0, len(radios_c), 3):
            pick_idx = idx + 1 if idx + 1 < len(radios_c) else idx
            try:
                page.evaluate("(el) => { if (!el.checked) el.click(); }", radios_c[pick_idx])
            except Exception:
                pass

        page.screenshot(path='audit_evidence/middle_auto_step6.png')
        page.locator("button:has-text('Continue')").first.click()
        time.sleep(3)

        # -------------------------------------------------------------
        # 7. HPC Credit: Summative Marks, Declaration & Submission
        # -------------------------------------------------------------
        print("\n[Step 7/7] Completing HPC Credit...")
        credit_inputs = page.locator("table").nth(1).locator("input[type=text], input[type=number]").all()
        print(f"  Found {len(credit_inputs)} marks inputs in table...")
        # 8 subjects: (33 max, 28 got)
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

        # Declaration checkbox
        decl_cb = page.locator("input[type=checkbox]").last
        try:
            page.evaluate("(el) => { if (!el.checked) el.click(); }", decl_cb)
            print("  Checked declaration checkbox!")
        except Exception:
            decl_cb.check(force=True)

        page.screenshot(path='audit_evidence/middle_auto_credit_filled.png')

        # Save as Draft
        draft_btn = page.locator("button:has-text('Save as Draft')").first
        if draft_btn.is_visible():
            draft_btn.click()
            time.sleep(2)
            print("  Saved HPC Credit as draft!")

        # Mark as Complete
        mark_btn = page.locator("button:has-text('Mark as Complete')").first
        if mark_btn.is_visible():
            mark_btn.click()
            time.sleep(2)
            print("  Clicked Mark as Complete!")

            modal_yes = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), button:has-text('Confirm')").first
            if modal_yes.is_visible():
                modal_yes.click()
                print("  Confirmed final submission dialog!")
                time.sleep(3)

        page.screenshot(path='audit_evidence/middle_auto_final_submitted.png')

        # Check Middle Stage Roster
        print("\nChecking Middle Stage Live Roster status...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(3)
        page.screenshot(path='audit_evidence/middle_roster_final.png')

        rows = page.locator("table tbody tr").all()
        for r in rows:
            txt = r.inner_text().strip().replace('\n', ' | ')
            if 'ARBAZ' in txt.upper():
                print(f"\n>>> LIVE STATUS FOR ARBAZ IQBAL: {txt} <<<\n")

        ctx.close()

if __name__ == '__main__':
    test_full_middle_automation()
