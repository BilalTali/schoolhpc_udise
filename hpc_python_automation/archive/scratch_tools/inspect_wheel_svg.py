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

    # Click Step 7
    s7 = page.locator("li").filter(has_text="Teacher's Feedback").first
    s7.scroll_into_view_if_needed()
    s7.click(force=True)
    time.sleep(2)

    # Inspect the SVG wheel paths
    wheel_paths = page.evaluate("""() => {
        // Find all SVGs
        const svgs = document.querySelectorAll('svg');
        const wheel = Array.from(svgs).find(s => s.querySelectorAll('path').length > 5);
        if (!wheel) return [];
        return Array.from(wheel.querySelectorAll('path, g')).map(p => ({
            id: p.id,
            fill: p.getAttribute('fill'),
            stroke: p.getAttribute('stroke'),
            d: (p.getAttribute('d') || '').slice(0, 30)
        }));
    }""")
    print("Found wheel paths:", len(wheel_paths))
    for p_info in wheel_paths[:10]:
        print("  Path:", p_info)

    # Scroll the right pane down
    page.evaluate("""() => {
        const pane = document.querySelector('.scrolled-outer, div[class*="content"]');
        if (pane) pane.scrollTop = 800;
    }""")
    time.sleep(1)
    page.screenshot(path='audit_evidence/step7_scrolled_pane.png')

    ctx.close()
