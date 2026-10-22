from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2', wait_until='networkidle')
    
    tas = page.locator("textarea").all()
    print(f"Found {len(tas)} textareas")
    for i, ta in enumerate(tas):
        html = ta.evaluate("el => el.outerHTML")
        val = ta.input_value()
        print(f"Textarea {i}: val='{val}'\n  outerHTML={html}\n")
    ctx.close()
