import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    all_domains = set()
    def on_res(res):
        if 'activities?' in res.url and 'hpc_stage=MIDDLE' in res.url:
            data = res.json()
            records = data.get('data', {}).get('records', [])
            print(f"MIDDLE ACTIVITIES: Found {len(records)} records")
            for idx, r in enumerate(records):
                d_ids = r.get('domain_ids')
                all_domains.update(d_ids)
                print(f"[{idx}] ID={r.get('id')} | Cap={r.get('activity_caption')} | Domains={d_ids}")

    page.on('response', on_res)
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(3)
    print("All domain IDs present in teacher bank:", sorted(list(all_domains)))
    ctx.close()
