import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Click Add Activity
    page.click("button:has-text('Add Activity')")
    time.sleep(1)

    # Pick from Activity Bank
    page.click("text=Pick from Activity Bank")
    time.sleep(0.5)
    page.click("button:has-text('Continue')")
    time.sleep(1.5)

    # Click Global Activities tab
    page.click("text=Global Activities")
    time.sleep(1.5)

    # Let's inspect the checkboxes and labels in Global Activities
    items = page.evaluate("""() => {
        const list = [];
        document.querySelectorAll("[role=dialog] label, [role=dialog] input[type=checkbox]").forEach(el => {
            const txt = el.innerText || el.labels?.[0]?.innerText || el.value || '';
            if (txt) list.push(txt.trim().replace(/\\n+/g, ' '));
        });
        return list;
    }""")
    print("GLOBAL ACTIVITIES LIST (sample):", items[:15])

    # Select the first global activity or L1CG1, C-1.2
    target_cb = (
        page.query_selector("label:has-text('L1CG1 , C-1.2') input, label:has-text('L1CG 1, C 1.2') input") or
        page.query_selector("[role=dialog] input[type=checkbox]")
    )
    if target_cb:
        target_cb.check()
        time.sleep(1)
        print("Checked a global activity!")
        
        # Click Use Activity button
        use_btn = page.query_selector("button:has-text('Use Activity')")
        if use_btn:
            print("Use Activity enabled?", not use_btn.is_disabled())
            use_btn.click()
            time.sleep(2)
            page.screenshot(path='after_picking_global_activity.png')
            
            # Read new card state
            card_info = page.evaluate("""() => {
                return {
                    textSnippet: document.querySelector('.page-dashboard, .hpc-forms')?.innerText?.slice(0, 800),
                    activityName: document.querySelector("input[placeholder*='Activity Name'], input[name*='activity']")?.value,
                    subjectField: document.querySelector(".scroller-cg-domain, #partBDomainSelect")?.innerText
                };
            }""")
            print("\nCARD AFTER USE ACTIVITY:")
            print("Activity Name:", card_info["activityName"])
            print("Subject/Domain:", card_info["subjectField"])

    ctx.close()
