import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    def on_res(res):
        if 'country/activities' in res.url and 'MIDDLE' in res.url:
            data = res.json()
            records = data.get('data', {}).get('records', [])
            print(f"COUNTRY MIDDLE ACTIVITIES: {len(records)}")
            with open('data/country_middle_activities.json', 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2)

    page.on('response', on_res)
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(1)

    btn = page.locator("button[title*='Global'], button:has-text('Import from Global')").first
    btn.click()
    time.sleep(3)
    ctx.close()
