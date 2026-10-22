import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Click step 7
    s7 = page.locator("li").filter(has_text="Teacher's Feedback").first
    s7.scroll_into_view_if_needed()
    time.sleep(0.5)
    s7.click(force=True)
    time.sleep(2)

    # Inspect wheel segments (SVG paths or polygons or buttons)
    wheel_info = page.evaluate("""() => {
        const svg = document.querySelector('svg');
        const paths = svg ? Array.from(svg.querySelectorAll('path, g, polygon, circle, text')).map(p => ({
            tag: p.tagName,
            id: p.id,
            className: p.className ? (p.className.baseVal || p.className) : '',
            fill: p.getAttribute('fill'),
            stroke: p.getAttribute('stroke'),
            text: p.textContent ? p.textContent.trim() : ''
        })) : [];

        // Checkboxes in step 7
        const cbs = Array.from(document.querySelectorAll('input[type=checkbox], input[type=radio]')).map(c => ({
            type: c.type,
            name: c.name,
            value: c.value,
            checked: c.checked,
            label: c.parentElement ? c.parentElement.innerText.trim() : ''
        }));

        // Textareas
        const tas = Array.from(document.querySelectorAll('textarea')).map(t => ({
            placeholder: t.placeholder,
            value: t.value
        }));

        return { path_count: paths.length, paths: paths.slice(0, 20), cbs: cbs, tas: tas };
    }""")
    print("Wheel info paths count:", wheel_info.get('path_count'))
    print("Checkboxes in step 7:", len(wheel_info.get('cbs', [])))
    for c in wheel_info.get('cbs', []):
        if c.get('label'):
            print("  CB:", c.get('label'))
    print("Textareas in step 7:", len(wheel_info.get('tas', [])))

    ctx.close()
