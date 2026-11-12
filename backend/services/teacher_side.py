"""
Students the School Register does not have (the school has no PARAKH school login, so it never fetched them; the
teacher fetched them with their own PARAKH sign-in). For them, what the register would give a card is kept on the
teacher's side instead - in the teacher's saved answers for each student (drafts), which every save to PARAKH uses:

  father's name  from the school's UDISE+ data (fetched on the School Register page), matched by APAAR ID, else
                 admission number, else name + date of birth; always the father (the HPC card shows "Father")
  missing fixes  names typed and days present / marks at random inside a range ("Fix what is missing")

Only empty answers are filled: what is on the PARAKH card or typed by the teacher stays.
"""
import random
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from backend.database import SessionLocal
from backend.hpc.stages import get_stage
from backend.models.register import RegisterStudent
from backend.services import card_store, class_settings, hpc_cards


def in_register(school_id: str, stage: str, parakh_ids: Iterable[str]) -> Set[str]:
    """The PARAKH ids of these students that the School Register has (the school's side handles them)."""
    ids = {str(i) for i in parakh_ids}
    if not ids or not school_id:
        return set()
    with SessionLocal() as db:
        rows = db.query(RegisterStudent.parakh_student_id).filter(
            RegisterStudent.school_id == school_id, RegisterStudent.stage == stage.capitalize(),
            RegisterStudent.parakh_student_id.in_(list(ids))).all()
    return {str(r[0]) for r in rows}


def _current(client, teacher_id: str, session: str, stage: str, ids: List[str], keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Each student's present answer for these keys: the teacher's draft, else the PARAKH card (as the app keeps it)."""
    st = get_stage(stage)
    wanted = set(keys)
    lookups = hpc_cards.lookups_for(f"teacher_{teacher_id}", client, stage)
    parts = [p for p in st.PARTS if any(f.key in wanted for f in p.fields(lookups))]
    raw, _ = card_store.class_parts(client, f"teacher_{teacher_id}", session, stage, ids, [p.col for p in parts], False) \
        if parts else ({i: {} for i in ids}, None)
    out: Dict[str, Dict[str, Any]] = {}
    for sid in ids:
        draft = (hpc_cards.load_draft(teacher_id, session, stage, sid) or {}).get("values") or {}
        now: Dict[str, Any] = {}
        for p in parts:
            fd = p.load(raw.get(sid, {}).get(p.col))
            for f in p.fields(lookups):
                if f.key in wanted:
                    now[f.key] = draft[f.key] if f.key in draft else f.read(fd)
        out[sid] = now
    return out


def _empty(v: Any) -> bool:
    return v is None or str(v).strip() in ("", "[]")


def udise_fathers(client, teacher, stage: str, students: List[Dict[str, Any]], session: Optional[str] = None) -> int:
    """For the teacher's students not in the School Register and without a parent's name on the card: the father's
    name from the school's UDISE+ data, into the teacher's saved answers. Returns how many were filled."""
    from backend.services import register_data
    session = session or client.ay
    outside = [s for s in students if str(s["student_id"]) not in in_register(teacher.school_id, stage,
                                                                              [s["student_id"] for s in students])]
    if not outside:
        return 0
    people = [SimpleNamespace(id=str(s["student_id"]), apaar_id=s.get("apaar_id") or "", admission_number=s.get("admission_number") or "",
                              student_name=s.get("student_name") or "", dob=s.get("dob") or "") for s in outside]
    try:
        found = register_data.udise_parents(teacher.school_id, people)
    except Exception:                                   # no UDISE+ data yet: nothing to fill
        return 0
    found = {sid: v["father"] for sid, v in found.items() if _ok_name(v.get("father"))}
    if not found:
        return 0
    now = _current(client, teacher.id, session, stage, list(found), ["a1_guardian_name"])
    filled = 0
    for sid, father in found.items():
        if _empty(now.get(sid, {}).get("a1_guardian_name")):
            hpc_cards.save_draft(teacher.id, session, stage, sid,
                                 {"a1_guardian_relation": "Father", "a1_guardian_name": " ".join(father.split())})
            filled += 1
    return filled


def _ok_name(name: Any) -> bool:
    from backend.services.register_data import NAME_MAX, NAME_RULE
    t = " ".join(str(name or "").split())
    return bool(t) and len(t) <= NAME_MAX and bool(NAME_RULE.match(t))


def fill_missing(client, teacher, stage: str, ids: List[str], names: Dict[str, Dict[str, str]],
                 attendance: Optional[Tuple[float, float]], marks: Optional[Tuple[int, int]]) -> Dict[str, Any]:
    """'Fix what is missing' for students not in the School Register: into the teacher's saved answers, only where
    empty. Numbers at random inside the range: days present as a % of each month's working days (the class
    settings), marks never above the subject's max marks."""
    import math
    session = client.ay
    settings = class_settings.for_teacher(teacher.id, stage, teacher.school_id)
    days = list(settings.get("working_days") or [None] * 12)
    maxes = settings.get("max_marks") or {}
    subjects = [n for n, _ in class_settings.marks_subjects(stage)]
    keys = ["a1_guardian_name"] + [f"a1_present_{i + 1}" for i in range(12)] + [f"d_{n}_obtained" for n in subjects]
    now = _current(client, teacher.id, session, stage, ids, keys)
    rng = random.Random()
    out = {"names": 0, "months": 0, "marks": 0, "problems": []}
    for sid in ids:
        values: Dict[str, Any] = {}
        given = names.get(sid)
        if given and _empty(now[sid].get("a1_guardian_name")):
            name = " ".join(str(given.get("name") or "").split())
            if _ok_name(name):
                values.update({"a1_guardian_relation": given.get("relation") or "Father", "a1_guardian_name": name})
                out["names"] += 1
            else:
                out["problems"].append(f"{sid}: letters, spaces, . ' - only (up to 50)")
        if attendance is not None:
            for i, wd in enumerate(days):
                key = f"a1_present_{i + 1}"
                if wd and _empty(now[sid].get(key)):
                    low, high = math.ceil(wd * attendance[0] / 100), math.floor(wd * attendance[1] / 100)
                    values[key] = rng.randint(min(low, high), max(low, high))
                    out["months"] += 1
        if marks is not None:
            for n in subjects:
                key = f"d_{n}_obtained"
                if _empty(now[sid].get(key)):
                    top = maxes.get(n) or class_settings.DEFAULT_MAX_MARKS
                    values[key] = rng.randint(min(marks[0], top), min(marks[1], top))
                    out["marks"] += 1
        if values:
            hpc_cards.save_draft(teacher.id, session, stage, sid, values)
    return out
