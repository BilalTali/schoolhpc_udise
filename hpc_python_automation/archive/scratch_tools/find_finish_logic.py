import re
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    chunk_texts = {}
    def on_res(r):
        if '.js' in r.url and 'static/chunks' in r.url:
            try:
                chunk_texts[r.url] = r.text()
            except Exception:
                pass

    page.on('response', on_res)
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')

    for url, text in chunk_texts.items():
        if 'mandatory' in text.lower() or 'finish' in text.lower():
            for m in re.finditer(r'toast\.(error|warn|info)\([^\)]+\)', text):
                print("Toast call:", m.group(0)[:150])
            for m in re.finditer(r'Finish Activity', text, re.IGNORECASE):
                print("Finish Activity snippet:", text[max(0, m.start() - 150):min(len(text), m.start() + 250)])

    ctx.close()
