import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc-dashboard', wait_until='networkidle')

    # Fetch global activities directly through the authenticated session
    data = page.evaluate("""async () => {
        try {
            const resp = await fetch('https://hpc.parakh.ncert.gov.in/api/proxy/country/activities');
            return await resp.json();
        } catch (e) {
            return { error: e.toString() };
        }
    }""")
    
    print("API RESPONSE TYPE:", type(data))
    if isinstance(data, list):
        print(f"Total Global Activities: {len(data)}")
        for act in data[:10]:
            print(f"ID: {act.get('id')}, Code: {act.get('code')}, Title: {act.get('title') or act.get('name')}, Stage: {act.get('stage')}, Subject: {act.get('subject')}")
        # Save to config/global_activities.json
        with open('config/global_activities.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("Saved to config/global_activities.json")
    elif isinstance(data, dict):
        print("Keys:", list(data.keys()))
        print("Sample:", str(data)[:500])

    ctx.close()
