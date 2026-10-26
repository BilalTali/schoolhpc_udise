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
from backend.hpc.stages import activity_grid, get_stage
from backend.services import class_settings, hpc_cards

# Problems the Activities grid fixes (from activity_grid.plan); any other Part B problem is fixed in the card editor.
GRID_PHRASES = ("No activity chosen", "Levels not chosen", "This student has activities", "Saving would remove",
                "cannot be added", "is not in your Activity Library")

_jobs: Dict[tuple, Dict[str, Any]] = {}
_lock = threading.Lock()


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
    row = {**portal_row, **class_settings.row_values(stage, settings), **(common or {}), **dashboard}
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
            "error": job["error"], "ready": sum(r["ready"] for r in results), "students": students}


def latest(teacher_id: str, stage: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _jobs.get((teacher_id, stage))


def start_check(client: Portal, teacher, stage: str, students: List[Dict[str, Any]], resolve, lookups) -> Dict[str, Any]:
    """Starts reading the class (GET only) unless a check is already running for this teacher and stage."""
    with _lock:
        running = _jobs.get((teacher.id, stage))
        if running and running["status"] == "RUNNING":
            return running
        job = {"id": uuid.uuid4().hex[:12], "stage": stage, "status": "RUNNING", "done": 0, "total": len(students),
               "results": [], "data": {}, "error": None, "started_at": _now(), "finished_at": None, "t0": time.time(),
               "session": client.ay, "settings": None, "lookups": lookups,
               "typed": activity_grid.typed_keys(resolve)}
        _jobs[(teacher.id, stage)] = job
    threading.Thread(target=_run, args=(job, client, teacher.id, stage, students, resolve, lookups), daemon=True).start()
    return job


def _run(job, client: Portal, teacher_id: str, stage: str, students, resolve, lookups) -> None:
    try:
        row = class_settings.load(teacher_id, stage)
        settings = row.values if row else class_settings.blank(stage)
        job["settings"] = {"values": settings, "saved_at": row.updated_at.isoformat(timespec="seconds") + "Z"
                           if row and row.updated_at else None}
        for s in students:
            sid = s["student_id"]
            base = {"student_id": sid, "student_name": s.get("student_name", ""), "grade": s.get("grade", ""),
                    "section": s.get("section", "")}
            try:
                data = sync.fetch_student(client, stage, sid)
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


def build_download(teacher, stage: str, include_all: bool, path, labels: Dict[str, str]):
    """Builds the template from the last finished check (nothing more is read from PARAKH)."""
    from fastapi import HTTPException, status
    from backend.hpc import template
    job = latest(teacher.id, stage)
    if not job or job["status"] != "COMPLETED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Check the class first (it reads each student's card).")
    settings = (job.get("settings") or {}).get("values") or class_settings.blank(stage)
    gaps = class_settings.missing(stage, settings)
    if gaps:
        raise HTTPException(status.HTTP_409_CONFLICT, "Finish the class settings first: " + "; ".join(gaps) + ".")
    results = job["results"]
    chosen = [r for r in results if (include_all or r["ready"]) and r["student_id"] in job["data"]]
    if not chosen:
        raise HTTPException(status.HTTP_409_CONFLICT, "No student's Part B is complete yet, so there is nothing to put in the file.")
    lookups = job["lookups"]
    rows, part_b, problems = {}, {}, {}
    for r in chosen:
        data, row = job["data"][r["student_id"]]
        st = get_stage(stage)
        parts = {p.col: p.load(data.raw_parts.get(p.col)) for p in st.PARTS if p.col in ("part_b", "part_c")}
        _, grid_values, _ = sync.grid_state(stage, parts, row, lookups, job.get("typed"))
        rows[r["student_id"]] = row
        part_b[r["student_id"]] = template.part_b_view(stage, {**row, **grid_values}, lookups, labels)
        found = list(r["other_problems"])
        if not r["ready"]:
            found = [f"PART B NOT READY: {p}" for p in r["part_b_problems"]] + found
        problems[r["student_id"]] = [template.short_problems(stage, found)]
    students = [{"student_id": r["student_id"], "student_name": r["student_name"]} for r in chosen]
    in_file = {r["student_id"] for r in chosen}
    summary = {"generated_at": _now(), "ready_as_of": job["finished_at"],
               "settings_saved_at": (job.get("settings") or {}).get("saved_at"),
               "classes": ", ".join(sorted({f"{r['grade']} {r['section']}".strip() for r in results})),
               "included_count": len(chosen), "excluded_count": len(results) - len(chosen),
               "rule": "All students (not-ready ones are marked)" if include_all else RULE,
               "students": [{"student_id": r["student_id"], "in_file": r["student_id"] in in_file, "ready": r["ready"],
                             "part_b_problems": r["part_b_problems"], "other_problems": r["other_problems"][:10]}
                            for r in results]}
    template.build(path, stage, students, rows, lookups, settings, class_settings.marks_subjects(stage),
                   class_settings.is_setting_key, part_b, problems, summary)
    from backend.services import audit
    audit.record(f"teacher:{teacher.id}", "download_template", "class_template", stage, None,
                 {"students": sorted(in_file), "include_all": include_all})
    return path
