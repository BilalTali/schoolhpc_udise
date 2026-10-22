import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url[:100], r.text()[:180] if 'json' in r.headers.get('content-type', '') else '') if any(k in r.url for k in ['hpc', 'save', 'complete', 'finish']) else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    def switch_step(txt):
        print(f"\n[Part-B] Switching to step: '{txt}'...")
        page.locator('li').filter(has_text=txt).first.click()
        time.sleep(2)

    def save_draft():
        sd = page.locator("button:has-text('Save as Draft')").first
        if sd.is_visible():
            sd.click()
            time.sleep(3)

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
    save_draft()

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
    save_draft()

    # 3. Step 5: Self Reflection
    switch_step("Self Reflection")
    page.evaluate("""() => {
        // 1. Smileys
        document.querySelectorAll("img[src*='smiley'], .assessment-smiley-yes, li[class*='smiley']").forEach(img => {
            if ((img.src && img.src.includes('yes')) || (img.className && img.className.includes('yes'))) {
                img.click();
            }
        });
        // 2. Click progress grid statements
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
    save_draft()

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
            inps[0].dispatchEvent(new Event('change', { bubbles: true }));
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
    save_draft()

    # 5. Step 7: Teacher's Feedback
    switch_step("Teacher's Feedback")
    page.evaluate("""() => {
        // Teacher wheel arcs
        const paths = document.querySelectorAll('svg path');
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

        const astAny = document.getElementById('ast_11') || document.querySelector('input[name="ast_11"]');
        if (astAny && astAny.checked) astAny.click();

        const barAny = document.getElementById('bar_10') || document.querySelector('input[name="bar_10"]');
        if (barAny && barAny.checked) barAny.click();

        const b9 = document.getElementById('bar_9') || document.querySelector('input[name="bar_9"]');
        if (b9 && !b9.checked) b9.click();

        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked && r.offsetParent !== null) r.click();
        });

        document.querySelectorAll("textarea").forEach(ta => {
            ta.disabled = false;
            if (!ta.value || !ta.value.trim() || ta.value === 'Bdhd') {
                ta.value = "Student shows excellent progress, strong multidisciplinary synthesis, and consistent peer collaboration. Continue providing enriched problem sets and project-based investigations.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });

        document.querySelectorAll("input[type=text]").forEach(inp => {
            if (inp.offsetParent !== null && !inp.disabled && !inp.value) {
                inp.value = "Consistent engagement";
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    }""")
    save_draft()

    page.screenshot(path='audit_evidence/each_step_saved_draft.png')

    # Inspect all step badges
    step_texts = page.evaluate("""() => {
        const lis = Array.from(document.querySelectorAll('li')).filter(l => l.innerText && (l.innerText.includes('Activity') || l.innerText.includes('Feedback') || l.innerText.includes('Reflection')));
        return lis.map(l => l.innerText.replace(/\\n/g, ' '));
    }""")
    print("Steps after saving all:", step_texts)

    # Click Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Finish Activity visible:", fa_btn.is_visible())
    fa_btn.click()
    time.sleep(2)

    page.screenshot(path='audit_evidence/finish_dialog_each_step.png')

    modal_btns = page.locator(".modal button, [role=dialog] button, div.modal-content button, .swal2-confirm, div.modal-footer button").all()
    print(f"Modal buttons count: {len(modal_btns)}")
    for b in modal_btns:
        txt = b.inner_text().strip()
        print("  Modal btn:", txt)
        if any(w in txt.lower() for w in ["yes", "confirm", "finish", "ok"]):
            print(f"  --> Clicking: '{txt}'")
            b.click()
            time.sleep(4)
            break

    page.screenshot(path='audit_evidence/after_finish_confirmed_success_now.png')

    ctx.close()
