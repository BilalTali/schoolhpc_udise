import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text="Teacher's Feedback").first.click()
    time.sleep(2)

    # Inspect all SVG elements, radios, checkboxes, textareas
    svg_info = page.evaluate("""() => {
        const paths = Array.from(document.querySelectorAll('svg path'));
        return paths.map((p, idx) => ({
            idx,
            fill: p.getAttribute('fill'),
            stroke: p.getAttribute('stroke'),
            d: p.getAttribute('d') ? p.getAttribute('d').substring(0, 30) : '',
            classes: p.className ? p.className.baseVal : ''
        }));
    }""")
    print(f"SVG paths count: {len(svg_info)}")
    for p_item in svg_info:
        print(" ", p_item)

    # Check all mandatory stars or red text in Step 7
    stars = page.evaluate("""() => {
        const redEls = Array.from(document.querySelectorAll('*')).filter(el => {
            const txt = (el.innerText || "").trim();
            return (txt.includes('*') || txt.includes('required') || txt.includes('Please select')) && el.children.length === 0;
        });
        return redEls.map(el => el.innerText.trim());
    }""")
    print("Mandatory/star labels in Step 7:", set(stars))

    # Check the text on step 7 button/tab
    step7_tab = page.evaluate("""() => {
        const step = Array.from(document.querySelectorAll('li, div')).find(el => el.innerText && el.innerText.includes("Teacher's Feedback"));
        return step ? step.innerText : "NOT FOUND";
    }""")
    print("Step 7 tab text:", repr(step7_tab))

    ctx.close()
