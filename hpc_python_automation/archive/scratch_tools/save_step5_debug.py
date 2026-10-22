import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.on('response', lambda r: print('API:', r.status, r.url, r.text()[:250] if 'json' in r.headers.get('content-type', '') else '') if 'hpc' in r.url else None)

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    step5_li = page.locator('li').filter(has_text='Self Reflection').first
    step5_li.click()
    time.sleep(2)

    # 1. Smileys: Click all 4-option green Yes smileys
    res_s = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll("img[src*='smiley_yes'], img[src*='yes'], li.assessment-smiley-yes, .assessment-smiley-yes").forEach(el => {
            el.click();
            count++;
        });
        return count;
    }""")
    print("Clicked smileys:", res_s)

    # 2. Progress grid statements: Click all
    res_st = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll("div, p, span, li").forEach(el => {
            if (el.innerText && el.innerText.startsWith('I was able to') && el.children.length === 0) {
                el.click();
                count++;
            }
        });
        return count;
    }""")
    print("Clicked progress statements:", res_st)

    # 3. Textareas
    res_ta = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll("textarea").forEach(t => {
            if (!t.disabled) {
                t.value = "Participated actively and applied new learning across subjects.";
                t.dispatchEvent(new Event('input', { bubbles: true }));
                t.dispatchEvent(new Event('change', { bubbles: true }));
                count++;
            }
        });
        return count;
    }""")
    print("Filled textareas in Step 5:", res_ta)
    time.sleep(1)

    # Click Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    print("Clicking Save as Draft...")
    sd.click()
    time.sleep(3)

    page.screenshot(path='audit_evidence/middle_step5_saved_draft.png')
    ctx.close()
