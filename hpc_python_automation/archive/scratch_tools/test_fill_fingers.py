import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2', wait_until='networkidle')
    time.sleep(2)
    
    # Finger values from Excel:
    finger_vals = [
        "Kindness",
        "Patience",
        "Mental Math",
        "Teamwork",
        "Creative Art"
    ]
    
    for i, val in enumerate(finger_vals):
        finger_inp = page.locator(f"input.pre-about-me-{i}").first
        if finger_inp.is_visible():
            print(f"Clicking finger {i}...")
            finger_inp.click()
            time.sleep(0.5)
            
            # The popup has an input and an Ok button
            pop_inp = page.locator("div.popover input, div:has(> button:has-text('Ok')) input").first
            if pop_inp.is_visible():
                pop_inp.fill(val)
                time.sleep(0.2)
                ok_btn = page.locator("button:has-text('Ok')").first
                if ok_btn.is_visible():
                    ok_btn.click()
                    time.sleep(0.5)
                    print(f"Finger {i} filled with '{val}', current value: '{finger_inp.input_value()}'")
                    
    page.screenshot(path='audit_evidence/after_hand_filled.png')
    ctx.close()
