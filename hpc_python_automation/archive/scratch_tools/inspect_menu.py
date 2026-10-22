import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage', wait_until='networkidle')
    time.sleep(2)
    
    # Click action button in first row
    btn = page.locator("table tbody tr button").first
    btn.click()
    time.sleep(1)
    
    # Check menu items that appeared
    menu_items = page.locator(".dropdown-menu a, .dropdown-menu button, [role=menu] [role=menuitem]").all()
    for m in menu_items:
        txt = m.inner_text().encode('ascii', 'ignore').decode()
        href = m.get_attribute("href")
        print(f"Menu item: '{txt}', href='{href}'")
        
    ctx.close()
