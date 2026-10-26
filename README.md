# Teacher Assist (HPC helper)

Fills students' Holistic Progress Cards on the PARAKH HPC portal
(https://hpc.parakh.ncert.gov.in) from an Excel workbook, for the **Foundational**,
**Preparatory** and **Middle** stages. A teacher with students in several stages gets one
workbook covering all of them.

```
teacher logs in ──► fetch class ──► Excel workbook ──► teacher fills it ──► upload
                                                                           │
            portal: A1 → A2 → (A3) → (A4) → B → C → HPC Credit → Mark as Complete
```

No browser automation: the app talks to the portal's own JSON API, sending exactly what
the portal's web pages send when a teacher clicks *Continue* and *Mark as Complete*.

## Run it

Requirements: Python 3.11+, Node 18+, MySQL (XAMPP) running.

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..

# terminal 1 - API on http://127.0.0.1:8000  (docs at /docs)
python -m uvicorn backend.main:app --reload

# terminal 2 - web app on http://localhost:5173
cd frontend && npm run dev
```

Settings (database URL, secret) can go in `.env` - see `.env.example`.
Tests: `python -m pytest`.

Settings: copy `frontend/.env.example` to `frontend/.env` to change `VITE_API_BASE` (default
`/api/v1`, forwarded by the dev server to `VITE_API_PROXY_TARGET`, default `http://127.0.0.1:8000`).
The web app signs in with an httpOnly cookie; it keeps no token in the browser's storage.

## Rules

- **The teacher types the PARAKH captcha.** The app shows PARAKH's captcha picture when a teacher
  connects; after that the session is renewed with PARAKH's own refresh token.
  `HPC_AUTO_CAPTCHA=true` makes the app read the captcha itself. That mode is **unsupported**,
  off by default, and is to be removed before any paid launch: PARAKH has not approved automated logins.
- **No student data goes to external AI services**, or anywhere except the PARAKH portal itself.
- **A copy of a student's PARAKH record is kept before every save** (`data/snapshots/`); a save is
  refused if the copy cannot be written. Restoring = a new save of those values, shown first.
- Requests to PARAKH are limited to `HPC_PORTAL_MAX_PER_SECOND` (default 4) per session.
- Changes to drafts, settings and saves to PARAKH are written to the `audit_log` table
  (never passwords).

## Where the data lives, and backups

Students' records, drafts, snapshots, PARAKH session tokens and the app's own keys live in
`HPC_DATA_DIR` (here `C:\TeacherAssist\data`), **outside OneDrive** or any other synced folder.
Set it, and the two below, in the project's `.env` (never committed).

| What | Where (this machine) | Protection |
|---|---|---|
| Data folder | `C:\TeacherAssist\data` | PARAKH passwords encrypted with `data/.secret_key`; session tokens and drafts as plain files on this disk |
| Backups | `C:\TeacherAssist\backups` | Encrypted (Fernet: AES-128 + HMAC) before they are written |
| Backup key | `C:\TeacherAssist\keys\backup.key` | Kept apart from the backups. **Keep an offline copy** (USB stick in a safe place): without it no backup can be opened |

`python scripts/backup_db.py` writes `db_hpc_automation_<time>.sql.enc` and `data_<time>.tar.gz.enc`
and applies the retention rules. `python scripts/restore_test.py` decrypts the newest backup in memory,
restores it into a scratch database (`hpc_restore_test`), compares it table by table and opens the
data archive. Windows Task Scheduler runs them as *TeacherAssist\Daily DB backup* (21:00) and
*TeacherAssist\Weekly restore test* (Sunday 21:30); both also run as soon as possible after a
missed start (PC off). Output goes to `backup_log.txt` in the backup folder.

Retention: backups keep the newest 14 plus the newest of each of the last 8 weeks; snapshots are
kept 400 days, and each student's newest 2 are always kept.

To restore for real: stop the API, decrypt with the key
(`python -c "from cryptography.fernet import Fernet; import sys; open(sys.argv[3],'wb').write(Fernet(open(sys.argv[1],'rb').read()).decrypt(open(sys.argv[2],'rb').read()))" <key> <file.enc> <out>`),
load the `.sql` with `mysql -u root hpc_automation < out.sql`, unpack the data archive over
`HPC_DATA_DIR`, then delete the decrypted files.

## How a teacher uses it

1. **Start HPC Session** with their portal login ID and password. The captcha is solved
   automatically; if the portal sends an OTP, enter it.
2. **Sync Roster**, then **Download Excel**. The workbook covers every stage the teacher
   has (assigned in this app or on the portal): a *Students* sheet with each student's
   stage, and one sheet per stage and HPC part (e.g. *Prep A1*, *Middle B*, *Found. C*),
   already filled with what the portal holds today.
3. Fill the workbook. Red headers are required; dropdowns show the allowed values.
4. **Upload** it. Every student is checked first with the portal's own rules - students
   with problems are listed and skipped, nothing is written for them.
5. **Sync**. Each ready student is saved part by part and marked complete, then read back
   to confirm the portal shows COMPLETED.

## Code map

```
backend/
  main.py              FastAPI app
  routers/             HTTP endpoints (auth, school admin, teacher)
  services/            portal sessions per user, upload jobs
  models/, schemas/    database tables, request/response shapes
  hpc/                 everything about the portal - usable without the web app
    portal.py          login (captcha, OTP), roster, read a part, save a part
    captcha.py         solves the login captcha
    stages/            what each part contains, per stage
      shared.py          A1 (all stages), C and HPC Credit (Preparatory, Middle)
      foundational.py    A2, B, C, HPC Credit for Balvatika 1-3, Grades 1-2
      preparatory.py     A2, A3, B for Grades 3-5
      middle.py          A2, A3, A4, B for Grades 6-8
      activity.py        Part B activities (Activity Bank)
    credit.py          HPC Credit tables, calculated exactly like the portal page
    fields.py          one Excel column <-> one value inside a part
    workbook.py        writes / reads the class workbook
    sync.py            fetch students, build save requests, sync a student
    reference/         tables extracted from the portal's page code
  tests/
frontend/              React web app (single page, src/App.tsx)
```

## When the portal changes

Every part's format comes from the portal's page code. If the portal is updated and a
part stops saving correctly, compare its page code (`/en/hpc/<stage>/<id>/part-...`) with
the matching definition in `backend/hpc/stages/`, and re-run the tests. The credit
constants in `hpc/reference/credit_tables.json` come from the `hpc-credit` page.

## Limits

- Secondary stage is not built.
- Foundational was built from the portal's page code and tested offline; no Foundational
  student existed on the test account yet, so it has not been checked against a real record.
- Part B uses one Activity Bank activity per student (more can be added in the portal).
  Bank activities with pictures are left out, because the portal page re-uploads those
  pictures and this app does not.
- The portal can end a session early (for example after logging in on the website with the
  same account). The app then renews the token, or logs in again with the saved login.
