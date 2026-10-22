import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_a2_inputs():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-A2"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        inputs = page.locator("input, textarea").all()
        print(f"Total inputs on Part A2: {len(inputs)}")
        for i, inp in enumerate(inputs):
            tag = inp.evaluate("(el) => el.tagName")
            cls = inp.get_attribute("class") or ""
            ph = inp.get_attribute("placeholder") or ""
            val = inp.input_value()
            lbl = inp.evaluate("""(el) => {
                let p = el.parentElement;
                return p ? p.innerText.trim().replace(/\\n/g, ' ') : '';
            }""")
            print(f"  [{i}] <{tag}> class='{cls}', placeholder='{ph}', val='{val}' | context: {repr(lbl[:60])}")

        ctx.close()

if __name__ == '__main__':
    inspect_a2_inputs()
