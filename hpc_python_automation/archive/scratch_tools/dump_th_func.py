import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    url = 'https://hpc.parakh.ncert.gov.in/_next/static/chunks/app/%5Blocale%5D/(postLogin)/hpc/middle-stage/%5Bid%5D/part-B/page-3163401083b85bc9.js'
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(1)

    content = page.evaluate(f"""async () => {{
        const r = await fetch('{url}');
        return await r.text();
    }}""")

    pos = content.find("tH=")
    if pos != -1:
        print(f"Found tH= at {pos}:")
        print(content[pos: pos + 1200])

    ctx.close()
