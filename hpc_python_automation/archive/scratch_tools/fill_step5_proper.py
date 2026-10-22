import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    step5_li = page.locator('li').filter(has_text='Self Reflection').first
    step5_li.click()
    time.sleep(2)

    # Let's inspect all IMGs on the page
    imgs = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('img')).map(i => ({
            src: i.src,
            className: i.className,
            parentClass: i.parentElement ? i.parentElement.className : '',
            parentTag: i.parentElement ? i.parentElement.tagName : ''
        })).filter(x => x.src.includes('smiley') || x.src.includes('something') || x.src.includes('yes'));
    }""")
    print("Found smileys:", len(imgs), imgs[:5])

    # Click all Yes smileys or first smiley of each group
    clicked_smileys = page.evaluate("""() => {
        // Look for img with yes or class with yes or first li of smiley lists
        let count = 0;
        const smileys = document.querySelectorAll("img[src*='smiley_yes'], img[src*='yes'], li.assessment-smiley-yes, .assessment-smiley-yes");
        smileys.forEach(s => {
            s.click();
            count++;
        });
        return count;
    }""")
    print("Clicked smileys:", clicked_smileys)
    time.sleep(1)

    # Progress grid statements (circle true statements)
    stmt_count = page.evaluate("""() => {
        let count = 0;
        // In Middle Stage, statements are clickable spans/p/divs or have circle class
        const els = document.querySelectorAll("div, p, span, li");
        els.forEach(el => {
            if (el.innerText && el.innerText.startsWith('I was able to') && el.children.length === 0) {
                el.click();
                count++;
            }
        });
        return count;
    }""")
    print("Clicked progress statements:", stmt_count)
    time.sleep(1)

    # Textareas in Step 5
    ta_count = page.evaluate("""() => {
        let count = 0;
        document.querySelectorAll("textarea").forEach(t => {
            if (!t.disabled) {
                t.value = "Learned collaborative scientific inquiry and real-world mathematical applications.";
                t.dispatchEvent(new Event('input', { bubbles: true }));
                t.dispatchEvent(new Event('change', { bubbles: true }));
                count++;
            }
        });
        return count;
    }""")
    print("Filled textareas in Step 5:", ta_count)
    time.sleep(1)

    page.screenshot(path='audit_evidence/step5_after_fill.png')

    # Save as Draft
    sd = page.locator("button:has-text('Save as Draft')").first
    if sd.is_visible():
        sd.click()
        print("Clicked Save as Draft!")
        time.sleep(2)

    page.screenshot(path='audit_evidence/step5_after_draft_save.png')
    ctx.close()
