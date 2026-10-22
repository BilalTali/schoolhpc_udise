import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(1)

    with page.expect_response(lambda r: 'country/activities' in r.url and 'MIDDLE' in r.url) as response_info:
        btn = page.locator("button[title*='Global'], button:has-text('Import from Global')").first
        btn.click()

    response = response_info.value
    data = response.json()
    records = data.get('data', {}).get('records', [])
    print(f"Captured {len(records)} country middle activities!")
    with open('data/country_middle_activities.json', 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2)

    # Let's inspect domains represented in the country activities
    domains = {}
    for r in records:
        for d in r.get('domain_ids', []):
            domains[d] = domains.get(d, 0) + 1
    print("Domains in country activities:", domains)

    ctx.close()
