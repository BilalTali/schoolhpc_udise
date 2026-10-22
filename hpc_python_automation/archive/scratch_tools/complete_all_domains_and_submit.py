import time
from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Navigating to Part-B...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')
        time.sleep(2)

        # Activity 2 should be active. If not, click button 2
        act2 = page.locator(".already-activity-selected ul li button").nth(1)
        if act2.is_visible():
            act2.click()
            time.sleep(1)
        else:
            print("Activity 2 button not found, checking Add Activity...")
            # If Activity 2 wasn't saved, add it now
            page.locator("button:has-text('Add Activity')").first.click()
            time.sleep(1)
            page.locator("text='Pick from Activity Bank'").first.click()
            time.sleep(0.5)
            page.locator(".modal button:has-text('Continue')").first.click()
            time.sleep(1)
            page.locator("text='Global Activities'").first.click()
            time.sleep(1)
            page.locator(".modal input[type=checkbox]").first.click()
            time.sleep(0.5)
            page.locator(".modal button:has-text('Use Activity')").first.click()
            time.sleep(3)

        # ── Step 2: Subject, CG & Competencies (Check all subjects!) ──────────
        print("[2] Navigating to Step 2...")
        page.locator("text='Subject, CG & Competencies'").first.click()
        time.sleep(1)

        dd = page.locator("#partBDomainSelect").first
        if dd.is_visible() and "dropdown-disabled" not in (dd.get_attribute("class") or ""):
            print("Opening Subject dropdown...")
            dd.click()
            time.sleep(1)
            
            # Click all unchecked checkboxes in the dropdown
            labels = page.locator("#partBDomainSelect label").all()
            print(f"Found {len(labels)} subject labels in dropdown")
            for lbl in labels:
                chk = lbl.locator("input[type=checkbox]").first
                if chk.is_visible() and not chk.is_checked():
                    txt = lbl.inner_text().strip()
                    print(f"Checking subject: {txt}")
                    chk.click()
                    time.sleep(0.2)
                    
            # Close dropdown by clicking header or label
            page.locator("label:has-text('Subject(s)')").first.click()
            time.sleep(1)

        # Also select at least one competency checkbox if any are unchecked
        page.evaluate("""() => {
            document.querySelectorAll("input[name='cpt']:not(:checked)").forEach((cb, idx) => {
                if (idx < 5) cb.click();
            });
        }""")
        time.sleep(1)

        # ── Step 3: Activity & Assessment Qs ──────────────────────────────────
        print("[3] Step 3: Activity & Assessment Qs...")
        page.locator("text='Activity & Assessment Qs'").first.click()
        time.sleep(1)
        for ta in page.locator("#scroll_activity_assessment textarea").all():
            if ta.is_visible() and not ta.input_value().strip():
                ta.fill("The learner demonstrated active participation, clear communication, and collaborative teamwork.")
                time.sleep(0.2)

        # ── Step 4: Assessment Rubric ─────────────────────────────────────────
        print("[4] Step 4: Assessment Rubric...")
        page.locator("text='Assessment Rubric'").first.click()
        time.sleep(1)
        page.evaluate("""() => {
            ['awrActive', 'senActive', 'creActive'].forEach(name => {
                const el = document.querySelector(`input[name='${name}'][value='proficient']`);
                if (el) el.click();
            });
        }""")
        time.sleep(1)

        # ── Step 5: Observational Notes ───────────────────────────────────────
        print("[5] Step 5: Observational Notes...")
        page.locator("text='Observational Notes'").first.click()
        time.sleep(1)
        for ta in page.locator("#scroll_teachers_feedback textarea").all():
            if ta.is_visible() and not ta.input_value().strip():
                ta.fill("Consistently engaged and collaborative.")
                time.sleep(0.2)

        # ── Step 6: Self Assessment ───────────────────────────────────────────
        print("[6] Step 6: Self Assessment...")
        page.locator("text='Self Assessment'").first.click()
        time.sleep(1)
        page.evaluate("""() => {
            document.querySelectorAll('li.assessment-smiley-yes').forEach(li => li.click());
        }""")
        time.sleep(1)

        # ── Finish Activity & Modal Confirm ───────────────────────────────────
        print("[7] Clicking Finish Activity...")
        fa = page.locator("button:has-text('Finish Activity')").first
        if fa.is_visible():
            fa.click()
            time.sleep(1)
            
            # Modal confirmation: click "Finish"
            finish_btn = page.locator(".modal button:has-text('Finish')").first
            if finish_btn.is_visible():
                finish_btn.click()
                print("Clicked modal Finish button!")
                time.sleep(2)

        # Save as draft & Continue
        print("[8] Saving Part-B as draft...")
        page.locator(".hpc-inner-action-bar button:has-text('Save as Draft')").first.click()
        time.sleep(2)
        page.screenshot(path='audit_evidence/after_part_b_all_subjects_finished.png')

        print("[9] Clicking Continue from Part-B...")
        page.locator(".hpc-inner-action-bar button:has-text('Continue')").first.click()
        time.sleep(3)

        # If on Part-C, click Continue to advance to HPC Credit
        if "part-C" in page.url:
            print("[10] Advancing past Part-C...")
            page.locator(".hpc-inner-action-bar button:has-text('Continue')").first.click()
            time.sleep(3)

        print("[11] Reached page:", page.url)
        page.screenshot(path='audit_evidence/reached_hpc_credit.png')

        # ── HPC Credit: Fill marks, declaration, Mark as Complete ─────────────
        print("[12] Submitting HPC Credit...")
        inputs = page.locator("table").last.locator("input[type=number], input[type=text]").all()
        visible_inputs = [inp for inp in inputs if inp.is_visible() and inp.is_enabled()]
        print(f"Found {len(visible_inputs)} active inputs on HPC Credit")

        # Fill 12 inputs (6 pairs of 33, 28)
        for i in range(0, len(visible_inputs), 2):
            visible_inputs[i].triple_click()
            visible_inputs[i].fill("33")
            if i + 1 < len(visible_inputs):
                visible_inputs[i+1].triple_click()
                visible_inputs[i+1].fill("28")

        # Check declaration checkbox
        page.evaluate("""() => {
            document.querySelectorAll("input[type='checkbox']").forEach(cb => {
                if (!cb.checked) cb.click();
            });
        }""")
        time.sleep(1)

        # Click Save as Draft
        page.locator("button:has-text('Save as Draft')").first.click()
        time.sleep(2)

        # Click Mark as Complete!
        print("[13] Clicking Mark as Complete...")
        page.locator("button:has-text('Mark as Complete')").first.click()
        time.sleep(2)

        # Confirm modal if any
        modal_btn = page.locator(".modal button:has-text('Yes'), [role=dialog] button:has-text('Yes'), .modal button:has-text('Confirm'), .modal button:has-text('Complete')").first
        if modal_btn.is_visible():
            modal_btn.click()
            print("Clicked confirmation dialog button!")
            time.sleep(3)

        page.screenshot(path='audit_evidence/after_mark_as_complete_v2.png')

        # Check final roster
        print("\n[14] Checking Live Roster status...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage', wait_until='networkidle')
        time.sleep(2)
        page.screenshot(path='audit_evidence/roster_final_verification_v2.png')

        rows = page.locator("table tbody tr").all()
        for r in rows:
            t = r.inner_text().strip().replace('\n', ' | ')
            if 'ARKAN' in t.upper():
                print(f'\n>>> FINAL LIVE ROSTER STATUS: {t} <<<\n')

        ctx.close()

if __name__ == '__main__':
    run()
