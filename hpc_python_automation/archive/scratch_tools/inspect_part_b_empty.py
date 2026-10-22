import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Let's see which sub-steps have red error badges or incomplete status
    step_items = page.evaluate("""() => {
        const lis = document.querySelectorAll('div.activity-tab-lists li, ul.stepper li, .stepper li, div[class*="step-item"]');
        return Array.from(lis).map(l => ({
            text: l.innerText.replace(/\\n/g, ' '),
            badge: l.querySelector('span[class*="badge"], div[class*="badge"], .count')?.innerText || ''
        }));
    }""")
    print("Steps and badges:", step_items)

    # Inspect Step 5 in detail
    page.locator('li').filter(has_text='Self Reflection').first.click()
    time.sleep(2)

    # Inspect empty inputs in Step 5
    empty_fields = page.evaluate("""() => {
        const empty = [];
        document.querySelectorAll('input, textarea, select').forEach(el => {
            if (el.offsetParent !== null) { // visible
                if ((el.type === 'text' || el.tagName === 'TEXTAREA') && !el.value.trim()) {
                    empty.push({ tag: el.tagName, placeholder: el.placeholder, name: el.name, id: el.id });
                }
            }
        });
        return empty;
    }""")
    print("Empty visible text inputs/textareas:", len(empty_fields), empty_fields)

    # Check unselected radio groups or smileys in Step 5
    radio_groups = page.evaluate("""() => {
        const groups = {};
        document.querySelectorAll("input[type=radio]").forEach(r => {
            groups[r.name] = groups[r.name] || { total: 0, checked: 0 };
            groups[r.name].total++;
            if (r.checked) groups[r.name].checked++;
        });
        return groups;
    }""")
    print("Radio groups:", radio_groups)

    ctx.close()
