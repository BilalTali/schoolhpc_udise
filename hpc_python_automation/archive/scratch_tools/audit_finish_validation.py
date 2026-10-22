import sys
import time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    slug = "MTQ0OTcyLTI2Mjctams="
    url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/part-B"
    page.goto(url, wait_until='networkidle')
    time.sleep(2)

    # Let's inspect all elements with red outline or :invalid or mandatory asterisks
    validation_state = page.evaluate("""() => {
        const issues = [];
        // Check all inputs and textareas
        document.querySelectorAll('input, textarea, select').forEach(el => {
            if (el.required && !el.value) {
                issues.push({ type: 'required_empty', tag: el.tagName, name: el.name, placeholder: el.placeholder });
            }
        });
        // Check react error messages
        document.querySelectorAll('.error-message, .invalid-feedback, .text-danger, span[class*="error"]').forEach(el => {
            if (el.innerText.trim()) issues.push({ type: 'error_text', text: el.innerText.trim() });
        });
        return issues;
    }""")
    print("Initial validation issues:", validation_state)

    # Let's see what happens when clicking Finish Activity: what changes in the DOM?
    fa_btn = page.locator("button:has-text('Finish Activity')").first
    print("Clicking Finish Activity...")
    fa_btn.click()
    time.sleep(1)

    after_click_issues = page.evaluate("""() => {
        const issues = [];
        document.querySelectorAll('.is-invalid, .has-error, .error, [aria-invalid="true"]').forEach(el => {
            issues.push({ tag: el.tagName, cls: el.className, text: el.innerText ? el.innerText.trim() : '' });
        });
        // Toast messages
        document.querySelectorAll('.toast, .Toastify, [role="alert"], div[class*="toast"], div[class*="alert"]').forEach(el => {
            if (el.innerText.trim()) issues.push({ type: 'toast', text: el.innerText.trim() });
        });
        return issues;
    }""")
    print("Issues after clicking Finish Activity:", after_click_issues)

    page.screenshot(path='audit_evidence/after_finish_validation_audit.png')
    ctx.close()
