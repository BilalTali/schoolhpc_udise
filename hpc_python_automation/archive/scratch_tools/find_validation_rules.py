import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Search in window / loaded scripts for validation function
    res = page.evaluate("""() => {
        const scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
        return scripts.filter(s => s.includes('part-B') || s.includes('chunks/app') || s.includes('chunks/main'));
    }""")
    print("Page scripts:", res)

    # Fetch the part-B chunk and search for validation logic
    for s_url in res:
        if 'part-B' in s_url:
            content = page.evaluate(f"""async () => {{
                const r = await fetch('{s_url}');
                return await r.text();
            }}""")
            print(f"Script {s_url} size: {len(content)}")
            idx = content.find("Please fill out all the mandatory fields")
            if idx != -1:
                print("Found toast string at idx:", idx)
                snippet = content[max(0, idx - 500): min(len(content), idx + 500)]
                print("Snippet around validation:\n", snippet)
            else:
                # search for 'finish' or 'mandatory'
                for term in ['is_complete', 'finish', 'mandatory', 'validate']:
                    t_idx = content.find(term)
                    print(f"Term '{term}' found: {t_idx != -1}")

    ctx.close()
