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

    # Find all occurrences of is_complete and Finish Activity
    indices = []
    start = 0
    while True:
        pos = content.find("is_complete", start)
        if pos == -1:
            break
        indices.append(pos)
        start = pos + len("is_complete")

    print(f"Found {len(indices)} occurrences of is_complete")
    for i, idx in enumerate(indices):
        print(f"\n--- Occurrence {i} at {idx} ---")
        print(content[max(0, idx - 400): min(len(content), idx + 400)])

    ctx.close()
