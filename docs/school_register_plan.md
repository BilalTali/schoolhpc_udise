# School Register: implementation plan

The school becomes the central data layer. Teachers keep their PARAKH login **only to save cards** (PARAKH accepts a
card from the class teacher only, and a save must read the card just before it, so nothing is overwritten).

```
School: PARAKH (school login) --> School Register: students of every stage, PARAKH's teachers and their classes
School: UDISE+ SDMS ----------> father's / mother's name, date of birth, APAAR (source kept)
School: Excel ----------------> monthly working days and days present, father/mother/guardian, summative marks
Teacher: class list from the School Register (their PARAKH classes); school values arrive locked
Teacher: saves cards to PARAKH with their own login (existing code: read before save, snapshot, verify, retry)
School: sees every student's status; compares UDISE+ / APAAR / PARAKH; reports
```

## What the code had (audit, 2026-11-01)

| Area | Before |
|---|---|
| School PARAKH fetch | `POST /school/roster/sync` used the teacher list path (`/teachers/{staff_id}/hpc/{stage}`) with the school login: one stage, saved as a file, used by nothing. A real school's file is empty. |
| PARAKH school endpoints (from PARAKH's page code) | `/states/{s}/districts/{d}/schools/{sch}/hpc/{stage}` (the school's HPC list), `/schools/{sch}/teachers`, `/schools/{sch}/teachers/{t}/grade_sections`. Not used. |
| Teacher fetch | Teacher login reads roster + every card (record + 6-7 parts per student) into a workbook and the card store. |
| Working days, max marks | Per teacher and stage (`class_settings`). |
| Saving | Teacher login; `sync.sync_student` reads the card, snapshots, saves part by part, verifies. **Kept as is.** |
| UDISE vs PARAKH | `udise_parakh.compare` - school only, but against classes the teachers fetched. |
| Storage | MySQL: accounts, upload jobs, library. Files: rosters, card copies, drafts. No school student table. |

## Phases (each committed and tested on its own)

1. **School Register** - tables `register_students` (unique: school, stage, PARAKH student id; exact PARAKH name and
   identity kept, never overwritten by Excel), `register_teacher_classes` (PARAKH teacher -> grade/section).
   School fetch via the school endpoints (all stages, assigned and unassigned students), idempotent upserts; a
   student PARAKH no longer lists is marked, not deleted. Falls back to the old path if the school endpoint is
   refused. Teacher -> students: the classes PARAKH maps to that teacher (matched by the teacher's PARAKH login).
2. **School settings and Excel** - working days per month and max marks per subject set by the school per stage
   and session (teachers read only; history kept). Workbook: Instructions, one sheet per stage with PARAKH identity
   (locked), monthly days present (absent and % calculated), father / mother (from UDISE+ when known) / guardian,
   marks obtained. Upload: template version, school, student ids, identity edits flagged, totals, marks <= max,
   duplicates, preview, apply valid rows, import history and audit. Re-upload of the same file changes nothing.
3. **Teacher data from the register** - the teacher's class list comes from the register (no PARAKH roster read);
   school values (working days, days present, guardian, max and obtained marks) are merged into every place a card
   row is built and are read-only for the teacher. Cards are read from PARAKH only when opened or saved.
4. **Status** - register status per student: fetched, assigned, in progress, submitted, verified on PARAKH, failed,
   needs correction - from the save's own verified result and PARAKH's hpc_status on the next fetch.
5. **Reconciliation** - `udise_parakh.compare` against the register; school only.
6. **Reports** - school: register, unassigned, attendance, marks, teacher progress, failures, missing data;
   teacher: own students only.

Not built (no PARAKH field or not asked): daily attendance, leave days on PARAKH, assessment periods beyond the one
PARAKH mark per subject, an APAAR source other than UDISE+ / PARAKH.

## Needs a live check (cannot be tested without a real school login)
The shape of PARAKH's school list and grade_sections replies is taken from its page code; the fetch logs what it
got and falls back to the old path. The first live school fetch must be checked against PARAKH's own screen.
