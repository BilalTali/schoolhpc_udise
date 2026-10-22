import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    page.locator('li').filter(has_text='Self Reflection').first.click()
    time.sleep(2)

    # Let's inspect the badge itself: what HTML element is 10?
    badge = page.evaluate("""() => {
        const li = Array.from(document.querySelectorAll('li')).find(l => l.innerText && l.innerText.includes('Self Reflection'));
        return li ? li.innerHTML : 'No li';
    }""")
    print("Badge HTML:", badge)

    # Let's scroll through the entire right pane and print all text
    right_text = page.evaluate("""() => {
        const divs = document.querySelectorAll('div, p, label');
        const lines = [];
        divs.forEach(d => {
            if (d.children.length === 0 && d.innerText && d.innerText.trim()) {
                lines.push(d.innerText.trim());
            }
        });
        return lines;
    }""")
    print(f"Total lines in Step 5: {len(right_text)}")
    for line in right_text:
        if any(w in line for w in ['*', 'Reflection', 'Progress', 'Awareness', 'Sensitivity', 'Creativity', 'Learnings', 'Practice', 'Help', 'circle', 'Mandatory']):
            print("  Line:", line)

    ctx.close()
