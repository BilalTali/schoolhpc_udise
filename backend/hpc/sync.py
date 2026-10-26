"""
Read students from the portal and write workbook values back, part by part.

For one student, sync does what a teacher does in the browser:
  1. read every part's current data from the portal,
  2. put the workbook values into it,
  3. run each part's own checks and calculations (see stages/),
  4. save A1 -> A2 -> ... -> C with "Continue", then HPC Credit with "Mark as Complete",
  5. read the student back and confirm the portal now says COMPLETED.
Nothing is written for a student whose workbook row has errors.
"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from backend.hpc.portal import STAGES as STAGE_NAMES, Portal, PortalError, stage_code
from backend.hpc.stages import activity_grid, get_stage
from backend.hpc.stages.common import Lookups, StudentContext


@dataclass
class StudentData:
    """Everything the portal holds for one student."""
    student_id: str
    record: Dict[str, Any]                 # GET without hpc_col
    raw_parts: Dict[str, Any]              # hpc_col -> formdata as stored

    @property
    def current_part(self) -> str:
        return str(self.record.get("current_part") or "")


@dataclass
class SyncResult:
    student_id: str
    name: str
    status: str                            # COMPLETED | INVALID | FAILED | SKIPPED | READY (dry run)
    errors: List[str] = field(default_factory=list)
    saved_parts: List[str] = field(default_factory=list)
    stage: str = ""
    changes: List[str] = field(default_factory=list)   # dry run: what a save would change on PARAKH (field names)


def fetch_student(portal: Portal, stage: str, student_id: str) -> StudentData:
    """The student's record and every part, read in parallel (the portal answers each in about 2 s)."""
    cols = [p.col for p in get_stage(stage).PARTS]
    with ThreadPoolExecutor(max_workers=len(cols) + 1) as pool:
        record = pool.submit(portal.student, stage, student_id)
        parts = {c: pool.submit(portal.student, stage, student_id, c) for c in cols}
        raw = {c: f.result().get("formdata") for c, f in parts.items()}
        return StudentData(str(student_id), record.result(), raw)


def fetch_students(portal: Portal, stage: str, student_ids: List[str], workers: int = 6,
                   on_each: Callable[[], None] = lambda: None) -> List[StudentData]:
    def one(sid):
        data = fetch_student(portal, stage, sid)
        on_each()                                  # progress: one more student read
        return data
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, student_ids))


def to_row(stage: str, data: StudentData, lookups: Lookups) -> Dict[str, Any]:
    """Current portal values as workbook cells: {field key: value}."""
    row = {}
    for part in get_stage(stage).PARTS:
        fd = part.load(data.raw_parts.get(part.col))
        for f in part.fields(lookups):
            row[f.key] = f.read(fd)
    return row


def build_payloads(stage: str, data: StudentData, row: Dict[str, Any], lookups: Lookups,
                   resolve: Optional[activity_grid.Resolver] = None):
    """Returns (payloads in save order, errors). Pure: does not touch the portal.
    `resolve` finds the activities the Activities grid may add (default: PARAKH's bank lists)."""
    st = get_stage(stage)
    errors: List[str] = []
    parts = {}
    for part in st.PARTS:
        fd = part.load(data.raw_parts.get(part.col))
        for f in part.fields(lookups):
            # A column missing from the workbook keeps the portal's value - but is still checked.
            err = f.write(fd, row[f.key] if f.key in row else f.read(fd))
            if err:
                errors.append(f"{part.title}: {err}")
        parts[part.col] = fd

    part_b = next(p for p in st.PARTS if p.code == "B")
    grid_errors = apply_activity_grid(stage, parts, row, lookups, resolve or activity_grid.resolver_from_lookups(lookups))
    errors += [f"{part_b.title}: {e}" for e in grid_errors]

    ctx = StudentContext(record=data.record, lookups=lookups, parts=parts)
    payloads = []
    for i, part in enumerate(st.PARTS):
        fd = parts[part.col]
        extra, part_errors = part.finish(fd, ctx)
        if part is part_b and grid_errors:
            part_errors = []          # the grid's messages already say what to fix; the rest would repeat them
        errors += [f"{part.title}: {e}" for e in part_errors]
        last = i == len(st.PARTS) - 1
        payload = {
            "hpc_col": part.col,
            "current_part": "mc" if last else st.PARTS[i + 1].code,
            "formdata": json.dumps(fd, ensure_ascii=False, separators=(",", ":")) if part.as_json_string else copy.deepcopy(fd),
            **extra,
        }
        if last:
            payload["hpc_status"] = "COMPLETED"
        payloads.append(payload)
    return payloads, errors


def part_c_levels(stage: str, parts: Dict[str, Any], lookups: Lookups) -> Dict[str, str]:
    """The student's Part C levels per subject, as grid values (used when the grid has none)."""
    st = get_stage(stage)
    part_c = next(p for p in st.PARTS if p.code == "C")
    fields = {f.key: f for f in part_c.fields(lookups)}
    fd = parts.get(part_c.col)
    if fd is None:
        fd = part_c.load(None)
    out = {}
    for s in st.DOMAINS:
        for ability, short in activity_grid.ABILITIES:
            f = fields.get(f"c_{s}_{ability}") or fields.get(f"c_{s}_{short}")
            level = str(f.read(fd) if f else "").strip()
            if level in activity_grid.LEVEL_TO_PORTAL:
                out[activity_grid.level_key(s, ability)] = level
    return out


def grid_state(stage: str, parts: Dict[str, Any], row: Dict[str, Any], lookups: Lookups,
               typed: Optional[Dict[str, str]] = None):
    """(current PARAKH activities, grid values to use, where each value came from). `typed` names the
    activities made in this app, which a card holds without a bank id."""
    st = get_stage(stage)
    part_b = next(p for p in st.PARTS if p.code == "B")
    now = activity_grid.current(st.DOMAINS, parts[part_b.col], typed)
    draft = {k: row[k] for k in activity_grid.grid_keys(st.DOMAINS) if k in row}
    values, source = activity_grid.effective(st.DOMAINS, now, draft, part_c_levels(stage, parts, lookups))
    return now, values, source


def apply_activity_grid(stage: str, parts: Dict[str, Any], row: Dict[str, Any], lookups: Lookups,
                        resolve: activity_grid.Resolver) -> List[str]:
    """Rebuilds Part B from the grid when the grid differs from PARAKH, or when an activity on the card was
    edited in the library since; otherwise leaves it exactly as it is."""
    st = get_stage(stage)
    part_b = next(p for p in st.PARTS if p.code == "B")
    now, values, _ = grid_state(stage, parts, row, lookups, activity_grid.typed_keys(resolve))
    replace = str(values.get(activity_grid.REPLACE_KEY, "")).lower() in ("yes", "true", "1")
    unchanged = all(values[k] == now.values.get(k, "") for k in values if k != activity_grid.REPLACE_KEY)
    if now.existing and unchanged and not replace and not activity_grid.stale_texts(parts[part_b.col], now, resolve):
        return []
    return activity_grid.apply(st.DOMAINS, dict(zip(st.DOMAINS, st.SUBJECTS)), st.ACTIVITY_GRID, parts[part_b.col], values, resolve)


GENDERS = {"MALE": "Male", "FEMALE": "Female", "BOY": "Male", "GIRL": "Female", "OTHER": "Other", "TRANSGENDER": "Other"}


def add_details(student: Dict[str, Any], record: Dict[str, Any]) -> None:
    """Fills gender and admission number from a student's full record (the roster list lacks them)."""
    stu = record.get("stu_info") or {}
    student["gender"] = GENDERS.get(str(stu.get("gender") or "").strip().upper(), "")
    student["admission_number"] = stu.get("school_admission_number", "")


def roster_with_details(portal: Portal, stage: str, lookups: Lookups, workers: int = 6) -> List[Dict[str, Any]]:
    """roster() plus gender and admission number (one extra read per student)."""
    students = roster(portal, stage, lookups)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(lambda s: portal.student(stage, s["student_id"]), students))
    for s, record in zip(students, records):
        add_details(s, record)
    return students


def roster(portal: Portal, stage: str, lookups: Lookups) -> List[Dict[str, Any]]:
    """The teacher's students for a stage, in the shape the workbook and the web app use."""
    out = []
    for r in portal.roster(stage):
        out.append({
            "student_id": str(r.get("id")),
            "student_name": (r.get("full_name") or f"{r.get('std_fname', '')} {r.get('std_lname', '')}").strip(),
            "hpc_login_id": r.get("std_reg_id", ""),
            "apaar_id": r.get("std_apaar_id", ""),
            "grade": next((g["grade_caption"] for g in lookups.grades if g["id"] == r.get("grade_id")), ""),
            "section": lookups.section_name(r.get("section_id")),
            "status": r.get("hpc_status") or "PENDING",
        })
    return out


def export_workbook(portal: Portal, stages: List[str], path,
                    on_students: Callable[[str, List["StudentData"]], None] = lambda stage, data: None,
                    on_roster: Callable[[str, List[Dict[str, Any]]], None] = lambda stage, students: None,
                    on_each: Callable[[str], None] = lambda stage: None):
    """
    Fetches every student's current HPC data for the given stages and writes one workbook.
    Returns (path, {stage: students}). on_roster gets each stage's class list as soon as it is read,
    on_each is called after every student's card, on_students gets each stage's cards (to keep them).
    """
    from backend.hpc import workbook
    sections, by_stage = [], {}
    for stage in stages:
        lookups = Lookups(portal, stage_code(stage))
        students = roster(portal, stage, lookups)
        on_roster(stage, students)
        data = fetch_students(portal, stage, [s["student_id"] for s in students], on_each=lambda stage=stage: on_each(stage))
        on_students(stage, data)
        for s, d in zip(students, data):
            add_details(s, d.record)
        rows = {d.student_id: to_row(stage, d, lookups) for d in data}
        for s, d in zip(students, data):
            s["grid_baseline"] = grid_baseline(stage, d, lookups)    # lets a download refresh the summary later
        sections.append(workbook.Section(stage, students, rows, lookups, activity_summaries={
            d.student_id: d_summary(stage, d, lookups) for d in data}))
        by_stage[stage] = students
    return workbook.build(sections, path), by_stage


def planned_changes(stage: str, data: StudentData, row: Dict[str, Any], payloads, lookups) -> List[str]:
    """The fields (by name, no values) a save would change on PARAKH, for the upload preview."""
    from backend.hpc.fields import _cell_text
    st = get_stage(stage)
    portal_row = to_row(stage, data, lookups)
    out = []
    for part, payload in zip(st.PARTS, payloads):
        if part.code == "B":
            stored = part.load(data.raw_parts.get(part.col))
            if payload["formdata"] != stored:
                out.append("Part B activities")
            continue
        for f in part.fields(lookups):
            if f.key in row and _cell_text(row[f.key]) != _cell_text(portal_row.get(f.key)):
                out.append(f"{part.code}: {f.label}")
    return out


def grid_baseline(stage: str, data: StudentData, lookups: Lookups) -> Dict[str, str]:
    """The Activities grid's values from what PARAKH holds (plus Part C levels where Part B has none)."""
    st = get_stage(stage)
    parts = {p.col: p.load(data.raw_parts.get(p.col)) for p in st.PARTS if p.col in ("part_b", "part_c")}
    _, values, _ = grid_state(stage, parts, {}, lookups)
    return values


def d_summary(stage: str, data: StudentData, lookups: Lookups) -> str:
    st = get_stage(stage)
    labels = {f"P{i}": lookups.activity_label(i) for i in lookups.activities}
    return activity_grid.summary_text(st.DOMAINS, dict(zip(st.DOMAINS, st.SUBJECTS)),
                                      grid_baseline(stage, data, lookups), labels)


def sync_workbook(portal: Portal, path, dry_run: bool = False, on_result=lambda result: None,
                  extra_values=lambda stage, student_id: {}, resolver_for=lambda stage: None,
                  before_save_for=lambda stage: None, base_values=lambda stage, student_id: {},
                  exception_problems: Optional[List[str]] = None,
                  on_step: Callable[[str, str], None] = lambda student_id, step: None) -> List[SyncResult]:
    """Checks, then uploads every student marked Sync=Yes, stage by stage. Calls on_result after each student.
    extra_values adds values kept outside the file (the Activities grid); resolver_for gives the activity list."""
    from backend.hpc import workbook
    rows = workbook.read(path, exception_problems)
    stages = workbook.detect_stages(path)
    only_stage = stages[0] if len(stages) == 1 else ""     # older one-stage files have no Stage column
    lookups: Dict[str, Lookups] = {}
    results = []
    for sid, row in rows.items():
        stage = str(row.get(workbook.STAGE_KEY) or only_stage)
        name = str(row.get(workbook.NAME_KEY) or sid)
        if not row.get(workbook.SYNC_KEY):
            result = SyncResult(sid, name, "SKIPPED", stage=stage)
        elif stage.lower() not in STAGE_NAMES:
            result = SyncResult(sid, name, "INVALID", [f"Students: unknown stage '{stage}'"], stage=stage)
        else:
            if stage not in lookups:
                lookups[stage] = Lookups(portal, stage_code(stage))
            # class settings under the file's values (an exception in the file wins); the dashboard's Part B on top
            row = {**base_values(stage, sid), **row, **extra_values(stage, sid)}
            result = sync_student(portal, stage, sid, row, lookups[stage], dry_run=dry_run, resolve=resolver_for(stage),
                                  before_save=before_save_for(stage), on_step=lambda step, sid=sid: on_step(sid, step))
        results.append(result)
        on_result(result)
    return results


def sync_student(portal: Portal, stage: str, student_id: str, row: Dict[str, Any],
                 lookups: Lookups, dry_run: bool = False, resolve: Optional[activity_grid.Resolver] = None,
                 before_save: Optional[Callable[[StudentData], Any]] = None,
                 on_step: Callable[[str], None] = lambda step: None,
                 data: Optional[StudentData] = None) -> SyncResult:
    """before_save keeps a copy of what PARAKH holds; nothing is written without one. on_step is told each
    step in plain words, for a live view. data: the card just read from PARAKH by the caller (not read twice)."""
    name = str(row.get("student_name") or student_id)
    try:
        if data is None:
            on_step("Reading the card from PARAKH")
            data = fetch_student(portal, stage, student_id)
        name = (data.record.get("stu_info") or {}).get("student_name") or name
        on_step("Checking the values")
        payloads, errors = build_payloads(stage, data, row, lookups, resolve)
        if errors:
            return SyncResult(student_id, name, "INVALID", errors, stage=stage)
        if dry_run:
            return SyncResult(student_id, name, "READY", stage=stage, changes=planned_changes(stage, data, row, payloads, lookups))
        if before_save is None:
            return SyncResult(student_id, name, "FAILED", ["Not saved: no copy of the current PARAKH values could be "
                                                           "kept first (no snapshot step was set up)."], stage=stage)
        try:
            on_step("Keeping a copy of the card before saving")
            before_save(data)
        except Exception as exc:
            return SyncResult(student_id, name, "FAILED", [f"Not saved: could not keep a copy of the current PARAKH "
                                                           f"values first ({exc})."], stage=stage)

        saved = []
        names = {p.col: ("HPC Credit" if p.code == "D" else f"Part {p.code}") for p in get_stage(stage).PARTS}
        for i, payload in enumerate(payloads, start=1):
            on_step(f"Saving {names.get(payload['hpc_col'], payload['hpc_col'])} ({i} of {len(payloads)})")
            portal.save_part(stage, student_id, payload)
            saved.append(payload["hpc_col"])
        on_step("Checking that PARAKH shows the card completed")

        remember = getattr(resolve, "remember", None)
        part_b = next((p for p in payloads if p["hpc_col"] == "part_b"), None)
        if remember and part_b is not None:
            remember(part_b["formdata"])             # which manual activities on this card are the app's own
        after = portal.student(stage, student_id)
        if after.get("current_part") != "mc":
            return SyncResult(student_id, name, "FAILED",
                              [f"Portal shows current part '{after.get('current_part')}' after saving, not 'mc'"], saved, stage)
        return SyncResult(student_id, name, "COMPLETED", [], saved, stage)
    except PortalError as exc:
        return SyncResult(student_id, name, "FAILED", [str(exc)], stage=stage)
