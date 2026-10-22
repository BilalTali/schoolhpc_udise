import time
from playwright.sync_api import sync_playwright

def inspect_middle_roster():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Navigating to Middle Stage roster...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(3)
        print("Current URL:", page.url)

        headers = [th.inner_text().strip() for th in page.locator("table thead th").all()]
        print("Table Headers:", headers)

        rows = page.locator("table tbody tr").all()
        print(f"Total rows in Middle Stage table: {len(rows)}")

        for idx, r in enumerate(rows[:10]):
            txt = r.inner_text().strip().replace('\n', ' | ').encode('ascii', 'replace').decode()
            links = r.locator("a").all()
            link_info = [(lnk.inner_text().strip().encode('ascii', 'replace').decode(), lnk.get_attribute("href")) for lnk in links]
            buttons = r.locator("button").all()
            btn_info = [b.inner_text().strip().encode('ascii', 'replace').decode() for b in buttons]
            print(f"Row {idx}: {txt}")
            print(f"   Links: {link_info}")
            print(f"   Buttons: {btn_info}")

        ctx.close()

if __name__ == '__main__':
    inspect_middle_roster()
