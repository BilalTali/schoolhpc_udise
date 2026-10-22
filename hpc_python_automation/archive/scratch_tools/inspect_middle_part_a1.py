import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')

def inspect_middle_part_a1():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Opening Middle Stage...")
        page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage', wait_until='networkidle')
        time.sleep(2)

        # Click Open on row 0 (ARBAZ IQBAL)
        row0 = page.locator("table tbody tr").first
        last_cell = row0.locator("td").last
        action_trigger = last_cell.locator(".custom-dropdown-header, label:has-text('⋮'), svg").first
        action_trigger.click()
        time.sleep(0.5)

        open_opt = page.locator(".custom-dropdown-item:has-text('Open'), li:has-text('Open'), div:has-text('Open')").last
        open_opt.click()
        time.sleep(3)

        print("Current URL:", page.url)

        # Inspect Grade radios
        radios = page.locator("input[type=radio]").all()
        print(f"Total radio inputs: {len(radios)}")
        for r in radios:
            name = r.get_attribute("name")
            val = r.get_attribute("value")
            checked = r.is_checked()
            lbl = r.evaluate("(el) => el.closest('label')?.innerText || el.parentElement?.innerText")
            print(f"  Radio: name={name}, val={val}, checked={checked}, label={repr(lbl)}")

        # Inspect dropdowns
        dropdowns = page.locator(".custom-dropdown-wrapper").all()
        print(f"Total custom dropdowns: {len(dropdowns)}")
        for d in dropdowns:
            txt = d.inner_text().strip().replace('\n', ' | ')
            print(f"  Dropdown: {repr(txt)}")

        # Inspect attendance table
        tables = page.locator("table").all()
        print(f"Total tables: {len(tables)}")
        for t_idx, tbl in enumerate(tables):
            rows = tbl.locator("tr").all()
            print(f"Table {t_idx} has {len(rows)} rows:")
            for r_idx, r in enumerate(rows):
                txt = r.inner_text().strip().replace('\n', ' | ')[:80]
                inps = r.locator("input").all()
                print(f"  r{r_idx}: text={repr(txt)} | inputs={len(inps)}")

        # Inspect interest checkboxes or sections
        checkboxes = page.locator("input[type=checkbox]").all()
        print(f"Total checkboxes: {len(checkboxes)}")
        for cb in checkboxes[:15]:
            lbl = cb.evaluate("(el) => el.closest('label')?.innerText || el.parentElement?.innerText")
            print(f"  CB: name={cb.get_attribute('name')}, id={cb.get_attribute('id')}, label={repr(lbl)}")

        # Inspect buttons at bottom
        buttons = page.locator("button").all()
        btn_texts = [b.inner_text().strip() for b in buttons if b.is_visible()]
        print(f"Visible buttons: {btn_texts}")

        ctx.close()

if __name__ == '__main__':
    inspect_middle_part_a1()
