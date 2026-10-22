import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    page.click("button:has-text('Add Activity')")
    time.sleep(1)
    page.click("text=Pick from Activity Bank")
    time.sleep(0.5)
    page.click("button:has-text('Continue')")
    time.sleep(1.5)
    page.click("text=Global Activities")
    time.sleep(2)

    # Extract all activities in the list
    activities = page.evaluate("""() => {
        const out = [];
        // The items have checkboxes or labels
        document.querySelectorAll("[role=dialog] label, [role=dialog] .custom-checkbox, [role=dialog] li, [role=dialog] [class*='activity']").forEach(el => {
            const txt = el.innerText?.trim();
            if (txt && (txt.includes('CG') || txt.includes('C-') || txt.includes('C '))) {
                if (!out.includes(txt)) out.push(txt.replace(/\\n+/g, ' '));
            }
        });
        return out;
    }""")

    print(f"Total Unique Global Activities Found in DOM: {len(activities)}")
    for a in activities:
        print("  *", a)

    # Save to config/global_activities.json
    with open("config/global_activities.json", "w", encoding="utf-8") as f:
        json.dump(activities, f, indent=2, ensure_ascii=False)
    print("Saved to config/global_activities.json")

    ctx.close()
