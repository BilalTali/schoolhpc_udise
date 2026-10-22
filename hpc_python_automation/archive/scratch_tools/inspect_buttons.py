from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import json

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    
    js = """() => {
        const btns = Array.from(document.querySelectorAll('button, a, input[type=button]')).map(b => ({
            tag: b.tagName,
            class: b.className,
            text: b.textContent.trim().replace(/\\s+/g, ' '),
            disabled: b.disabled || b.classList.contains('disabled'),
            outer: b.outerHTML.slice(0, 150)
        }));
        return btns;
    }"""
    buttons = page.evaluate(js)
    for b in buttons:
        print(f"[{b['tag']}] '{b['text']}' class='{b['class']}' disabled={b['disabled']}")
    ctx.close()
