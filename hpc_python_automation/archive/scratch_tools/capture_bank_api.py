import sys
import time
import json
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def capture_global_activities_api():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_response(res):
            if "activity" in res.url.lower():
                print(f"API: {res.status} {res.url}")
                try:
                    if "json" in res.headers.get("content-type", ""):
                        data = res.json()
                        print(f"  Response JSON keys/len: {len(data) if isinstance(data, list) else data.keys() if isinstance(data, dict) else type(data)}")
                except:
                    pass

        page.on("response", on_response)

        page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank', wait_until='networkidle')
        time.sleep(2)

        # Click the 2nd button (Global Activity Bank)
        top_btns = page.locator(".content-header button, div.d-flex button, div:has-text('My Activity Bank') button").all()
        top_btns[1].click()
        time.sleep(2)

        modal = page.locator(".modal, [role=dialog], div[class*='modal']").first
        # Switch to Middle
        stage_dd = modal.locator(".custom-dropdown-header:has-text('Foundational')").first
        if stage_dd.is_visible():
            stage_dd.click()
            time.sleep(1)
            opt = page.locator(".custom-dropdown-item:has-text('Middle')").first
            if opt.is_visible():
                opt.click()
                time.sleep(3)

        ctx.close()

if __name__ == '__main__':
    capture_global_activities_api()
