import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:200] if 'json' in r.headers.get('content-type', '') else '') if 'hpc' in r.url else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Open Step 7: Teacher's Feedback
    s7 = page.locator("li").filter(has_text="Teacher's Feedback").first
    s7.scroll_into_view_if_needed()
    time.sleep(1)
    s7.click(force=True)
    time.sleep(2)

    # 1. Click SVG wheel segments (paths in svg)
    wheel_clicks = page.evaluate("""() => {
        let count = 0;
        // In the student progress wheel SVG, the segments are clickable paths
        const svg = document.querySelector('svg');
        if (svg) {
            const paths = svg.querySelectorAll('path, g');
            paths.forEach(p => {
                // Click paths that look like segments or have click handlers
                const fill = p.getAttribute('fill') || '';
                if (fill && fill !== 'none' && fill !== '#fff' && fill !== '#ffffff') {
                    p.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                    count++;
                }
            });
        }
        return count;
    }""")
    print("Clicked SVG wheel paths:", wheel_clicks)
    time.sleep(1)

    # 2. Check Positive Habits and Areas of Support checkboxes in Step 7
    cb_clicks = page.evaluate("""() => {
        let count = 0;
        const cbs = document.querySelectorAll("input[type=checkbox]");
        cbs.forEach(cb => {
            const parent = cb.parentElement ? cb.parentElement.innerText : '';
            if (parent.includes('Follow Instructions') || parent.includes('Collaboration') || 
                parent.includes('Responsible') || parent.includes('Creative') || 
                parent.includes('None') || parent.includes('Independent Work')) {
                if (!cb.checked) {
                    cb.click();
                    count++;
                }
            }
        });
        return count;
    }""")
    print("Checked habit/support checkboxes:", cb_clicks)
    time.sleep(1)

    # 3. Fill Teacher's Remarks textarea
    res_ta = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll('textarea').forEach(ta => {
            if (!ta.disabled && (!ta.value || !ta.value.trim())) {
                ta.value = "Student demonstrates strong analytical reasoning, consistent collaboration with peers, and creative application of concepts.";
                ta.dispatchEvent(new Event('input', { bubbles: true }));
                ta.dispatchEvent(new Event('change', { bubbles: true }));
                count++;
            }
        });
        return count;
    }""")
    print("Filled teacher remark textareas:", res_ta)
    time.sleep(1)

    # Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print("Clicked Save as Draft!")
        time.sleep(3)

    page.screenshot(path='audit_evidence/middle_step7_filled_draft.png')

    # Click Finish Activity!
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    if fa_btn.is_visible():
        print("Clicking Finish Activity...")
        fa_btn.click()
        time.sleep(2)

        # Confirm dialog if any
        modals = page.locator(".modal, [role=dialog]").all()
        for m in modals:
            if m.is_visible():
                print("Modal visible:", m.inner_text().replace('\n', ' | '))
                btn = m.locator("button:has-text('Yes'), button:has-text('Confirm'), button:has-text('OK')").first
                if btn.is_visible():
                    print("Clicking modal confirm...")
                    btn.click()
                    time.sleep(4)
                    break

    page.screenshot(path='audit_evidence/middle_step7_after_finish.png')
    ctx.close()
