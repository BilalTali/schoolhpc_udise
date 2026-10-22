import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    print(f"Navigating to {url}...")
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    def switch_step(txt):
        print(f"\n--- Switching to step: '{txt}' ---")
        page.evaluate(f"""(t) => {{
            const els = Array.from(document.querySelectorAll('div.step-item, div[class*="step"], p, span'));
            const target = els.find(e => e.innerText && e.innerText.trim().includes(t));
            if (target) target.click();
        }}""", txt)
        time.sleep(2)

    def fill_visible_textareas(default_text):
        res = page.evaluate(f"""(txt) => {{
            let filled = 0;
            document.querySelectorAll('textarea').forEach(ta => {{
                if (!ta.disabled && (!ta.value || !ta.value.trim())) {{
                    ta.value = txt;
                    ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filled++;
                }}
            }});
            return filled;
        }}""", default_text)
        print(f"  Filled {res} textareas via evaluate")

    # Step 3: Activity
    switch_step("Activity")
    fill_visible_textareas("Active inquiry, concept discussions, and collaborative experiments.")

    # Step 4: Assessment Rubric
    switch_step("Assessment Rubric")
    fill_visible_textareas("Consistently proficient conceptual understanding and insightful application.")
    page.evaluate("""() => {
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (r.value === 'proficient' || r.value === '2' || !r.checked) {
                r.click();
            }
        });
    }""")

    # Step 5: Student's Self Reflection
    switch_step("Self Reflection")
    fill_visible_textareas("I enjoyed working on the tasks and discovered new connections between subjects.")
    page.evaluate("""() => {
        document.querySelectorAll("li.assessment-smiley-yes, .assessment-smiley-yes, img[src*='yes']").forEach(el => el.click());
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked) r.click();
        });
    }""")

    # Step 6: Peer Feedback
    switch_step("Peer Feedback")
    fill_visible_textareas("Actively shared ideas, listened carefully, and supported team progress.")
    page.evaluate("""() => {
        document.querySelectorAll("li.assessment-smiley-yes, .assessment-smiley-yes, img[src*='yes']").forEach(el => el.click());
        document.querySelectorAll("input[type=radio]").forEach(r => {
            if (!r.checked) r.click();
        });
    }""")

    # Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print("Clicked Save as Draft")
        time.sleep(2)

    # Click Finish Activity
    print("Clicking Finish Activity...")
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    if fa_btn.is_visible():
        fa_btn.click()
        time.sleep(2)

        # Confirm dialog if any
        modal_btn = page.locator(".modal button, [role=dialog] button").all()
        for b in modal_btn:
            print("  Modal btn:", b.inner_text().strip())
            if any(w in b.inner_text().lower() for w in ["yes", "confirm", "finish", "ok"]):
                print("  Clicking confirm in finish modal...")
                b.click()
                time.sleep(3)
                break

    page.screenshot(path='audit_evidence/middle_after_all_steps_finish.png')
    ctx.close()
