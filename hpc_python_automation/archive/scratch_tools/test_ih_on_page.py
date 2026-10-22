import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context('.browser_profile', headless=True)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.goto('https://hpc.parakh.ncert.gov.in/en/hpc/middle-stage/MTQ0OTcyLTI2Mjctams=/part-B', wait_until='networkidle')
    time.sleep(2)

    # Let's inspect the current student formdata from the page or fetch
    res = page.evaluate("""async () => {
        const resp = await fetch('/api/proxy/states/jk/hpc/2627/MIDDLE/144972?hpc_col=part_b');
        const json = await resp.json();
        const act = json.data.formdata[0];
        const dt = act.dt;
        return {
            name: act.nm,
            is_complete: act.is_complete,
            domains: dt.domain,
            has_gl: Array.isArray(dt.gl) && dt.gl.length,
            has_cpt: Array.isArray(dt.cpt) && dt.cpt.length,
            activity: dt.activity,
            ast: dt.ast,
            bar: dt.bar,
            tf: dt.tf,
            desc: dt.desc,
            spt: dt.spt,
            awr: dt.awr,
            sen: dt.sen,
            cre: dt.cre,
            slr: dt.slr,
            ml: dt.ml,
            mpa: dt.mpa,
            mps: dt.mps,
            mpc: dt.mpc
        };
    }""")
    print("CURRENT ACTIVITY KEYS & STATUS:")
    for k, v in res.items():
        print(f"  {k}: {v}")

    ctx.close()
