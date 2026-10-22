import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    page.click("button:has-text('Add Activity')")
    page.click("text=Create Manually")
    page.click("button:has-text('Continue')")
    page.click("text=Subject, CG & Competencies")
    time.sleep(1)

    # Click the dropdown
    page.click(".scroller-cg-domain #partBDomainSelect")
    time.sleep(1)

    # Print the exact HTML of the list container and items
    html = page.evaluate("""() => {
        const list = document.querySelector(".custom-dropdown-list, ul.dropdown-list, .scroller-cg-domain ul");
        return list ? list.outerHTML : "Dropdown list not found";
    }""")
    print("DROPDOWN LIST HTML:")
    print(html[:1500])

    ctx.close()
