from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time, json

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    time.sleep(2)
    
    # Click Add Activity
    add_btn = page.query_selector("button:has-text('Add Activity')")
    if add_btn:
        add_btn.click()
        time.sleep(1.5)
        
    # Inspect modal inputs
    info = page.evaluate('''() => {
        const modal = document.querySelector('.modal');
        if (!modal) return 'No modal';
        return Array.from(modal.querySelectorAll('input, label, div')).filter(e => 
            e.textContent.includes('Activity Bank') || e.value?.includes('Activity') || e.type === 'radio'
        ).map(e => ({
            tag: e.tagName,
            type: e.type,
            id: e.id,
            name: e.name,
            value: e.value,
            classes: e.className,
            text: e.textContent.trim(),
            outer: e.outerHTML.slice(0, 150)
        }));
    }''')
    print('MODAL RADIO ELEMENTS:')
    print(json.dumps(info, indent=2))
    
    # Click the second radio button using JS
    clicked_radio = page.evaluate('''() => {
        const radios = document.querySelectorAll('.modal input[type=radio]');
        if (radios.length >= 2) {
            radios[1].checked = true;
            radios[1].dispatchEvent(new Event('change', { bubbles: true }));
            radios[1].click();
            return { clicked: true, id: radios[1].id, val: radios[1].value };
        }
        return { clicked: false, count: radios.length };
    }''')
    print('Clicked radio result:', clicked_radio)
    time.sleep(1)
    page.screenshot(path='audit_evidence/modal_radio_checked.png')
    
    # Click Continue
    cont = page.query_selector(".modal button:has-text('Continue')")
    if cont:
        print('Clicking Continue...')
        cont.click()
        time.sleep(3)
        page.screenshot(path='audit_evidence/modal_after_continue.png', full_page=True)
        
        # Check what appears
        modal_content = page.evaluate('''() => {
            const m = document.querySelector('.modal');
            if (!m) return 'No modal active';
            return {
                title: m.querySelector('.modal-title')?.textContent.trim(),
                bodyText: m.querySelector('.modal-body')?.textContent.trim().replace(/\\s+/g, ' ').slice(0, 500),
                tableRows: Array.from(m.querySelectorAll('tr, .item, li')).map(r => r.textContent.trim().replace(/\\s+/g, ' ').slice(0, 100))
            };
        }''')
        print('MODAL CONTENT AFTER CONTINUE:')
        print(json.dumps(modal_content, indent=2))
        
    ctx.close()
