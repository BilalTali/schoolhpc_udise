import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    page.click("button:has-text('Add Activity')")
    time.sleep(1)
    page.click("text=Pick from Activity Bank")
    time.sleep(0.5)
    page.click("button:has-text('Continue')")
    time.sleep(1.5)
    page.click("text=Global Activities")
    time.sleep(2)

    # Let's inspect all elements containing "L1CG" or "MCG" or "TWCG"
    data = page.evaluate("""() => {
        const results = [];
        const all = document.querySelectorAll('*');
        all.forEach(el => {
            const t = el.innerText?.trim();
            if (t && (t.startsWith('L1CG') || t.startsWith('MCG') || t.startsWith('TWCG') || t.startsWith('AE') || t.startsWith('PE'))) {
                results.push({
                    text: t,
                    tag: el.tagName,
                    class: el.className,
                    parentTag: el.parentElement?.tagName,
                    parentClass: el.parentElement?.className
                });
            }
        });
        return results;
    }""")
    print("Found matching elements:", len(data))
    for d in data[:20]:
        print(d)

    ctx.close()
