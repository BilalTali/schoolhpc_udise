from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import time

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    time.sleep(3)
    
    dialogs = []
    page.on('dialog', lambda d: (dialogs.append((d.type, d.message)), print('DIALOG DETECTED:', d.type, d.message), d.accept()))
    
    # Click activity 1 if present
    act_btn = (
        page.query_selector('.already-activity-selected li button') or 
        page.query_selector('.activity-list li button') or
        page.query_selector('button:has-text("Activity")')
    )
    if act_btn:
        print('Found act btn:', act_btn.inner_text())
        act_btn.click()
        time.sleep(1.5)
        
    fin = (
        page.query_selector('button:has-text("Finish Activity")') or
        page.query_selector('button:has-text("Finished")')
    )
    if fin:
        print('Found finish btn:', fin.evaluate('el => el.outerHTML'))
        fin.click()
        time.sleep(2)
        print('After click dialogs:', dialogs)
        page.screenshot(path='audit_evidence/test_dialog_result.png')
    else:
        print('Finish btn not found directly.')
    ctx.close()
