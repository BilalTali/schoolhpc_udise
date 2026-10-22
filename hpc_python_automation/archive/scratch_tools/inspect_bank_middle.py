import requests
import json
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
    time.sleep(3)
    print("Activity Bank URL:", page.url)
    page.screenshot(path='audit_evidence/middle_activity_bank_page.png')

    # Get activities from API directly using page cookies/session
    res = page.evaluate("""async () => {
        const resp = await fetch('/api/proxy/states/jk/hpc/2627/activity-bank?page=1&limit=100&stage=MIDDLE');
        if (resp.ok) return await resp.json();
        const resp2 = await fetch('/api/proxy/states/jk/hpc/2627/activity-bank?page=1&limit=100');
        return await resp2.json();
    }""")
    print("Teacher's Bank Count:", len(res.get('data', {}).get('rows', [])) if isinstance(res.get('data'), dict) else len(res.get('data', [])))
    rows = res.get('data', {}).get('rows', []) if isinstance(res.get('data'), dict) else res.get('data', [])
    for idx, r in enumerate(rows[:20]):
        print(f"  [{idx}]: ID={r.get('id')} | Name={r.get('act_name') or r.get('title')} | Domains={r.get('domain_names') or r.get('subject_names') or r.get('category_names')}")

    ctx.close()
