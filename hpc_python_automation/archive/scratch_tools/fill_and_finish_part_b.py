import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url[:120], r.text()[:200] if 'json' in r.headers.get('content-type', '') else '') if any(k in r.url for k in ['hpc', 'save', 'complete']) else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    def switch_step(txt):
        print(f"\n[Part-B] Switching to step: '{txt}'...")
        page.locator('li').filter(has_text=txt).first.click()
        time.sleep(2)

    # 1. Step 3: Activity
    switch_step("Activity")
    # Check approach checkboxes if any
    page.evaluate("""() => {
        document.querySelectorAll("input[type=checkbox]").forEach(cb => {
            if (!cb.checked && cb.offsetParent !== null) cb.click();
        });
    }""")
    page.evaluate("""() => {
        document.querySelectorAll("textarea").forEach(ta => {
            if (!ta.disabled && (!ta.value || !ta.value.trim())) {
                ta.value = "Interdisciplinary project with collaborative problem-solving and structured investigations.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # 2. Step 4: Rubric
    switch_step("Assessment Rubric")
    page.evaluate("""() => {
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (r.offsetParent !== null && !r.checked) {
                if (r.value === 'proficient' || r.value === '2' || !r.name.includes('sen')) {
                    r.click();
                }
            }
        });
        document.querySelectorAll("textarea").forEach(ta => {
            if (!ta.disabled && (!ta.value || !ta.value.trim())) {
                ta.value = "Consistently proficient across all multidisciplinary competencies.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # 3. Step 5: Self Reflection
    switch_step("Self Reflection")
    page.evaluate("""() => {
        document.querySelectorAll("img[src*='smiley_yes'], img[src*='yes'], li.assessment-smiley-yes, .assessment-smiley-yes").forEach(el => el.click());
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked && r.offsetParent !== null) r.click();
        });
        document.querySelectorAll("textarea").forEach(ta => {
            if (!ta.value || !ta.value.trim()) {
                ta.value = "Learned and applied new concepts with enthusiasm.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # 4. Step 6: Peer Feedback
    switch_step("Peer Feedback")
    page.evaluate("""() => {
        const inps = document.querySelectorAll('input[type=text]');
        if (inps.length >= 2) {
            if (!inps[0].value) inps[0].value = "ARBAZ IQBAL";
            if (!inps[1].value) inps[1].value = "MOHAMMAD SAHIL";
            inps[0].dispatchEvent(new Event('input', { bubbles: true }));
            inps[1].dispatchEvent(new Event('input', { bubbles: true }));
        }
        document.querySelectorAll("img[src*='smiley_yes'], img[src*='yes'], li.assessment-smiley-yes, .assessment-smiley-yes").forEach(el => el.click());
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked && r.offsetParent !== null) r.click();
        });
        document.querySelectorAll("textarea").forEach(ta => {
            if (!ta.value || !ta.value.trim()) {
                ta.value = "Great partner, communicates clearly and helps peers.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # 5. Step 7: Teacher's Feedback
    switch_step("Teacher's Feedback")
    page.evaluate("""() => {
        // Click SVG wheel paths
        document.querySelectorAll("svg path").forEach(p => {
            try { p.dispatchEvent(new MouseEvent('click', { bubbles: true })); } catch(e) {}
        });
        // Check strengths checkboxes ast_1 to ast_4
        ['ast_1', 'ast_2', 'ast_3', 'ast_4'].forEach(id => {
            const el = document.getElementById(id);
            if (el && !el.checked) el.click();
        });
        // Check barrier none bar_9
        const b9 = document.getElementById('bar_9');
        if (b9 && !b9.checked) b9.click();
        // Radios
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked && r.offsetParent !== null) r.click();
        });
        // Textarea
        document.querySelectorAll("textarea").forEach(ta => {
            if (!ta.disabled && (!ta.value || !ta.value.trim())) {
                ta.value = "Provide advanced conceptual projects, encourage peer tutoring, and maintain consistent regular assessment.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # Save as Draft
    time.sleep(2)
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        print("Clicking Save as Draft...")
        sd.click()
        time.sleep(4)

    page.screenshot(path='audit_evidence/middle_step7_saved.png')

    # Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Finish Activity visible:", fa_btn.is_visible())
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)
        modal_btn = page.locator(".modal button, [role=dialog] button").all()
        for b in modal_btn:
            txt = b.inner_text().strip()
            print("Modal btn:", txt)
            if any(w in txt.lower() for w in ["yes", "confirm", "finish", "ok"]):
                print(f"Clicking confirm: '{txt}'...")
                b.click()
                time.sleep(4)
                break

    page.screenshot(path='audit_evidence/middle_after_finish_clicked.png')

    # Check Continue button
    cont = page.locator("button:has-text('Continue')").first
    print("Continue button visible:", cont.is_visible())
    if cont.is_visible():
        cont.click()
        time.sleep(3)
        print("URL after Continue:", page.url)

    ctx.close()
