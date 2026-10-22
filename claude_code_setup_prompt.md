# Claude Code prompt: HPC project skeleton, venv and inspector

Prepare the project skeleton, virtual environment and dependencies for "hpc_python_automation", and install the field inspector provided at the end of this prompt. Do setup only. Do not write other portal logic, do not open the portal, and do not touch any student data.

## Environment
- OS: macOS. Editor: VS Code. Use Python 3.11 or newer (check with `python3 --version`; stop and tell me if it is older).
- Create the project in the current directory as `hpc_python_automation/`.

## Step 1: Virtual environment
1. `python3 -m venv .venv`
2. Activate with `source .venv/bin/activate`.
3. `python -m pip install --upgrade pip`
4. Create `.vscode/settings.json` setting `python.defaultInterpreterPath` to `${workspaceFolder}/.venv/bin/python`.

## Step 2: Dependencies
Create `requirements.txt` with: playwright, pandas, openpyxl, pydantic, pytest, streamlit, python-dotenv. Install with `pip install -r requirements.txt`. Then:
1. `python -m playwright install chromium`
2. `pip freeze > requirements.lock.txt`
3. Import-check every package and print each version.

## Step 3: Folder structure
Create exactly this tree, with an empty `__init__.py` in every Python package folder:

```
hpc_python_automation/
├── app.py                      (placeholder: prints "HPC automation, not implemented yet")
├── config/
│   ├── portal.json             (start_url: https://hpc.parakh.ncert.gov.in/en/hpc-dashboard, stages: Preparatory, Middle)
│   └── stage_schemas.json      (empty object {}, to be filled from the canonical headers)
├── audit/
│   ├── browser_inspector.py    (FULL CODE provided below, write it verbatim)
│   ├── field_inventory.py      (stub)
│   └── audit_report.py         (stub)
├── excel/
│   ├── template_generator.py   (stub)
│   ├── importer.py             (stub)
│   └── validator.py            (stub)
├── portal/
│   ├── login.py                (stub)
│   ├── uploader.py             (stub)
│   └── verifier.py             (stub)
├── database/
│   ├── models.py               (stub)
│   └── repository.py           (stub)
├── tests/
│   ├── test_mappings.py        (one placeholder test that passes)
│   └── test_validation.py      (one placeholder test that passes)
├── reports/
├── audit_evidence/
├── data/                       (input workbooks; git-ignored)
├── requirements.txt
├── requirements.lock.txt
├── .env.example
├── .gitignore
└── README.md
```

Stub files get a short docstring stating their single responsibility and no other code.

## Step 4: Config and safety files
- `.gitignore` must exclude: `.venv/`, `.browser_profile/`, `audit_evidence/`, `reports/`, `data/`, `*.xlsx`, `*.csv`, `*.db`, `.env`, `__pycache__/`, `.pytest_cache/`, `hpc_field_audit.json`, `network_log.json`.
- `.env.example` holds only non-secret settings (`PORTAL_URL=`, `BATCH_SIZE=25`). No username, password, OTP or token fields.
- `README.md` documents setup, venv activation, running tests and the inspector (`python audit/browser_inspector.py`), plus these rules: the user logs in manually; credentials never go in code or files; the audit is read-only; no upload before the audit is reconciled; student data is never committed.

## Step 5: Verification
1. `python -m py_compile audit/browser_inspector.py` must succeed. Do NOT run the inspector or open the portal.
2. Run `pytest`; both placeholder tests must pass.
3. Run `python app.py`; it must print the placeholder message.
4. Print the final folder tree.
5. `git init` and commit with message "Project skeleton".

## Rules
- Install nothing outside the venv.
- Create no files beyond those listed.
- If any step fails, stop and report the exact error instead of working around it.
- Finish with a checklist of what was created and the installed versions.

## File content: audit/browser_inspector.py (write verbatim)

```python
"""
HPC portal field inspector (READ-ONLY).

You log in yourself in the browser window. For each page/stage you open,
press Enter in the terminal and the script records every form control and
a screenshot. It never clicks, types or submits anything.

Run from the project root:
    python audit/browser_inspector.py
Outputs:
    hpc_field_audit.xlsx, hpc_field_audit.json, network_log.json, audit_evidence/*.png
"""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
from playwright.sync_api import sync_playwright

START_URL = "https://hpc.parakh.ncert.gov.in/en/hpc-dashboard"
ROOT = Path.cwd()
EVIDENCE = ROOT / "audit_evidence"
PROFILE = ROOT / ".browser_profile"  # keeps your session between runs; add to .gitignore
EVIDENCE.mkdir(exist_ok=True)
NETWORK_LOG = []  # method, URL (no query string), status only; no headers, cookies or bodies

EXTRACT_JS = """
() => {
  const labelFor = el => {
    const out = [];
    if (el.labels) for (const l of el.labels) out.push(l.innerText.trim());
    const aria = el.getAttribute('aria-label'); if (aria) out.push(aria);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) lb.split(/\\s+/).forEach(id => {
      const n = document.getElementById(id); if (n) out.push(n.innerText.trim());
    });
    if (!out.length) {
      const wrap = el.closest('div');
      const l = wrap && wrap.querySelector('label');
      if (l) out.push(l.innerText.trim());
    }
    if (!out.length && el.placeholder) out.push(el.placeholder);
    return out.join(' | ');
  };
  const sectionOf = el => {
    const fs = el.closest('fieldset');
    if (fs && fs.querySelector('legend')) return fs.querySelector('legend').innerText.trim();
    let n = el;
    while (n && n !== document.body) {
      let p = n.previousElementSibling;
      while (p) {
        const h = p.matches('h1,h2,h3,h4,h5') ? p : p.querySelector('h1,h2,h3,h4,h5');
        if (h) return h.innerText.trim();
        p = p.previousElementSibling;
      }
      n = n.parentElement;
    }
    return '';
  };
  const sel = 'input, select, textarea, [role=combobox], [role=listbox], [contenteditable=true]';
  return [...document.querySelectorAll(sel)].map((el, i) => {
    const tag = el.tagName.toLowerCase();
    let options = [];
    if (tag === 'select') options = [...el.options].map(o => o.text.trim());
    else if (['radio', 'checkbox'].includes(el.type)) options = [el.value];
    return {
      order: i + 1,
      section: sectionOf(el),
      label: labelFor(el),
      html_name: el.getAttribute('name') || '',
      html_id: el.id || '',
      tag: tag,
      control_type: el.type || el.getAttribute('role') || tag,
      required: !!el.required || el.getAttribute('aria-required') === 'true',
      readonly: !!el.readOnly,
      disabled: !!el.disabled,
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
      allowed_values: options.join(' ; '),
      maxlength: el.getAttribute('maxlength') || '',
      minlength: el.getAttribute('minlength') || '',
      pattern: el.getAttribute('pattern') || '',
      min: el.getAttribute('min') || '',
      max: el.getAttribute('max') || '',
      placeholder: el.getAttribute('placeholder') || '',
      current_value_present: !!(el.value && String(el.value).trim()),
    };
  });
}
"""


def capture(page, stage, note, seq):
    rows = []
    for frame in page.frames:
        try:
            controls = frame.evaluate(EXTRACT_JS)
        except Exception as exc:  # cross-origin or detached frame
            print(f"  skipped frame {frame.url}: {exc}")
            continue
        for c in controls:
            c.update(
                stage=stage,
                page_url=frame.url,
                page_note=note,
                captured_at=datetime.now().isoformat(timespec="seconds"),
                # filled in later during reconciliation
                excel_header="",
                mapping_status="unmapped",
                test_status="not tested",
                evidence="",
            )
            rows.append(c)
    shot = EVIDENCE / f"{seq:03d}_{stage}_{note}.png".replace(" ", "_").replace("/", "-")
    page.screenshot(path=str(shot), full_page=True)
    for r in rows:
        r["evidence"] = shot.name
    return rows


def log_response(resp):
    req = resp.request
    if req.resource_type in ("xhr", "fetch", "document") or req.method != "GET":
        u = urlsplit(resp.url)
        NETWORK_LOG.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "method": req.method,
            "url": f"{u.scheme}://{u.netloc}{u.path}",
            "status": resp.status,
            "resource_type": req.resource_type,
        })


def save(all_rows):
    (ROOT / "network_log.json").write_text(
        json.dumps(NETWORK_LOG, indent=2), encoding="utf-8"
    )
    if not all_rows:
        return
    df = pd.DataFrame(all_rows)
    df.to_excel(ROOT / "hpc_field_audit.xlsx", index=False)
    (ROOT / "hpc_field_audit.json").write_text(
        json.dumps(all_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main():
    all_rows, seq = [], 0
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE), headless=False, viewport={"width": 1400, "height": 900}
        )
        ctx.on("response", log_response)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(START_URL)
        print("\nLog in yourself in the browser window. Do NOT share credentials.")
        print("Open a form page, set the stage, then come back here.\n")
        while True:
            stage = input("Stage label (Preparatory / Middle / other), or q to finish: ").strip()
            if stage.lower() == "q":
                break
            note = input("Short page/section note (e.g. 'student-details'): ").strip() or "page"
            seq += 1
            rows = capture(page, stage or "unknown", note, seq)
            all_rows.extend(rows)
            save(all_rows)
            print(f"  captured {len(rows)} controls (total {len(all_rows)})\n")
            print("Tip: also capture again after choosing dropdown values or "
                  "triggering validation, since some rules only appear then.\n")
        ctx.close()
    print(f"Done. {len(all_rows)} controls saved to hpc_field_audit.xlsx")


if __name__ == "__main__":
    main()
```
