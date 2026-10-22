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

    # Let's inspect what elements exist in the right pane
    info = page.evaluate("""() => {
        const pane = document.querySelector('div.scrolled-outer, div.outer-white, .step-content');
        if (!pane) return { error: 'No pane' };

        // 1. Smileys
        const smileys = Array.from(pane.querySelectorAll('img, svg, li, div')).filter(e => {
            const src = e.getAttribute('src') || '';
            const cls = e.className || '';
            return src.includes('smiley') || cls.includes('smiley') || src.includes('yes');
        }).map(e => ({ tag: e.tagName, cls: e.className, src: e.getAttribute('src') }));

        // 2. Progress grid clickable statements
        const statements = Array.from(pane.querySelectorAll('p, span, div, li')).filter(e => {
            return e.innerText && e.innerText.includes('I was able to');
        }).map(e => ({ tag: e.tagName, cls: e.className, text: e.innerText.trim() }));

        // 3. Textareas
        const textareas = Array.from(pane.querySelectorAll('textarea')).map(t => ({
            placeholder: t.placeholder,
            value: t.value
        }));

        return { smileys: smileys.length, statements: statements.length, textareas: textareas.length, sample_stmt: statements.slice(0, 3) };
    }""")
    print("Step 5 inspection:", info)

    ctx.close()
