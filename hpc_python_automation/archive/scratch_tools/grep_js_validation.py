import re
import urllib.request
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    scripts = []
    page.on('response', lambda r: scripts.append(r.text()) if '.js' in r.url and 'static/chunks' in r.url else None)
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')

    print(f"Captured {len(scripts)} scripts")
    # Search for "mandatory fields" or "Finish Activity"
    for s in scripts:
        matches = [m.start() for m in re.finditer(r'mandatory fields', s, re.IGNORECASE)]
        for idx in matches:
            snippet = s[max(0, idx - 200):min(len(s), idx + 200)]
            print("\n=== JS SNIPPET ===")
            print(snippet)

    ctx.close()
