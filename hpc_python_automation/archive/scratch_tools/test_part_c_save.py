from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-C', wait_until='domcontentloaded')
    time.sleep(2)
    
    # 1. Check all value=2 checkboxes across all 7 subjects
    js = """() => {
        let count = 0;
        document.querySelectorAll('input[type=checkbox][value="2"]').forEach(cb => {
            if (!cb.checked) {
                cb.click();
                count++;
            }
        });
        return count;
    }"""
    checked_count = page.evaluate(js)
    print(f'Checked {checked_count} checkboxes.')
    time.sleep(1)
    
    # 2. Fill ALL 7 textareas
    tas = page.query_selector_all("textarea")
    print(f"Found {len(tas)} textareas on Part-C.")
    for i, t in enumerate(tas):
        t.fill("Demonstrates commendable conceptual clarity, active teamwork, and consistent inquiry.")
    time.sleep(1)
    
    # 3. Click Continue
    cont = page.query_selector("button:has-text('Continue')")
    if cont:
        print("Clicking Continue on Part-C...")
        cont.click()
        time.sleep(4)
        print("New URL after Part-C Continue:", page.url)
        page.screenshot(path='audit_evidence/test_part_c_success.png', full_page=True)
        
    ctx.close()
