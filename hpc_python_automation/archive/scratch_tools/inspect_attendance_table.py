from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/preparatory-stage/MTQyNDExLTI2Mjctams=/part-A1', wait_until='networkidle')
    
    table = page.locator('table').first
    rows = table.locator('tr').all()
    print('Total rows in attendance table:', len(rows))
    for r_idx, r in enumerate(rows):
        txt = r.inner_text().replace('\n', ' | ')[:80]
        inputs = r.locator('input').all()
        inp_details = [(inp.input_value(), inp.get_attribute('readonly')) for inp in inputs]
        print(f'Row {r_idx}: text="{txt}" | inputs({len(inputs)}): {inp_details}')
    ctx.close()
