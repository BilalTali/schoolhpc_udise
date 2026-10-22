import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_middle_credit():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        slug = "MTQ0OTcyLTI2Mjctams="
        url = f"https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/{slug}/hpc-credit"
        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle')
        time.sleep(2)

        # Print all tables
        tables = page.locator("table").all()
        print(f"Total tables on HPC Credit: {len(tables)}")
        for t_idx, tbl in enumerate(tables):
            rows = tbl.locator("tr").all()
            print(f"Table {t_idx} has {len(rows)} rows:")
            for r_idx, r in enumerate(rows):
                txt = r.inner_text().strip().replace('\n', ' | ')[:100]
                inps = r.locator("input").all()
                inp_details = [(inp.input_value(), inp.get_attribute("readonly")) for inp in inps]
                print(f"  r{r_idx}: text={repr(txt)} | inps={inp_details}")

        # Check checkboxes (declaration)
        cbs = page.locator("input[type=checkbox]").all()
        print(f"Checkboxes: {len(cbs)}")
        for idx, cb in enumerate(cbs):
            lbl = cb.evaluate("(el) => el.closest('label')?.innerText || el.parentElement?.innerText")
            print(f"  cb[{idx}]: checked={cb.is_checked()}, label={repr(lbl)}")

        # Check buttons
        btns = [b.inner_text().strip() for b in page.locator("button:visible").all()]
        print("Visible buttons on HPC Credit:", btns)

        ctx.close()

if __name__ == '__main__':
    inspect_middle_credit()
