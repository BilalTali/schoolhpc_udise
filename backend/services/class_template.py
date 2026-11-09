"""
"Download template (Part B complete students only)": checks which students' Part B is complete
(the real save's own checks, nothing re-written here), then builds the class workbook for them.

Bulk-entry answers (mother tongue and the like) saved as drafts are put into the file pre-filled; the
teacher can still change them there.

A student is READY when sync.build_payloads - the code a real save runs - reports no Part B problem
for them, with PARAKH's data plus everything set on the dashboard (Activities grid and the card
editor's Part B answers). Problems in other parts are listed in the workbook, but do not exclude.

Reading the class is read-only (GET requests) and runs in the background with progress.
"""
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.hpc import sync
from backend.hpc.portal import Portal, PortalError
from backend.hpc.fields import with_default
from backend.hpc.stages import activity_grid, get_stage
from backend.services import card_store, class_settings, hpc_cards

# Problems the Activities grid fixes (from activity_grid.plan); any other Part B problem is fixed in the card editor.
GRID_PHRASES = ("No activity chosen", "Levels not chosen", "This student has activities", "Saving would remove",
                "cannot be added", "is not in your Activity Library")

_jobs: Dict[tuple, Dict[str, Any]] = {}
_lock = threading.RLock()


def _where(part, f) -> str:
    """Where a teacher fills this question."""
    from backend.hpc.suggestions import FILL_ONLY
    if f.key in class_settings.SETTING_KEYS:
        return "Class settings (tab 4)"
    if part.code == "C" and f.kind != "text":
        return "Common answers (tab 3) - Part C levels grid"
    if hpc_cards.is_common(part.code, f):
        return f"Common answers (tab 3) - question '{f.label}'" + (" (type it, then Apply to all)" if f.label in FILL_ONLY else "")
    return f"Excel file - sheet '{{stage}}', column '{f.label}' (or the student's card)"


def precheck(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], resolve) -> Dict[str, Any]:
    """Before the class check: every empty required answer - and every answer PARAKH would refuse (too long, not
    one of the choices ...) - of every student, from what the app holds (saved
    answers, class settings, the stored copy of each card - parts not kept yet are read from PARAKH once), grouped
    by question, with where to fix it. The Activities grid's own problems (activities, levels, Part B answers)
    come from its check. Read-only."""
    from backend.services import activity_grid as grid_service, card_store
    owner = f"teacher_{teacher.id}"
    session = client.ay
    lookups = hpc_cards.lookups_for(owner, client, stage)
    st = get_stage(stage)
    ids = [s["student_id"] for s in students]
    raw, _ = card_store.class_parts(client, owner, session, stage, ids, [p.col for p in st.PARTS], False)
    from_settings = class_settings.row_values(stage, class_settings.for_teacher(teacher.id, stage, teacher.school_id))
    labels = {}
    groups: Dict[tuple, Dict[str, Any]] = {}
    complete = 0

    def add(where: str, part: str, question: str, s: Dict[str, Any]) -> None:
        g = groups.setdefault((where, part, question), {"where": where, "part": part, "question": question, "students": []})
        g["students"].append({"student_id": s["student_id"], "student_name": s.get("student_name", ""),
                              "grade": s.get("grade", ""), "section": s.get("section", "")})

    for s in students:
        sid = s["student_id"]
        draft = hpc_cards.load_draft(teacher.id, session, stage, sid) or {}
        values = draft.get("values") or {}
        before = sum(len(g["students"]) for g in groups.values())
        for part in st.PARTS:
            fd = part.load(raw[sid].get(part.col))
            part_name = f"{part.code} - {part.title.split(' - ', 1)[-1]}"
            for f in part.fields(lookups):
                if f.key in values:
                    value = values[f.key]
                elif f.key in from_settings:
                    value = from_settings[f.key]
                else:
                    value = f.read(fd)
                value = with_default(f.key, value)                # e.g. an empty mother tongue is saved as Kashmiri
                where = "Activities (tab 2) - Part B answers" if part.code == "B" else _where(part, f).replace("{stage}", stage)
                if (isinstance(value, list) and not value) or str(value if value is not None else "").strip() in ("", "[]"):
                    if f.required and part.code != "B":   # Part B's empty answers: the Activities grid says so below
                        add(where, part_name, f.label, s)
                    continue
                _, problem = f.parse(hpc_cards.to_cell_value(f, value))   # an answer PARAKH would refuse
                if problem:                                               # (too long, not one of the choices ...)
                    add(where, part_name, f"{f.label}: {problem.split(': ', 1)[-1]}", s)
        row = grid_service.student_row(stage, s, raw[sid], draft, resolve, labels)
        for problem in row["problems"]:
            if problem.startswith("Part B answers not filled: "):
                for question in problem[len("Part B answers not filled: "):].split(", "):
                    add("Activities (tab 2) - Part B answers", "B - Activity", question, s)
            else:
                add("Activities (tab 2) - the grid", "B - Activity", problem, s)
        complete += sum(len(g["students"]) for g in groups.values()) == before
    items = sorted(groups.values(), key=lambda g: (g["where"], g["part"], g["question"]))
    return {"stage": stage, "students": len(students), "complete": complete, "items": items}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dashboard_values(teacher_id: str, session: str, stage: str, student_id: str, lookups=None) -> Dict[str, Any]:
    """Everything about Part B that the dashboard holds for a student: grid values and Part B answers."""
    st = get_stage(stage)
    part_b = next(p for p in st.PARTS if p.code == "B")
    index = {f.key: f for f in part_b.fields(lookups)}          # Part B's own answers (no dropdowns from PARAKH)
    keys = set(activity_grid.grid_keys(st.DOMAINS)) | set(index)
    draft = hpc_cards.load_draft(teacher_id, session, stage, student_id) or {}
    values = {k: v for k, v in (draft.get("values") or {}).items() if k in keys}
    return {k: hpc_cards.to_cell_value(index[k], v) if k in index else v for k, v in values.items()}


def assess(stage: str, data: sync.StudentData, lookups, dashboard: Dict[str, Any], settings: Dict[str, Any],
           resolve, common: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Runs the save's own build for one student; splits its problems into Part B and the rest. Pure."""
    st = get_stage(stage)
    part_b = next(p for p in st.PARTS if p.code == "B")
    portal_row = sync.to_row(stage, data, lookups)
    row = {**portal_row, **class_settings.row_values(stage, settings), **(common or {}), **dashboard,
           **sync.school_values(stage, data)}                 # the School Register's values win, as in every save
    _, errors = sync.build_payloads(stage, data, row, lookups, resolve)
    prefix = f"{part_b.title}: "
    part_b_problems = [e[len(prefix):] for e in errors if e.startswith(prefix)]
    other = [e for e in errors if not e.startswith(prefix)]
    fix = "activities" if any(p.startswith(GRID_PHRASES) for p in part_b_problems) else ("card" if part_b_problems else "")
    return {"ready": not part_b_problems, "part_b_problems": part_b_problems, "other_problems": other, "fix": fix,
            "row": row, "portal_row": portal_row}


# ---------------------------------------------------------------------------
# The background check
# ---------------------------------------------------------------------------

def job_view(job: Optional[Dict[str, Any]], with_names: bool = True) -> Optional[Dict[str, Any]]:
    """What the screen shows. Names only for the teacher's own screen; everything else uses IDs."""
    if job is None:
        return None
    results = job["results"]
    elapsed = time.time() - job["t0"]
    left = (elapsed / job["done"] * (job["total"] - job["done"])) if job["done"] and job["status"] == "RUNNING" else 0
    students = [{"student_id": r["student_id"], **({"student_name": r["student_name"]} if with_names else {}),
                 "grade": r["grade"], "section": r["section"], "ready": r["ready"],
                 "part_b_problems": r["part_b_problems"], "other_problems": r["other_problems"][:10], "fix": r["fix"]}
                for r in results]
    return {"id": job["id"], "stage": job["stage"], "status": job["status"], "done": job["done"], "total": job["total"],
            "seconds_left": int(left), "started_at": job["started_at"], "finished_at": job["finished_at"],
            "error": job["error"], "ready": sum(r["ready"] for r in results),
            "complete": sum(complete(r) for r in results), "blocking": blocking(results), "students": students}


def complete(result: Dict[str, Any]) -> bool:
    """Ready to save to PARAKH as it is: Part B complete and nothing else missing (a save refuses a card with any
    required answer empty - the parent's name, marks obtained ...)."""
    return bool(result.get("ready")) and not result.get("other_problems")


def blocking(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What keeps Part-B-complete students from being saved, most common first: [{problem, students}]."""
    counts: Dict[str, int] = {}
    for r in results:
        if not r.get("ready"):
            continue
        for problem in dict.fromkeys(r.get("other_problems") or []):      # once per student
            counts[problem] = counts.get(problem, 0) + 1
    return [{"problem": p, "students": n} for p, n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]


def _kept_card(client: Portal, teacher_id: str, session: str, stage: str, student_id: str) -> "sync.StudentData":
    """A student's card from the app's kept copy (what the screens show), reading only what is not kept yet."""
    cols = [p.col for p in get_stage(stage).PARTS]
    found = card_store.parts(client, f"teacher_{teacher_id}", session, stage, student_id, [card_store.RECORD, *cols])
    return sync.StudentData(str(student_id), found[card_store.RECORD] or {}, {c: found[c] for c in cols})


def latest(teacher_id: str, stage: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _jobs.get((teacher_id, stage))


def start_check(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], resolve, lookups) -> Dict[str, Any]:
    """Starts checking the class unless a check is already running for this teacher and stage. It works from the
    cards the app keeps (read from PARAKH once; a student not kept yet is read then): seconds, not minutes. The
    upload still checks every student against PARAKH itself just before saving."""
    with _lock:
        running = _jobs.get((teacher.id, stage))
        if running and running["status"] == "RUNNING":
            return running
        job = {"id": uuid.uuid4().hex[:12], "stage": stage, "status": "RUNNING", "done": 0, "total": len(students),
               "results": [], "data": {}, "error": None, "started_at": _now(), "finished_at": None, "t0": time.time(),
               "session": client.ay, "settings": None, "lookups": lookups,
               "typed": activity_grid.typed_keys(resolve), "resolve": resolve}
        _jobs[(teacher.id, stage)] = job
    threading.Thread(target=_run, args=(job, client, teacher.id, stage, students, resolve, lookups), daemon=True).start()
    return job


def _run(job, client: Portal, teacher_id: str, stage: str, students, resolve, lookups) -> None:
    try:
        row = class_settings.load(teacher_id, stage)
        settings = class_settings.for_teacher(teacher_id, stage)
        job["settings"] = {"values": settings, "saved_at": row.updated_at.isoformat(timespec="seconds") + "Z"
                           if row and row.updated_at else None}
        for s in students:
            sid = s["student_id"]
            base = {"student_id": sid, "student_name": s.get("student_name", ""), "grade": s.get("grade", ""),
                    "section": s.get("section", "")}
            try:
                data = _kept_card(client, teacher_id, job["session"], stage, sid)
            except PortalError as exc:
                job["results"].append({**base, "ready": False, "fix": "", "other_problems": [],
                                       "part_b_problems": [f"Could not read this student's card from PARAKH ({exc})."]})
            else:
                result = assess(stage, data, lookups, dashboard_values(teacher_id, job["session"], stage, sid, lookups),
                                settings, resolve, hpc_cards.common_values(teacher_id, job["session"], stage, sid, lookups))
                job["data"][sid] = (data, result["row"])
                job["results"].append({**base, **{k: result[k] for k in ("ready", "part_b_problems", "other_problems", "fix")}})
            job["done"] += 1
        job["status"] = "COMPLETED"
    except Exception as exc:                                   # the check reads only; a failure changes nothing
        job["status"], job["error"] = "FAILED", f"The check stopped: {exc}"
    finally:
        job["finished_at"] = _now()


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

RULE = "Only students whose Part B is complete (the same checks a real save runs) - unless 'all students' was chosen."


def _section(teacher, stage: str, include_all: bool, labels: Dict[str, str], only: Optional[set] = None):
    """One stage's part of a template, from its last finished check (nothing more is read from PARAKH).
    only: just these students (chosen by the teacher, ready or not).
    Returns (section for template.build_many, every student's result, the students in the file, the check)."""
    from fastapi import HTTPException, status
    from backend.hpc import template
    job = latest(teacher.id, stage)
    if not job or job["status"] != "COMPLETED":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Check the class first on {stage} (it reads each student's card).")
    settings = (job.get("settings") or {}).get("values") or class_settings.blank(stage)
    gaps = class_settings.missing(stage, settings)
    if gaps:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Finish the class settings for {stage} first: " + "; ".join(gaps) + ".")
    results = job["results"]
    chosen = [r for r in results if (r["student_id"] in only if only is not None else include_all or r["ready"])
              and r["student_id"] in job["data"]]
    lookups = job["lookups"]
    rows, part_b, problems = {}, {}, {}
    st = get_stage(stage)
    for r in chosen:
        data, row = job["data"][r["student_id"]]
        parts = {p.col: p.load(data.raw_parts.get(p.col)) for p in st.PARTS if p.col in ("part_b", "part_c")}
        defaults = activity_grid.defaults_for(job.get("resolve"), (data.record.get("stu_info") or {}).get("grade_id"))
        _, grid_values, _ = sync.grid_state(stage, parts, row, lookups, job.get("typed"), defaults)
        rows[r["student_id"]] = row
        part_b[r["student_id"]] = template.part_b_view(stage, {**row, **grid_values}, lookups, labels)
        problems[r["student_id"]] = [] if r["ready"] else list(r["part_b_problems"])   # the rest: live colours
    section = {"stage": stage, "students": [{"student_id": r["student_id"], "student_name": r["student_name"]} for r in chosen],
               "rows": rows, "lookups": lookups, "settings": settings, "marks_subjects": class_settings.marks_subjects(stage),
               "is_setting_key": class_settings.is_setting_key, "part_b": part_b, "problems": problems}
    return section, results, chosen, job


def build_download(teacher, stage: str, include_all: bool, path, labels: Dict[str, str], only: Optional[set] = None):
    """The template for one stage (only: just the students the teacher chose)."""
    return build_download_many(teacher, [stage], include_all, path, {stage: labels}, only)


def build_download_many(teacher, stages: List[str], include_all: bool, path, labels: Dict[str, Dict[str, str]],
                        only: Optional[set] = None):
    """One file for several stages: a sheet per stage. Every stage needs a finished check and its class settings;
    a stage with nobody ready is left out (the Class summary says so)."""
    from fastapi import HTTPException, status
    from backend.hpc import template
    sections, everyone, in_file, checks = [], [], set(), []
    for stage in stages:
        section, results, chosen, job = _section(teacher, stage, include_all, labels.get(stage) or {}, only)
        checks.append((stage, job))
        everyone += [{**r, "stage": stage} for r in results]
        in_file |= {r["student_id"] for r in chosen}
        if chosen:
            sections.append(section)
    if not sections:
        raise HTTPException(status.HTTP_409_CONFLICT, "None of the chosen students is in the last check." if only is not None
                            else "No student's Part B is complete yet, so there is nothing to put in the file.")
    one = len(stages) == 1
    saved = [(stage, (job.get("settings") or {}).get("saved_at")) for stage, job in checks]
    summary = {"generated_at": _now(),
               "ready_as_of": min(job["finished_at"] for _, job in checks),
               "settings_saved_at": saved[0][1] if one else "; ".join(f"{stage}: {at or '-'}" for stage, at in saved),
               "classes": ", ".join(sorted({f"{r['grade']} {r['section']}".strip() for r in everyone})),
               "included_count": len(in_file), "excluded_count": len(everyone) - len(in_file),
               "rule": ("Only the students the teacher chose (not-ready ones are marked)" if only is not None
                        else "All students (not-ready ones are marked)" if include_all else RULE)
                       + ("" if one or len(sections) == len(stages) else
                          " Stages with nobody ready yet are not in this file: "
                          + ", ".join(st for st in stages if st not in {sec["stage"] for sec in sections}) + "."),
               "students": [{"student_id": r["student_id"], "in_file": r["student_id"] in in_file, "ready": r["ready"],
                             "part_b_problems": r["part_b_problems"], "other_problems": r["other_problems"][:10],
                             "stage": r["stage"]} for r in everyone]}
    template.build_many(path, sections, summary)
    from backend.services import audit
    audit.record(f"teacher:{teacher.id}", "download_template", "class_template", ",".join(sec["stage"] for sec in sections), None,
                 {"students": sorted(in_file), "include_all": include_all, "chosen": only is not None})
    return path
