# HPC Python Automation

Read-only field inspector and future automation toolkit for the HPC portal
(https://hpc.parakh.ncert.gov.in).

---

## Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium
```

## Running Tests

```bash
pytest
```

Both placeholder tests should pass immediately after setup.

## Running the Field Inspector

```bash
python audit/browser_inspector.py
```

1. A Chromium browser window will open and navigate to the HPC dashboard.
2. **Log in yourself** in the browser — credentials are never stored in code or files.
3. Open the form page/stage you want to capture, then return to the terminal.
4. Enter the stage label (e.g. `Preparatory`) and a short note (e.g. `student-details`).
5. The script takes a screenshot and records all form controls — **read-only, no clicks or submits**.
6. Repeat for each page/stage, then enter `q` to finish.

Outputs (all git-ignored):
- `hpc_field_audit.xlsx` — field inventory spreadsheet
- `hpc_field_audit.json` — machine-readable field data
- `network_log.json` — API call log (no headers, cookies or bodies)
- `audit_evidence/*.png` — full-page screenshots

## Rules

- **The user logs in manually.** Credentials (username, password, OTP, token) must never appear in code or any file.
- **The audit is strictly read-only.** The inspector never clicks, types or submits.
- **No upload before reconciliation.** Do not use the uploader until the field audit is fully reconciled against the Excel template.
- **Student data is never committed.** The `data/` directory and all `.xlsx`/`.csv` files are git-ignored.
