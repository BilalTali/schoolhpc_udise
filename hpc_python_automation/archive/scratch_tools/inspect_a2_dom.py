import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A2', wait_until='networkidle')
    time.sleep(2)
    
    elements = page.locator('input[type=text], textarea, input:not([type=checkbox]):not([type=radio])').all()
    print(f"Total elements: {len(elements)}")
    for i, el in enumerate(elements):
        tag = el.evaluate('e => e.tagName')
        cls = el.get_attribute('class') or ''
        ph = el.get_attribute('placeholder') or ''
        val = el.input_value()
        parent_txt = el.evaluate('e => e.parentElement ? e.parentElement.innerText.replace(/\\n/g, " ") : ""')[:70]
        # Also get surrounding text or grandparent
        gp_txt = el.evaluate('e => e.closest("div") ? e.closest("div").innerText.replace(/\\n/g, " ") : ""')[:80]
        print(f"[{i}] <{tag}> ph='{ph}' val='{val}' | parent='{parent_txt}' | box='{gp_txt}'")
    ctx.close()
