from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2', wait_until='networkidle')
    
    other_inputs = page.locator("input[type=text]:not([class*='pre-about-me'])").all()
    print(f"Found {len(other_inputs)} non-finger inputs")
    for i, inp in enumerate(other_inputs):
        html = inp.evaluate("el => el.outerHTML")
        parent_html = inp.evaluate("el => el.parentElement.outerHTML")
        val = inp.input_value()
        print(f"Input {i}: val='{val}'\n  outerHTML={html}\n  parent={parent_html}\n")
    ctx.close()
