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

    # Click step 7
    s7 = page.locator("li").filter(has_text="Teacher's Feedback").first
    s7.scroll_into_view_if_needed()
    time.sleep(1)
    s7.click(force=True)
    time.sleep(2)

    # Find the wheel container and inspect all SVGs and clickable elements inside it
    info = page.evaluate("""() => {
        // Find element containing "Student Progress Wheel"
        const wheelHeading = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, div, p')).find(e => e.innerText && e.innerText.includes('Student Progress Wheel'));
        const container = wheelHeading ? wheelHeading.parentElement : document.body;
        
        const svgs = Array.from(container.querySelectorAll('svg')).map(s => ({
            tag: s.tagName,
            cls: s.className ? s.className.baseVal : '',
            paths: s.querySelectorAll('path').length
        }));

        const inputs = Array.from(container.querySelectorAll('input, textarea')).map(i => ({
            tag: i.tagName,
            type: i.type,
            name: i.name,
            placeholder: i.placeholder,
            parent: i.parentElement ? i.parentElement.innerText.slice(0, 40) : ''
        }));

        return { svgs, inputs };
    }""")
    print("Wheel container info:", info)

    # Let's scroll down to see the rest of Step 7
    page.evaluate("() => window.scrollBy(0, 800)")
    time.sleep(1)
    page.screenshot(path='audit_evidence/middle_step7_scrolled.png')

    ctx.close()
