import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from portal.login import get_browser_context

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-B', wait_until='networkidle')

    def switch_step(name):
        page.evaluate(f'''() => {{
            const ps = Array.from(document.querySelectorAll('p')).filter(p => p.innerText.trim() === '{name}');
            if (ps.length > 0) ps[0].click();
        }}''')
        time.sleep(1)

    # Step 4: Rubrics
    switch_step('Assessment Rubric')
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

    # Step 5: Observational Notes
    switch_step('Observational Notes')
    time.sleep(1)
    tas5 = page.locator('textarea').all()
    print('Step 5 textareas:', len(tas5))
    for ta in tas5:
        if ta.is_visible():
            ta.fill("Exhibits strong engagement in group tasks and connects concepts across subjects.")
    time.sleep(1)

    # Step 6: Self Assessment (Smiley emojis)
    switch_step('Self Assessment')
    time.sleep(1)
    smilies = page.evaluate('''() => {
        const items = document.querySelectorAll('li.assessment-smiley-yes, .assessment-smiley-yes');
        items.forEach(el => el.click());
        return items.length;
    }''')
    print('Clicked smilies:', smilies)
    time.sleep(1)

    # Click Finish Activity
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print('Finish btn visible:', fa_btn.is_visible())
    fa_btn.click()
    time.sleep(2)

    page.screenshot(path='audit_evidence/after_step5_6_finished.png')
    
    # Check dialogs or buttons
    btns = [b.inner_text().strip() for b in page.locator('button').all() if b.is_visible()]
    print('Buttons after finish click:', btns)
    ctx.close()
