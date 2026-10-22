import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:200] if 'json' in r.headers.get('content-type', '') else '') if 'hpc' in r.url else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    def switch_step(txt):
        print(f"\n[Part-B] Switching to step: '{txt}'...")
        page.locator('li').filter(has_text=txt).first.click()
        time.sleep(2)

    def fill_all_visible_inputs(default_text):
        res = page.evaluate(f"""(txt) => {{
            let count = 0;
            document.querySelectorAll('input, textarea').forEach(el => {{
                if (el.offsetParent !== null && !el.disabled && (el.type === 'text' || el.tagName === 'TEXTAREA')) {{
                    if (!el.value || !el.value.trim()) {{
                        el.value = txt;
                        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        count++;
                    }}
                }}
            }});
            return count;
        }}""", default_text)
        print(f"  Filled {res} visible inputs/textareas")

    def click_all_smileys_and_radios():
        res = page.evaluate("""() => {
            let count = 0;
            // 1. Smileys
            document.querySelectorAll("img[src*='smiley_yes'], img[src*='yes'], li.assessment-smiley-yes, .assessment-smiley-yes").forEach(el => {
                el.click();
                count++;
            });
            // 2. Radios
            document.querySelectorAll("input[type=radio]").forEach(r => {
                if (r.offsetParent !== null && !r.checked) {
                    if (r.value === 'proficient' || r.value === '2' || r.value === 'yes' || !r.name.includes('sen')) {
                        r.click();
                        count++;
                    }
                }
            });
            // 3. Statements
            document.querySelectorAll("div, p, span, li").forEach(el => {
                if (el.innerText && el.innerText.startsWith('I was able to') && el.children.length === 0) {
                    el.click();
                    count++;
                }
            });
            return count;
        }""")
        print(f"  Clicked {res} smileys, radios, and statements")

    # Step 3: Activity
    switch_step("Activity")
    fill_all_visible_inputs("Inquiry-based problem solving and hands-on experimentation across domains.")

    # Step 4: Assessment Rubric
    switch_step("Assessment Rubric")
    fill_all_visible_inputs("Consistent conceptual clarity, structured analysis, and active inquiry.")
    click_all_smileys_and_radios()

    # Step 5: Self Reflection
    switch_step("Self Reflection")
    click_all_smileys_and_radios()
    fill_all_visible_inputs("Learned key interdisciplinary concepts and collaborated enthusiastically.")

    # Step 6: Peer Feedback
    switch_step("Peer Feedback")
    # Fill names specifically if empty
    page.evaluate("""() => {
        const inps = document.querySelectorAll('input[type=text]');
        if (inps.length >= 2) {
            if (!inps[0].value) inps[0].value = "ARBAZ IQBAL";
            if (!inps[1].value) inps[1].value = "MOHAMMAD SAHIL";
            inps[0].dispatchEvent(new Event('input', { bubbles: true }));
            inps[1].dispatchEvent(new Event('input', { bubbles: true }));
        }
    }""")
    click_all_smileys_and_radios()
    fill_all_visible_inputs("Strong team player, active listener, and supportive partner during activities.")

    # Save as Draft
    time.sleep(1)
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print("Clicked Save as Draft!")
        time.sleep(3)

    page.screenshot(path='audit_evidence/middle_part_b_perfect_filled.png')

    # Click Finish Activity
    print("\nClicking Finish Activity...")
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)

        # Confirm dialog if any
        modal_btn = page.locator(".modal button, [role=dialog] button").all()
        for b in modal_btn:
            txt = b.inner_text().strip()
            print("  Modal btn:", txt)
            if any(w in txt.lower() for w in ["yes", "confirm", "finish", "ok"]):
                print(f"  Clicking confirm: '{txt}'...")
                b.click()
                time.sleep(4)
                break

    page.screenshot(path='audit_evidence/middle_after_finish_confirmed.png')
    ctx.close()
