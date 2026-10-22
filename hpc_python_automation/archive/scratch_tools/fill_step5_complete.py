import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Click Step 5
    s5 = page.locator("li").filter(has_text="Self Reflection").first
    s5.click()
    time.sleep(2)

    # 1. Circle smileys (click all Yes smileys)
    page.evaluate("""() => {
        document.querySelectorAll("img[src*='smiley_yes'], img[src*='yes']").forEach(img => img.click());
    }""")
    time.sleep(1)

    # 2. Circle statements in progress grid
    grid_clicked = page.evaluate("""() => {
        let count = 0;
        // In Middle Stage, statements are in table or grid cells
        const cells = document.querySelectorAll('div, td, th, p, span');
        cells.forEach(c => {
            if (c.innerText && (c.innerText.includes('I was able to') || c.innerText.includes('I was curious'))) {
                if (c.children.length === 0 || c.tagName === 'TD' || c.tagName === 'DIV') {
                    c.click();
                    count++;
                }
            }
        });
        return count;
    }""")
    print("Clicked progress grid cells:", grid_clicked)
    time.sleep(1)

    # 3. Fill the 4 inputs in My Learnings
    # Scroll down to see them
    page.evaluate("""() => {
        const pane = document.querySelector('.activation-tab-content');
        if (pane) pane.scrollTop = 1000;
    }""")
    time.sleep(1)

    # Fill textareas and inputs in Step 5
    tas = page.locator(".activation-tab-content textarea:visible, textarea:visible").all()
    print("Visible textareas in Step 5:", len(tas))
    for t in tas:
        if not t.input_value():
            t.fill("Learned key concepts and applied practical problem-solving methods.")

    inps = page.locator(".activation-tab-content input[type=text]:visible, input[type=text]:visible").all()
    print("Visible text inputs in Step 5:", len(inps))
    for i in inps:
        if not i.input_value():
            i.fill("Hands-on experiments and team collaboration.")

    # Save as Draft
    time.sleep(1)
    sd = page.locator("button:has-text('Save as Draft')").first
    sd.click()
    print("Clicked Save as Draft!")
    time.sleep(3)

    page.screenshot(path='audit_evidence/step5_completely_filled.png')
    ctx.close()
