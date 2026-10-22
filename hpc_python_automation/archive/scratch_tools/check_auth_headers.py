import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    headers_captured = {}
    def on_req(req):
        if '/api/' in req.url:
            print("API URL:", req.url)
            print("Headers:", {k: v for k, v in req.headers.items() if 'auth' in k.lower() or 'token' in k.lower() or 'cookie' in k.lower()})
            headers_captured.update(req.headers)

    page.on('request', on_req)
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
    time.sleep(2)
    
    ls = page.evaluate("() => ({ ...localStorage })")
    print("Local storage keys:", list(ls.keys()))
    for k in ls:
        if any(term in k.lower() for term in ['token', 'auth', 'user', 'jwt', 'bearer', 'key']):
            print(f"Key {k}: {str(ls[k])[:80]}")

    ctx.close()
