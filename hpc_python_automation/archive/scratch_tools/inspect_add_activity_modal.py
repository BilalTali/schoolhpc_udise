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
    if not add_btn:
        print("[ERROR] Add Activity button not found!")
        ctx.close()
        exit(1)
        
    print("[1] Clicking + Add Activity...")
    add_btn.click()
    time.sleep(2)
    page.screenshot(path='audit_evidence/modal_step1.png')
    
    # Inspect modal content
    modal_html = page.evaluate('''() => {
        const m = document.querySelector('.modal, [role=dialog], .custom-modal');
        return m ? m.outerHTML.slice(0, 1500) : 'NO MODAL FOUND';
    }''')
    print("[1b] Modal HTML:\n", modal_html[:500])
    
    # Look for Global Activity option
    g_opt = (
        page.query_selector("input[type=radio][value*='global' i]") or
        page.query_selector("label:has-text('Global Activity')") or
        page.query_selector("*:has-text('Global Activity')")
    )
    if g_opt:
        print("[2] Clicking Global Activity option...")
        g_opt.click()
        time.sleep(1)
        
    page.screenshot(path='audit_evidence/modal_step1_selected.png')

    # Look for Continue button in modal
    cont = page.query_selector(".modal button:has-text('Continue'), .modal button:has-text('Next'), button:has-text('Continue')")
    if cont:
        print("[3] Clicking modal Continue...")
        cont.click()
        time.sleep(2)
        
    page.screenshot(path='audit_evidence/modal_step2_list.png')
    
    # Inspect the activity list inside the modal
    list_info = page.evaluate('''() => {
        const m = document.querySelector('.modal, [role=dialog]');
        if (!m) return 'No modal';
        const items = Array.from(m.querySelectorAll('tr, li, .activity-item, .item, input[type=radio]')).map(el => ({
            tag: el.tagName,
            text: el.textContent.trim().replace(/\\s+/g, ' ').slice(0, 80),
            outer: el.outerHTML.slice(0, 150)
        }));
        return items;
    }''')
    print("[4] List items in modal:\n", list_info[:10])
    
    ctx.close()
