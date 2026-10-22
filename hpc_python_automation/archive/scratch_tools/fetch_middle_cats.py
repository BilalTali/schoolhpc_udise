import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/activity-bank')
    
    js = """
    async () => {
        const s = await (await fetch('/api/auth/session')).json();
        const token = (s && s.user && s.user.access_token) || '';
        const state = (s && s.user && s.user.state_code_internal) || 'jk';
        const ay = (s && s.user && s.user.school_cur_ay_code) || '2627';
        
        const res = await fetch('/api/proxy/hpc/activity-categories/MIDDLE', {
            headers: { 'Authorization': 'Bearer ' + token, 'Accept': 'application/json' }
        });
        const json = await res.json();
        return { session: s, categories: json };
    }
    """
    result = page.evaluate(js)
    with open('data/middle_activity_categories.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    cats = result.get("categories", {}).get("data", []) or []
    print("Categories count:", len(cats))
    for c in cats[:10]:
        print("  Cat:", c)
    ctx.close()
