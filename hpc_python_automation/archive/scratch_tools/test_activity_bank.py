from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    time.sleep(3)
    
    # 1. Click Add Activity
    add_btn = page.query_selector("button:has-text('Add Activity')")
    if add_btn:
        print("[1] Clicking + Add Activity...")
        add_btn.click()
        time.sleep(1.5)
        
        # 2. Click "Pick from Activity Bank"
        pick_btn = page.query_selector("label:has-text('Pick from Activity Bank'), *:has-text('Pick from Activity Bank')")
        if pick_btn:
            print("[2] Clicking Pick from Activity Bank...")
            pick_btn.click()
            time.sleep(1)
            
        page.screenshot(path='audit_evidence/activity_bank_step1.png')
        
        # 3. Click Continue
        cont = page.query_selector(".modal button:has-text('Continue')")
        if cont:
            print("[3] Clicking modal Continue...")
            cont.click()
            time.sleep(3)
            
        page.screenshot(path='audit_evidence/activity_bank_step2.png')
        
        # Print modal / page elements
        items = page.evaluate('''() => {
            return Array.from(document.querySelectorAll('.modal tr, .modal li, .modal .card, .modal [role=row], .modal button')).map(el => ({
                tag: el.tagName,
                text: el.textContent.trim().replace(/\\s+/g, ' ').slice(0, 100),
                classes: el.className
            }));
        }''')
        print(f"[4] Found {len(items)} elements in Activity Bank:")
        for it in items[:15]:
            print("  ", it)
            
    ctx.close()
