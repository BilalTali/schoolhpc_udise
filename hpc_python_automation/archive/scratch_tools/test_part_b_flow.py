from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    time.sleep(3)
    
    # Click Add Activity
    add_btn = page.query_selector("button:has-text('Add Activity')")
    if add_btn:
        print("[1] Clicking Add Activity...")
        add_btn.click()
        time.sleep(2)
        
        # Radio Global Activity
        g_rad = page.query_selector("label:has-text('Global Activity'), input[type=radio][value*='global' i]")
        if g_rad:
            print("[2] Selecting Global Activity...")
            g_rad.click()
            time.sleep(1)
            
        cont_btn = page.query_selector(".modal button:has-text('Continue'), button:has-text('Continue'), button:has-text('Next')")
        if cont_btn:
            print("[3] Clicking Continue in modal...")
            cont_btn.click()
            time.sleep(2)
            
        # Select first activity
        act_row = page.query_selector(".global-activity-list li, table tbody tr, .activity-option, div.global-act-item")
        if act_row:
            print("[4] Selecting activity row...")
            act_row.click()
            time.sleep(1)
            
        conf = page.query_selector("button:has-text('Add'), button:has-text('Confirm'), button:has-text('Select')")
        if conf:
            print("[5] Confirming Add Activity...")
            conf.click()
            time.sleep(3)

    page.screenshot(path='audit_evidence/test_step_after_add.png', full_page=True)
    print("Screenshot: test_step_after_add.png")

    # Click Step 6 directly
    s6 = page.query_selector("button:has-text('Self Assessment'), li:has-text('Self Assessment'), div:has-text('Self Assessment')")
    if s6:
        print("[6] Clicking Step 6 Self Assessment...")
        s6.click()
        time.sleep(2)
        
        # Click all emojis
        clicked = page.evaluate('''() => {
            let count = 0;
            document.querySelectorAll('li.assessment-smiley-yes, .assessment-smiley-yes').forEach(el => {
                el.click();
                count++;
            });
            return count;
        }''')
        print(f"[7] Clicked {clicked} emojis.")
        time.sleep(2)

    # Check Finish Activity button state
    fin = page.query_selector("button:has-text('Finish Activity')")
    if fin:
        disabled = fin.get_attribute("disabled")
        classes = fin.get_attribute("class")
        print(f"[8] Finish Activity button found! disabled={disabled}, class={classes}")
        
        # Click it!
        try:
            fin.click(timeout=5000)
            print("[9] Clicked Finish Activity successfully!")
            time.sleep(3)
        except Exception as e:
            print(f"[ERROR] Clicking Finish Activity: {e}")
            
    page.screenshot(path='audit_evidence/test_step_after_finish_click.png', full_page=True)
    print("Screenshot: test_step_after_finish_click.png")

    # Check Continue button state
    cont = page.query_selector("button:has-text('Continue')")
    if cont:
        print(f"[10] Continue button disabled={cont.get_attribute('disabled')}, class={cont.get_attribute('class')}")
        try:
            cont.click(timeout=5000)
            time.sleep(3)
            print(f"[11] New URL after Continue: {page.url}")
        except Exception as e:
            print(f"[ERROR] Clicking Continue: {e}")

    page.screenshot(path='audit_evidence/test_final_page.png', full_page=True)
    print("Final Screenshot: test_final_page.png")
    ctx.close()
