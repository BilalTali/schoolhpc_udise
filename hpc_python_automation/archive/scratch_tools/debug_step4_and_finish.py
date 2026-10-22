import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    # Expand activity card
    page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const act = btns.find(b => b.innerText.includes('TWCG 1') || b.innerText.includes('1'));
        if (act) act.click();
    }''')
    time.sleep(1)

    # Click Step 4 Assessment Rubric
    page.evaluate('''() => {
        const ps = Array.from(document.querySelectorAll('p')).filter(p => p.innerText.trim() === 'Assessment Rubric');
        if (ps.length > 0) ps[0].click();
    }''')
    time.sleep(1.5)

    # Fill Step 4 radios & textareas
    page.evaluate('''() => {
        ['awrActive', 'senActive', 'creActive'].forEach(name => {
            const rad = document.querySelector(`input[type=radio][name='${name}'][value='proficient']`);
            if (rad && !rad.checked) rad.click();
        });
        document.querySelectorAll('textarea').forEach(ta => {
            if (!ta.value) ta.value = "Consistent conceptual understanding, empathy, and collaborative effort.";
        });
    }''')
    time.sleep(1)

    # Click Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print('Finish btn visible:', fa_btn.is_visible())
    fa_btn.click()
    time.sleep(2)

    page.screenshot(path='audit_evidence/after_step4_filled_finish.png')
    
    # Check dialogs or buttons
    btns = [b.inner_text().strip() for b in page.locator('button').all() if b.is_visible()]
    print('Buttons after finish click:', btns)
    ctx.close()
