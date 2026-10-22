import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def capture_412_body():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/hpc-credit"
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        # Check declaration
        cb = page.locator("input[type=checkbox]").last
        if not cb.is_checked():
            page.evaluate("(el) => el.click()", cb)
            time.sleep(1)

        def handle_response(response):
            if "hpc/2627/MIDDLE/144972" in response.url:
                print(f"\n>>> URL: {response.url}")
                print(f">>> STATUS: {response.status}")
                try:
                    print(f">>> BODY: {response.text()}")
                except Exception as e:
                    print(f">>> ERR READING BODY: {e}")

        page.on("response", handle_response)

        mark_btn = page.locator("button:has-text('Mark as Complete')").first
        print("Clicking Mark as Complete to catch error response...")
        mark_btn.click()
        time.sleep(4)

        ctx.close()

if __name__ == '__main__':
    capture_412_body()
