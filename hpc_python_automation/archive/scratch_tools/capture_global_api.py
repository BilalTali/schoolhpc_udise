import time
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()

    captured_responses = []

    def on_response(response):
        if "activities" in response.url.lower():
            try:
                body = response.json()
                captured_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "data": body
                })
            except Exception:
                pass

    page.on("response", on_response)

    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDA5LTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    page.click("button:has-text('Add Activity')")
    time.sleep(1)
    page.click("text=Pick from Activity Bank")
    time.sleep(0.5)
    page.click("button:has-text('Continue')")
    time.sleep(1.5)
    page.click("text=Global Activities")
    time.sleep(3)

    print(f"Captured {len(captured_responses)} activity responses.")
    for cr in captured_responses:
        print("URL:", cr["url"], "Status:", cr["status"])
        data = cr["data"]
        # Save if this contains activities list
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            items = data["data"]
            print(f"  Found {len(items)} items in data['data']!")
            with open("config/global_activities.json", "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
            print("  [OK] Saved to config/global_activities.json")
            for item in items[:5]:
                print("   -", item.get("name") or item.get("title") or item.get("code") or item)
        elif isinstance(data, list):
            print(f"  Found {len(data)} items directly in list!")
            with open("config/global_activities.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("  [OK] Saved to config/global_activities.json")

    ctx.close()
