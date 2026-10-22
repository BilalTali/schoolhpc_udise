from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time, json

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    time.sleep(2)
    
    # 1. Click Add Activity
    add_btn = page.query_selector("button:has-text('Add Activity')")
    if add_btn:
        add_btn.click()
        time.sleep(1.5)
        
    # 2. Click radio 2: "Pick from Activity Bank"
    page.evaluate('''() => {
        const radios = document.querySelectorAll('.modal input[type=radio]');
        if (radios.length >= 2) {
            radios[1].checked = true;
            radios[1].dispatchEvent(new Event('change', { bubbles: true }));
            radios[1].click();
        }
    }''')
    time.sleep(1)
    
    # 3. Click Continue
    cont = page.query_selector(".modal button:has-text('Continue')")
    if cont:
        cont.click()
        time.sleep(2)
        
    # 4. Click "Global Activities" tab
    glob_tab = page.query_selector("button:has-text('Global Activities'), a:has-text('Global Activities'), li:has-text('Global Activities'), span:has-text('Global Activities'), *:has-text('Global Activities')")
    print("Clicking Global Activities tab...")
    page.evaluate('''() => {
        const els = Array.from(document.querySelectorAll('*')).filter(e => e.textContent.trim() === 'Global Activities');
        if (els.length > 0) {
            els[els.length - 1].click();
        }
    }''')
    time.sleep(3)
    page.screenshot(path='audit_evidence/modal_global_activities_tab.png', full_page=True)
    
    # Inspect the loaded activities
    activities = page.evaluate('''() => {
        const rows = document.querySelectorAll('.modal table tbody tr, .modal .table tbody tr, .modal [role=row]');
        return Array.from(rows).map((r, i) => ({
            index: i + 1,
            text: r.textContent.trim().replace(/\\s+/g, ' ').slice(0, 120),
            hasRadio: !!r.querySelector('input[type=radio]'),
            outer: r.outerHTML.slice(0, 150)
        }));
    }''')
    print(f"Found {len(activities)} Global Activities:")
    for a in activities[:10]:
        print("  ", a)
        
    ctx.close()
