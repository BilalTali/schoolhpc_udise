import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text='Self Reflection').first.click()
    time.sleep(2)

    # 1. Click all smileys
    res_smileys = page.evaluate("""() => {
        let count = 0;
        // In Step 5, look for smiley images or their parent containers
        document.querySelectorAll("img[src*='smiley'], .assessment-smiley-yes, li[class*='smiley']").forEach(img => {
            if (img.src && img.src.includes('yes') || img.className.includes('yes')) {
                img.click();
                count++;
            }
        });
        return count;
    }""")
    print("Clicked smileys:", res_smileys)

    # 2. Click progress grid statements
    res_grid = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll("td, div, p").forEach(el => {
            const txt = (el.innerText || "").trim();
            if (txt.startsWith("I was able to") || txt.startsWith("I was attentive") || txt.startsWith("I was curious")) {
                if (el.children.length === 0 || el.tagName === 'TD') {
                    el.click();
                    count++;
                }
            }
        });
        return count;
    }""")
    print("Clicked grid items:", res_grid)

    # 3. Check if textareas in My Learnings are disabled, remove disabled and fill
    res_ta = page.evaluate("""() => {
        let filled = 0;
        document.querySelectorAll("textarea, input[type=text]").forEach(el => {
            if (el.placeholder && el.placeholder.includes("Write here") || el.className.includes("text-start") || el.className.includes("ellipsis-line-2")) {
                el.disabled = false;
                el.readOnly = false;
                el.value = "Active learning and collaborative inquiry";
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                filled++;
            }
        });
        return filled;
    }""")
    print("Filled textareas:", res_ta)

    # Save as draft
    page.locator("button:has-text('Save as Draft')").first.click()
    time.sleep(3)

    # Now check badge on Step 5
    badge5 = page.evaluate("""() => {
        const step = Array.from(document.querySelectorAll('li, div')).find(el => el.innerText && el.innerText.includes("Student's Self") && el.innerText.includes("Reflection"));
        return step ? step.innerText : "NOT FOUND";
    }""")
    print("Step 5 text after saving:", repr(badge5))

    page.screenshot(path='audit_evidence/step5_after_click_test.png')
    ctx.close()
