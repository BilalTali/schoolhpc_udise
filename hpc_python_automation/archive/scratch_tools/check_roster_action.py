import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage', wait_until='networkidle')
    time.sleep(2)
    
    rows = page.locator("table tbody tr").all()
    print(f"Total table rows: {len(rows)}")
    for i, r in enumerate(rows[:5]):
        text = r.inner_text().replace('\n', ' | ')
        # Check action menu button or links in row
        links = r.locator("a").all()
        hrefs = [a.get_attribute("href") for a in links]
        # Check buttons in row
        btn = r.locator("button").all()
        print(f"Row {i}: text='{text}', hrefs={hrefs}, buttons={len(btn)}")
        
    ctx.close()
