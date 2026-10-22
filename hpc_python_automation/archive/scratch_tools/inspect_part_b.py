from playwright.sync_api import sync_playwright
from portal.login import get_browser_context
import json

with sync_playwright() as p:
    ctx = get_browser_context(p, headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/142407/part-B', wait_until='domcontentloaded')
    
    js = """() => {
        return Array.from(document.querySelectorAll('button')).map(b => ({
            text: b.textContent.trim().replace(/\\s+/g, ' '),
            disabled: b.disabled || b.classList.contains('disabled'),
            classes: b.className,
            visible: b.offsetParent !== null,
            outer: b.outerHTML.slice(0, 150)
        })).filter(b => b.text.includes('Continue') || b.text.includes('Next') || b.text.includes('Finish'));
    }"""
    print(json.dumps(page.evaluate(js), indent=2))
    ctx.close()
