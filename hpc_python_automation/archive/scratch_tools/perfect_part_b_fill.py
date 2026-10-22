import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url[:100], r.text()[:200] if 'json' in r.headers.get('content-type', '') else '') if any(k in r.url for k in ['hpc', 'save', 'complete', 'finish']) else None)

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
    page.evaluate("""() => {
        document.querySelectorAll("input[type=checkbox]").forEach(cb => {
            if (!cb.checked && cb.offsetParent !== null) cb.click();
        });
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
        // 1. Smileys: click all 'yes' smileys
        document.querySelectorAll("img[src*='smiley'], .assessment-smiley-yes, li[class*='smiley']").forEach(img => {
            if ((img.src && img.src.includes('yes')) || (img.className && img.className.includes('yes'))) {
                img.click();
            }
        });
        // 2. Click progress grid statements (all 3 categories)
        document.querySelectorAll("td, div, p").forEach(el => {
            const txt = (el.innerText || "").trim();
            if (txt.startsWith("I was able to") || txt.startsWith("I was attentive") || txt.startsWith("I was curious")) {
                if (el.children.length === 0 || el.tagName === 'TD') {
                    el.click();
                }
            }
        });
        // 3. My Learnings inputs
        document.querySelectorAll("textarea, input[type=text]").forEach(el => {
            if (el.placeholder && el.placeholder.includes("Write here") || el.className.includes("text-start") || el.className.includes("ellipsis-line-2")) {
                el.disabled = false;
                el.readOnly = false;
                el.value = "Active inquiry, hands-on learning, and collaborative problem solving.";
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # 4. Step 6: Peer Feedback
    switch_step("Peer Feedback")
    page.evaluate("""() => {
        const inps = document.querySelectorAll('input[type=text]');
        if (inps.length >= 2) {
            inps[0].disabled = false;
            inps[1].disabled = false;
            if (!inps[0].value) inps[0].value = "ARBAZ IQBAL";
            if (!inps[1].value) inps[1].value = "MOHAMMAD SAHIL";
            inps[0].dispatchEvent(new Event('input', { bubbles: true }));
            inps[1].dispatchEvent(new Event('change', { bubbles: true }));
            inps[1].dispatchEvent(new Event('input', { bubbles: true }));
            inps[1].dispatchEvent(new Event('change', { bubbles: true }));
        }
        document.querySelectorAll("img[src*='smiley'], .assessment-smiley-yes, li[class*='smiley']").forEach(img => {
            if ((img.src && img.src.includes('yes')) || (img.className && img.className.includes('yes'))) {
                img.click();
            }
        });
        document.querySelectorAll("td, div, p").forEach(el => {
            const txt = (el.innerText || "").trim();
            if (txt.startsWith("My peer was able to") || txt.startsWith("Was attentive") || txt.startsWith("Was curious") || txt.startsWith("I was able to")) {
                if (el.children.length === 0 || el.tagName === 'TD') el.click();
            }
        });
        document.querySelectorAll("textarea").forEach(ta => {
            ta.disabled = false;
            if (!ta.value || !ta.value.trim()) {
                ta.value = "Supportive partner, listens actively and explains concepts clearly.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # 5. Step 7: Teacher's Feedback
    switch_step("Teacher's Feedback")
    page.evaluate("""() => {
        // SVG wheel teacher paths
        const paths = document.querySelectorAll('svg path');
        // Click Teacher arcs for awareness, sensitivity, creativity
        [6, 9, 12, 13, 14, 16, 17, 19, 20].forEach(idx => {
            if (paths[idx]) {
                try { paths[idx].dispatchEvent(new MouseEvent('click', { bubbles: true })); } catch(e) {}
            }
        });

        // Habits / Strengths
        ['ast_1', 'ast_2', 'ast_3', 'ast_4', 'ast_5', 'ast_6'].forEach(id => {
            const el = document.getElementById(id) || document.querySelector(`input[name="${id}"]`);
            if (el && !el.checked) el.click();
        });

        // Uncheck 'Any other' checkboxes so text isn't mandatory
        const astAny = document.getElementById('ast_11') || document.querySelector('input[name="ast_11"]');
        if (astAny && astAny.checked) astAny.click();

        const barAny = document.getElementById('bar_10') || document.querySelector('input[name="bar_10"]');
        if (barAny && barAny.checked) barAny.click();

        // Barriers: None
        const b9 = document.getElementById('bar_9') || document.querySelector('input[name="bar_9"]');
        if (b9 && !b9.checked) b9.click();

        // Radios
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked && r.offsetParent !== null) r.click();
        });

        // All textareas in Step 7
        document.querySelectorAll("textarea").forEach(ta => {
            ta.disabled = false;
            if (!ta.value || !ta.value.trim() || ta.value === 'Bdhd') {
                ta.value = "Student shows excellent progress, strong multidisciplinary synthesis, and consistent peer collaboration. Continue providing enriched problem sets and project-based investigations.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });

        // Text inputs in Step 7
        document.querySelectorAll("input[type=text]").forEach(inp => {
            if (inp.offsetParent !== null && !inp.disabled && !inp.value) {
                inp.value = "Consistent engagement";
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")

    # Save as Draft
    time.sleep(2)
    sd = page.locator("button:has-text('Save as Draft')").first
    print("Clicking Save as Draft...")
    sd.click()
    time.sleep(4)

    page.screenshot(path='audit_evidence/perfect_part_b_saved.png')

    # Check Step badges
    badges = page.evaluate("""() => {
        const steps = Array.from(document.querySelectorAll('li, div.step-item')).filter(el => el.innerText && (el.innerText.includes('Reflection') || el.innerText.includes('Feedback')));
        return steps.map(s => s.innerText.replace(/\\n/g, ' '));
    }""")
    print("Step badges after draft save:", badges[:4])

    # Now click Finish Activity!
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Clicking Finish Activity, visible:", fa_btn.is_visible())
    fa_btn.click()
    time.sleep(2)

    page.screenshot(path='audit_evidence/perfect_after_finish_clicked.png')

    # Look for confirm button in modal
    modal_btns = page.locator(".modal button, [role=dialog] button, div.modal-content button, .swal2-confirm, div.modal-footer button").all()
    print(f"Found {len(modal_btns)} modal buttons")
    for b in modal_btns:
        txt = b.inner_text().strip()
        print("  Modal btn:", txt)
        if any(w in txt.lower() for w in ["yes", "confirm", "finish", "ok"]):
            print(f"  --> Clicking modal confirm: '{txt}'")
            b.click()
            time.sleep(4)
            break

    page.screenshot(path='audit_evidence/perfect_after_finish_confirmed.png')

    # Click Continue
    cont = page.locator("button:has-text('Continue')").first
    if cont.is_visible():
        print("Clicking Continue to Part C...")
        cont.click()
        time.sleep(3)
        print("Current URL:", page.url)

    ctx.close()
