"""
The Activity Library: PARAKH's Activity Bank cached in our database, plus each school's own
names, edits, on/off switches and defaults, plus activities made in this app.

Who sees what
  portal_global   every school (one shared copy)
  portal_teacher  the teacher who owns it on PARAKH, and their school admin
  local           the school admin and the teacher who made it; the whole school once it is
                  shared ("school"); other schools only after the teacher consented to share
                  it AND the platform admin approved it ("community_ok")
Who may change what
  school admin    names, edits and on/off for every activity the school sees; defaults;
                  local activities of the school
  teacher         their own local activities (create, edit, share, delete); sync with their
                  own PARAKH session
Edits are stored in our database only. Nothing here writes to the portal.
"""
import copy
import hashlib
import html
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.hpc.portal import Portal, PortalError
from backend.hpc.stages import get_stage
from backend.models.library import (
    SHARE_STATES, ActivitySyncJob, AuditLog, LibraryActivity, SchoolActivitySetting, StageActivityDefault,
    TeacherActivityEdit,
)

STAGES = ("Foundational", "Preparatory", "Middle")
PAGE_SIZE = 100                    # PARAKH refuses more than 100 per page for "My activities"
MAX_PAGES = 100
MIN_INTERVAL = 0.5                 # at most two portal requests a second
RETRIES = 3
MAX_TEXT = 10000
CONSENT_TEXT = ("I made this activity myself, it contains no student's personal information, and I agree "
                "that other teachers using this app may use, copy and adapt it. I can stop sharing at any time; "
                "copies already made stay with their users.")
LEVELS = ("beginner", "proficient", "advanced")
APPROACHES = {"Art-Integrated": 1, "Sports-Integrated": 2, "Toy-Based": 3, "Technology-Integrated": 4, "Any Other": 5}  # Middle
ABILITIES = ("awareness", "sensitivity", "creativity")
_RUBRIC_KEY = {"awareness": "awr", "sensitivity": "sen", "creativity": "cre"}
_sleep = time.sleep                # replaced in tests


# ---------------------------------------------------------------------------
# Callers
# ---------------------------------------------------------------------------

@dataclass
class Actor:
    role: str                      # SCHOOL_ADMIN | TEACHER
    id: str
    school_id: str
    name: str = ""

    @property
    def key(self) -> str:
        return f"{self.role.lower()}:{self.id}"

    @property
    def is_admin(self) -> bool:
        return self.role == "SCHOOL_ADMIN"


def actor_from(current_user: Dict[str, Any]) -> Actor:
    user = current_user["user"]
    name = getattr(user, "teacher_name", None) or getattr(user, "admin_name", None) or ""
    return Actor(current_user["role"], user.id, current_user["school_id"], name)


def audit(db: Session, actor: Optional[Actor], action: str, entity: str, entity_id: Optional[str],
          before: Any = None, after: Any = None, school_id: Optional[str] = None) -> None:
    db.add(AuditLog(actor=actor.key if actor else "sync", actor_name=None,          # IDs only in logs
                    school_id=school_id or (actor.school_id if actor else None), entity=entity,
                    entity_id=entity_id, action=action, before=before, after=after))


# ---------------------------------------------------------------------------
# Stage subjects
# ---------------------------------------------------------------------------

def check_stage(stage: str) -> str:
    name = (stage or "").strip().capitalize()
    if name not in STAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown stage '{stage}'. Use one of {', '.join(STAGES)}.")
    return name


def stage_subjects(stage: str) -> List[Dict[str, str]]:
    st = get_stage(stage)
    return [{"code": c, "name": n} for c, n in zip(st.DOMAINS, st.SUBJECTS)]


def _subject_names(stage: str) -> Dict[str, str]:
    return {s["code"]: s["name"] for s in stage_subjects(stage)}


# ---------------------------------------------------------------------------
# Visibility and permissions
# ---------------------------------------------------------------------------

def can_view(actor: Actor, act: LibraryActivity) -> bool:
    if act.source == "portal_global":
        return True
    same_school = act.owner_school_id == actor.school_id
    if act.source == "portal_teacher":
        return same_school and (actor.is_admin or act.owner_teacher_id == actor.id)
    if act.share_state == "community_ok":
        return True
    if not same_school:
        return False
    return actor.is_admin or act.share_state != "private" or act.owner_teacher_id == actor.id


def can_edit_text(actor: Actor, act: LibraryActivity) -> bool:
    """PARAKH activities: anyone who sees them - the school admin edits the school's copy, a teacher their own
    (used for their students only). Made in this app: the owner (or the admin)."""
    if act.source != "local":
        return can_view(actor, act)
    if act.owner_school_id != actor.school_id:
        return False
    return actor.is_admin or (act.owner_teacher_id is not None and act.owner_teacher_id == actor.id)


def _visible_query(db: Session, actor: Actor, stage: str):
    return [a for a in db.query(LibraryActivity).filter(LibraryActivity.stage == stage).all() if can_view(actor, a)]


def get_visible(db: Session, actor: Actor, activity_id: str) -> LibraryActivity:
    act = db.get(LibraryActivity, activity_id)
    if not act or not can_view(actor, act):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Activity not found.")
    return act


def _forbid(message: str):
    raise HTTPException(status.HTTP_403_FORBIDDEN, message)


# ---------------------------------------------------------------------------
# The school's view of an activity
# ---------------------------------------------------------------------------

def _texts(content: Dict[str, Any]) -> Dict[str, Any]:
    """PARAKH's content layout -> the field names the web app uses."""
    desc = list(content.get("desc") or []) + ["", ""]
    rubric = {}
    for ability in ABILITIES:
        texts = list(content.get(_RUBRIC_KEY[ability]) or []) + ["", "", ""]
        rubric[ability] = dict(zip(LEVELS, (str(t or "") for t in texts[:3])))
    return {"activity_text": str(desc[0] or ""), "assessment_text": str(desc[1] or ""), "rubric": rubric,
            "goals": list(content.get("gl") or []), "competencies": list(content.get("cpt") or []),
            "approaches": list(content.get("approaches") or []), "approach_other": str(content.get("any-other") or "")}


def _apply_texts(content: Dict[str, Any], changes: Dict[str, Any]) -> Dict[str, Any]:
    """Web app field names -> PARAKH's content layout (on a copy)."""
    out = copy.deepcopy(content)
    desc = (list(out.get("desc") or []) + ["", ""])[:2]
    if "activity_text" in changes:
        desc[0] = changes["activity_text"]
    if "assessment_text" in changes:
        desc[1] = changes["assessment_text"]
    out["desc"] = desc
    for ability, levels in (changes.get("rubric") or {}).items():
        key = _RUBRIC_KEY[ability]
        texts = (list(out.get(key) or []) + ["", "", "", ""])[:4]
        for i, level in enumerate(LEVELS):
            if level in levels:
                texts[i] = levels[level]
        out[key] = texts
    for field, key in (("goals", "gl"), ("competencies", "cpt"), ("approaches", "approaches")):
        if field in changes:
            out[key] = list(changes[field])
    if "approach_other" in changes:
        out["any-other"] = changes["approach_other"]
    return out


def _mine(db: Session, actor: Actor, activity_id: str, create: bool = False) -> Optional[TeacherActivityEdit]:
    if actor.is_admin:
        return None
    row = db.query(TeacherActivityEdit).filter_by(teacher_id=actor.id, activity_id=activity_id).first()
    if row is None and create:
        row = TeacherActivityEdit(school_id=actor.school_id, teacher_id=actor.id, activity_id=activity_id)
        db.add(row)
        db.flush()
    return row


def _mine_for(db: Session, actor: Actor, ids: List[str]) -> Dict[str, TeacherActivityEdit]:
    if actor.is_admin or not ids:
        return {}
    rows = db.query(TeacherActivityEdit).filter(TeacherActivityEdit.teacher_id == actor.id,
                                                TeacherActivityEdit.activity_id.in_(ids)).all()
    return {r.activity_id: r for r in rows}


def _layers(setting: Optional[SchoolActivitySetting], mine: Optional[TeacherActivityEdit]):
    return (setting.edited if setting else None) or {}, (mine.edited if mine else None) or {}


def effective_content(act: LibraryActivity, setting: Optional[SchoolActivitySetting] = None,
                      mine: Optional[TeacherActivityEdit] = None) -> Dict[str, Any]:
    """The texts used for cards: PARAKH's original, then the school's edits, then the teacher's own."""
    if act.source == "local":
        return act.content or {}
    school, own = _layers(setting, mine)
    if not school and not own:
        return act.content or {}
    content = _apply_texts(act.content or {}, {k: v for k, v in school.items() if k != "subjects"})
    return _apply_texts(content, {k: v for k, v in own.items() if k != "subjects"})


def _setting(db: Session, school_id: str, activity_id: str, create: bool = False) -> Optional[SchoolActivitySetting]:
    row = db.query(SchoolActivitySetting).filter_by(school_id=school_id, activity_id=activity_id).first()
    if row is None and create:
        row = SchoolActivitySetting(school_id=school_id, activity_id=activity_id)
        db.add(row)
        db.flush()
    return row


def _settings_for(db: Session, school_id: str, ids: List[str]) -> Dict[str, SchoolActivitySetting]:
    if not ids:
        return {}
    rows = db.query(SchoolActivitySetting).filter(SchoolActivitySetting.school_id == school_id,
                                                  SchoolActivitySetting.activity_id.in_(ids)).all()
    return {r.activity_id: r for r in rows}


def default_id(db: Session, school_id: str, stage: str) -> Optional[str]:
    row = db.query(StageActivityDefault).filter_by(school_id=school_id, teacher_id=None, stage=stage).first()
    return row.activity_id if row else None


def view(act: LibraryActivity, setting: Optional[SchoolActivitySetting], actor: Actor,
         default: Optional[str] = None, mine: Optional[TeacherActivityEdit] = None) -> Dict[str, Any]:
    school_edits, my_edits = _layers(setting, mine)
    edited = {**school_edits, **my_edits}
    names = _subject_names(act.stage)
    all_codes = list(names)
    content = effective_content(act, setting, mine)
    if act.source == "local":
        subjects = list(act.subjects or [])
    else:
        # portal activities can be used for every subject
        subjects = list(my_edits.get("subjects") or school_edits.get("subjects") or all_codes)
    subjects = [c for c in all_codes if c in subjects]
    missing = [names[c] for c in all_codes if c not in subjects]
    texts = _texts(content)
    title = (setting.display_name if setting else None) or act.title or ""
    status_ = setting.status if setting else "active"
    portal_active = act.source == "local" or bool((act.original_snapshot or {}).get("is_active", True))
    ready = _portal_ready(act, content, subjects)
    usable, reason = True, ""
    if status_ != "active":
        usable, reason = False, "Turned off for your school."
    elif act.upstream_status == "removed":
        usable, reason = False, "No longer on PARAKH."
    elif not portal_active:
        usable, reason = False, "Turned off on PARAKH."
    elif act.source == "local" and not ready["ok"]:
        usable, reason = False, "Not finished yet - still needs: " + ", ".join(ready["missing"]) + "."
    elif act.has_pictures:
        usable, reason = False, "Has pictures - choose it on the PARAKH website instead."
    return {
        "id": act.id, "source": act.source, "stage": act.stage, "portal_id": act.portal_id,
        "code": act.code, "title": title,
        "label": f"{act.code} - {title}" if title and title != act.code else act.code,
        **texts,
        "subjects": subjects, "subject_names": [names[c] for c in subjects],
        "covers_all": not missing, "missing_subjects": missing,
        "portal_subjects": list(act.portal_subjects or []),
        "portal_subject_names": [names.get(c, c) for c in (act.portal_subjects or [])],
        "has_pictures": bool(act.has_pictures), "status": status_, "is_default": act.id == default,
        "edited": bool(edited), "edited_fields": sorted(edited),
        "edited_by_school": bool(school_edits), "edited_by_me": bool(my_edits),
        "modified": act.source != "local" and any(k != "subjects" for k in edited),
        "edit_scope": "activity" if act.source == "local" else ("school" if actor.is_admin else "me"),
        "can_reset": act.source != "local" and bool(school_edits if actor.is_admin else my_edits),
        "upstream_status": act.upstream_status, "removed_at": _iso(act.removed_at), "portal_active": portal_active,
        "last_synced_at": _iso(act.last_synced_at), "used_counter": act.used_counter, "tier": act.tier,
        "share_state": act.share_state if act.source == "local" else None,
        "is_mine": act.owner_teacher_id is not None and act.owner_teacher_id == actor.id,
        "usable_in_excel": usable, "not_usable_reason": reason,
        "can_edit": can_edit_text(actor, act), "can_manage": actor.is_admin,
        "can_delete": act.source == "local" and can_edit_text(actor, act),
        "version": act.version if act.source == "local" else (
            (setting.version if setting else 1) if actor.is_admin else (mine.version if mine else 1)),
        "portal_ready": ready,
    }


def _portal_ready(act: LibraryActivity, content: Dict[str, Any], subjects: List[str]) -> Dict[str, Any]:
    """What PARAKH's own activity form needs before an activity could be created there."""
    missing = []
    t = _texts(content)
    if not (act.title or act.code):
        missing.append("Activity name")
    if not subjects:
        missing.append("Subjects")
    if not t["goals"]:
        missing.append("Curricular goal")
    if not t["competencies"]:
        missing.append("Competency")
    if not t["activity_text"].strip():
        missing.append("Activity description")
    if not t["assessment_text"].strip():
        missing.append("Assessment")
    for ability in ABILITIES:
        if not all(t["rubric"][ability][lvl].strip() for lvl in LEVELS):
            missing.append(f"{ability.capitalize()} levels")
    if act.stage == "Middle":                       # the Middle page needs the teaching approach
        if not t["approaches"]:
            missing.append("Approach")
        elif 5 in t["approaches"] and not t["approach_other"].strip():
            missing.append("Approach (any other) text")
    return {"ok": not missing, "missing": missing}


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat(timespec="seconds") + "Z" if dt else None


def detail(db: Session, actor: Actor, act: LibraryActivity) -> Dict[str, Any]:
    setting = _setting(db, actor.school_id, act.id)
    out = view(act, setting, actor, default_id(db, actor.school_id, act.stage), _mine(db, actor, act.id))
    if act.source != "local":
        original = view(act, None, actor)
        out["original"] = {k: original[k] for k in ("activity_text", "assessment_text", "rubric", "goals",
                                                    "competencies", "subjects", "subject_names")}
        out["diff"] = _diff(original, out)
    history = (db.query(AuditLog).filter(AuditLog.entity_id == act.id, AuditLog.school_id == actor.school_id)
               .order_by(AuditLog.at.desc()).limit(20).all())
    out["history"] = [{"at": _iso(h.at), "who": _who(db, h.actor), "action": h.action} for h in history]
    return out


def _who(db: Session, actor: str) -> str:
    """A person's name for a history line, looked up now (audit rows keep IDs only)."""
    from backend.models.entities import School, Teacher
    role, _, uid = actor.partition(":")
    if role == "teacher":
        t = db.get(Teacher, uid)
        return t.teacher_name if t else "A teacher"
    if role == "school_admin":
        s = db.get(School, uid)
        return f"{s.admin_name} (school admin)" if s else "School admin"
    return "PARAKH sync" if actor == "sync" else "Someone"


_DIFF_LABELS = [("activity_text", "Activity description"), ("assessment_text", "Assessment"),
                ("subject_names", "Subjects covered"), ("goals", "Curricular goal"), ("competencies", "Competency")]


def _diff(original: Dict[str, Any], current: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = [{"field": f, "label": label, "original": original[f], "current": current[f]}
           for f, label in _DIFF_LABELS if original[f] != current[f]]
    for ability in ABILITIES:
        for level in LEVELS:
            a, b = original["rubric"][ability][level], current["rubric"][ability][level]
            if a != b:
                out.append({"field": f"rubric.{ability}.{level}", "original": a, "current": b,
                            "label": f"{ability.capitalize()} - {level.capitalize()}"})
    return out


# ---------------------------------------------------------------------------
# Listing and the Excel dropdown
# ---------------------------------------------------------------------------

def _code_key(code: str):
    """Natural order for codes like 'L1CG 1, C 1.10' (spacing ignored, numbers compared as numbers)."""
    flat = re.sub(r"\s+", "", code or "").upper()
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.findall(r"\d+|\D+", flat)]


def list_views(db: Session, actor: Actor, stage: str) -> List[Dict[str, Any]]:
    acts = _visible_query(db, actor, stage)
    settings = _settings_for(db, actor.school_id, [a.id for a in acts])
    mine = _mine_for(db, actor, [a.id for a in acts])
    default = default_id(db, actor.school_id, stage)
    views = [view(a, settings.get(a.id), actor, default, mine.get(a.id)) for a in acts]
    views.sort(key=lambda v: (not v["is_default"], _code_key(v["code"]), v["title"].lower(), v["id"]))
    return views


def filter_views(views: List[Dict[str, Any]], q: str = "", source: str = "", subject: str = "",
                 covers_all: Optional[bool] = None, status_: str = "", edited: Optional[bool] = None,
                 upstream: str = "", mine: Optional[bool] = None) -> List[Dict[str, Any]]:
    q = q.strip().lower()

    def keep(v):
        if q and not any(q in str(x).lower() for x in [v["code"], v["title"], *v["subject_names"], v["portal_id"] or ""]):
            return False
        if source and v["source"] != source:
            return False
        if subject and subject not in v["subjects"]:
            return False
        if covers_all is not None and v["covers_all"] != covers_all:
            return False
        if status_ and v["status"] != status_:
            return False
        if edited is not None and v["edited"] != edited:
            return False
        if upstream and v["upstream_status"] != upstream:
            return False
        if mine is not None and v["is_mine"] != mine:
            return False
        return True

    return [v for v in views if keep(v)]


def library_entries(db: Session, actor: Actor, stage: str) -> Dict[str, Dict[str, Any]]:
    """Grid key -> what a save needs to put the activity on a card. Texts are the ones used here: PARAKH's
    original with the school's and this teacher's edits ("modified" when they differ, so the card's copy is
    marked edited, as the PARAKH page does). Activities made in this app have no PARAKH id; they go on the
    card as a typed activity once finished. Turned-off or picture activities are not usable."""
    acts = _visible_query(db, actor, stage)
    settings = _settings_for(db, actor.school_id, [a.id for a in acts])
    mine = _mine_for(db, actor, [a.id for a in acts])
    out = {}
    for a in acts:
        v = view(a, settings.get(a.id), actor, mine=mine.get(a.id))
        caption = a.title if a.source == "local" else (a.original_snapshot or {}).get("activity_caption") or a.code
        out[_key(v)] = {"portal_id": a.portal_id, "caption": caption, "label": v["label"],
                        "content": effective_content(a, settings.get(a.id), mine.get(a.id)),
                        "is_global": a.source == "portal_global", "modified": v["modified"],
                        "usable": v["usable_in_excel"], "reason": v["not_usable_reason"], "key": _key(v)}
    return out


def resolver_for_teacher(teacher_id: str, stage: str, fallback=None):
    """A Part B activity resolver backed by the library (falls back to PARAKH's lists if never synced)."""
    from backend.models.entities import Teacher
    with SessionLocal() as db:
        t = db.get(Teacher, teacher_id)
        entries = library_entries(db, Actor("TEACHER", t.id, t.school_id, t.teacher_name), stage) if t else {}
    if not entries and fallback is None:
        return None                     # never synced: the save uses PARAKH's own lists

    def resolve(key: str):
        if key in entries:
            return entries[key]
        return fallback(key) if fallback and not entries else None
    own = [(k, e) for k, e in entries.items() if e["portal_id"] is None] + \
          [(k, e) for k, e in entries.items() if e["portal_id"] is not None and e["modified"]]
    resolve.typed = {}
    for k, e in own:                                 # made here first, then edited bank activities
        resolve.typed.setdefault(e["caption"], k)
    from backend.services import own_activities
    owner = f"teacher_{teacher_id}"
    resolve.owned = own_activities.load(owner)
    resolve.remember = lambda part_b: own_activities.remember(owner, part_b, resolve.typed)
    return resolve


def _key(v: Dict[str, Any]) -> str:
    prefix = {"portal_global": "P", "portal_teacher": "T"}.get(v["source"], "L")
    return f"{prefix}{v['portal_id']}" if v["portal_id"] is not None else f"L{v['id']}"


def dropdown_entries(db: Session, actor: Actor, stage: str) -> List[Dict[str, str]]:
    """What the workbook's activity dropdown offers: usable activities, default first, then by code.
    `key` is the stable id the workbook reader maps back to (P<portal id>, T<portal id>, L<uuid>)."""
    out = []
    for v in list_views(db, actor, stage):
        if v["usable_in_excel"]:
            key = _key(v)
            out.append({"key": key, "label": f"{v['label']} (#{key})", "activity_id": v["id"]})
    return out


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------

def _clean_text(value: Any, label: str, limit: int = MAX_TEXT) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if len(text) > limit:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{label} is too long ({len(text)} characters, up to {limit}).")
    return text


def _clean_changes(stage: str, changes: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for f, label in (("activity_text", "Activity description"), ("assessment_text", "Assessment")):
        if f in changes and changes[f] is not None:
            out[f] = _clean_text(changes[f], label)
    if changes.get("rubric") is not None:
        rubric = {}
        for ability, levels in changes["rubric"].items():
            if ability not in ABILITIES:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown ability '{ability}'.")
            rubric[ability] = {lvl: _clean_text(levels[lvl], f"{ability} {lvl}") for lvl in LEVELS if lvl in levels}
        out["rubric"] = rubric
    for f in ("goals", "competencies"):
        if changes.get(f) is not None:
            out[f] = [_clean_text(x, f, 60) for x in changes[f] if str(x or "").strip()]
    if changes.get("approaches") is not None:
        try:
            approaches = sorted({int(x) for x in changes["approaches"]})
        except (TypeError, ValueError):
            approaches = [0]
        if any(x not in APPROACHES.values() for x in approaches):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown approach.")
        out["approaches"] = approaches
    if changes.get("approach_other") is not None:
        out["approach_other"] = _clean_text(changes["approach_other"], "Approach (any other)", 500)
    if changes.get("subjects") is not None:
        known = [s["code"] for s in stage_subjects(stage)]
        chosen = [c for c in known if c in set(changes["subjects"])]
        unknown = set(changes["subjects"]) - set(known)
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown subject(s) for {stage}: {', '.join(sorted(unknown))}.")
        if not chosen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose at least one subject.")
        out["subjects"] = chosen
    return out


def known_codes(db: Session, actor: Actor, stage: str) -> Dict[str, List[Dict[str, Any]]]:
    """Curricular goal and competency codes PARAKH's own activities use for this stage (PARAKH has no
    list of its own we can read), with how many activities use each - what a new activity may pick from."""
    goals: Dict[str, int] = {}
    competencies: Dict[str, int] = {}
    for a in _visible_query(db, actor, stage):
        if a.source == "local":
            continue
        for code in (a.content or {}).get("gl") or []:
            goals[str(code)] = goals.get(str(code), 0) + 1
        for code in (a.content or {}).get("cpt") or []:
            competencies[str(code)] = competencies.get(str(code), 0) + 1
    as_list = lambda d: [{"code": c, "used_by": n} for c, n in sorted(d.items(), key=lambda kv: _code_key(kv[0]))]
    return {"goals": as_list(goals), "competencies": as_list(competencies)}


def _check_codes(db: Session, actor: Actor, stage: str, clean: Dict[str, Any]) -> None:
    """Goal and competency codes must be ones PARAKH uses, or the card would carry a code it does not know."""
    if "goals" not in clean and "competencies" not in clean:
        return
    known = known_codes(db, actor, stage)
    for field, label in (("goals", "Curricular goal"), ("competencies", "Competency")):
        allowed = {c["code"] for c in known[field]}
        unknown = [c for c in clean.get(field) or [] if allowed and c not in allowed]
        if unknown:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"{label} code(s) not used by any PARAKH activity for {stage}: {', '.join(unknown)}. "
                                "Pick from the list.")


def create_local(db: Session, actor: Actor, stage: str, title: str, changes: Dict[str, Any],
                 share: str = "", consent: bool = False) -> LibraryActivity:
    title = _clean_text(title, "Activity name", 200)
    if not title:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Give the activity a name.")
    clean = _clean_changes(stage, {"subjects": [s["code"] for s in stage_subjects(stage)], **changes})
    _check_codes(db, actor, stage, clean)
    act = LibraryActivity(source="local", stage=stage, code=title, title=title,
                          content=_apply_texts({}, {k: v for k, v in clean.items() if k != "subjects"}),
                          subjects=clean["subjects"], owner_school_id=actor.school_id,
                          owner_teacher_id=None if actor.is_admin else actor.id,
                          share_state="school" if actor.is_admin else "private",
                          created_by=actor.key, updated_by=actor.key)
    db.add(act)
    db.flush()
    audit(db, actor, "create", "activity", act.id, after={"title": title, "stage": stage})
    if share:
        set_share(db, actor, act, share, consent)
    return act


def update(db: Session, actor: Actor, act: LibraryActivity, changes: Dict[str, Any], version: Optional[int]) -> None:
    display_name = changes.pop("display_name", None)
    new_status = changes.pop("status", None)
    title = changes.pop("title", None)
    clean = _clean_changes(act.stage, changes)
    _check_codes(db, actor, act.stage, clean)
    if (clean or title is not None) and not can_edit_text(actor, act):
        _forbid("Only the school admin, or the teacher who made this activity, can change it.")
    if (display_name is not None or new_status is not None) and not actor.is_admin:
        _forbid("Only the school admin can rename activities or turn them on or off.")

    if act.source == "local":
        if version is not None and version != act.version:
            raise HTTPException(status.HTTP_409_CONFLICT, "Someone else changed this activity. Reload it to see their changes.")
        before = {"title": act.title, **_texts(act.content), "subjects": act.subjects}
        if title is not None and _clean_text(title, "Activity name", 200) not in ("", act.title):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "The name cannot be changed once the activity is made: students' cards find it by its name. "
                                "You can still change everything else, or make a copy under a new name.")
        if clean:
            act.content = _apply_texts(act.content or {}, {k: v for k, v in clean.items() if k != "subjects"})
            if "subjects" in clean:
                act.subjects = clean["subjects"]
        if clean or title is not None:
            act.version += 1
            act.updated_by = actor.key
            audit(db, actor, "edit", "activity", act.id, before, {"title": act.title, **_texts(act.content),
                                                                  "subjects": act.subjects})
    if act.source != "local" and not actor.is_admin:
        if clean:                                   # a teacher's own version, for their students only
            mine = _mine(db, actor, act.id, create=True)
            if version is not None and version != mine.version:
                raise HTTPException(status.HTTP_409_CONFLICT, "This activity changed in another tab. Reload it to see the changes.")
            school = _texts(effective_content(act, _setting(db, actor.school_id, act.id)))
            before = mine.edited
            mine.edited = _store_edits(act, _merge_edits(mine.edited or {}, clean), school)
            mine.version += 1
            audit(db, actor, "edit_own", "activity", act.id, {"edited": before}, {"edited": mine.edited})
        return
    setting = _setting(db, actor.school_id, act.id, create=True)
    if act.source != "local" and version is not None and version != setting.version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Someone else changed this activity. Reload it to see their changes.")
    before = {"display_name": setting.display_name, "status": setting.status, "edited": setting.edited}
    changed = False
    if act.source != "local" and clean:
        setting.edited = _store_edits(act, _merge_edits(setting.edited or {}, clean))
        changed = True
    if display_name is not None:
        setting.display_name = _clean_text(display_name, "Display name", 120) or None
        changed = True
    if new_status is not None:
        if new_status not in ("active", "disabled"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Status must be 'active' or 'disabled'.")
        setting.status = new_status
        changed = True
        if new_status == "disabled":
            _clear_default_if(db, actor, act)
    if changed:
        setting.version += 1
        setting.updated_by = actor.key
        only_status = new_status is not None and not clean and display_name is None
        audit(db, actor, "status" if only_status else "edit", "activity", act.id,
              before, {"display_name": setting.display_name, "status": setting.status, "edited": setting.edited})


def _merge_edits(stored: Dict[str, Any], clean: Dict[str, Any]) -> Dict[str, Any]:
    """New edits on top of earlier ones; rubric texts are merged level by level."""
    out = {**copy.deepcopy(stored), **{k: v for k, v in clean.items() if k != "rubric"}}
    if "rubric" in clean:
        rubric = out.setdefault("rubric", {})
        for ability, levels in clean["rubric"].items():
            rubric[ability] = {**rubric.get(ability, {}), **levels}
    return out


def _store_edits(act: LibraryActivity, edits: Dict[str, Any], base: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Keeps only edits that differ from the base (the portal original, or for a teacher the school's
    version); an edit back to the base disappears."""
    original = base or _texts(act.content or {})
    out: Dict[str, Any] = {}
    for key, value in edits.items():
        if key == "rubric":
            merged = {a: {**original["rubric"][a], **(value.get(a) or {})} for a in ABILITIES}
            diff = {a: {l: merged[a][l] for l in LEVELS if merged[a][l] != original["rubric"][a][l]} for a in ABILITIES}
            diff = {a: lv for a, lv in diff.items() if lv}
            if diff:
                out["rubric"] = diff
        elif key == "subjects":
            if sorted(value) != sorted(s["code"] for s in stage_subjects(act.stage)):
                out["subjects"] = value
        elif original.get(key) != value:
            out[key] = value
    return out or None


def reset(db: Session, actor: Actor, act: LibraryActivity) -> None:
    """Admin: the school's edits go. Teacher: their own edits go (back to the school's version)."""
    if act.source == "local":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This activity was made in this app, so there is no original to go back to.")
    if not actor.is_admin:
        mine = _mine(db, actor, act.id)
        if mine and mine.edited:
            audit(db, actor, "reset_own", "activity", act.id, before={"edited": mine.edited}, after={"edited": None})
            mine.edited = None
            mine.version += 1
        return
    setting = _setting(db, actor.school_id, act.id)
    if setting and setting.edited:
        audit(db, actor, "reset", "activity", act.id, before={"edited": setting.edited}, after={"edited": None})
        setting.edited = None
        setting.version += 1
        setting.updated_by = actor.key


def duplicate(db: Session, actor: Actor, act: LibraryActivity) -> LibraryActivity:
    v = view(act, _setting(db, actor.school_id, act.id), actor, mine=_mine(db, actor, act.id))
    changes = {k: v[k] for k in ("activity_text", "assessment_text", "rubric", "goals", "competencies", "subjects",
                                 "approaches", "approach_other")}
    copy_ = create_local(db, actor, act.stage, f"Copy of {v['label']}"[:200], changes)
    audit(db, actor, "duplicate", "activity", copy_.id, before={"from": act.id})
    return copy_


def delete_local(db: Session, actor: Actor, act: LibraryActivity) -> None:
    if act.source != "local":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Activities from PARAKH cannot be deleted. Turn them off instead.")
    if not can_edit_text(actor, act):
        _forbid("Only the school admin, or the teacher who made this activity, can delete it.")
    audit(db, actor, "delete", "activity", act.id, before={"title": act.title, "stage": act.stage})
    db.query(StageActivityDefault).filter_by(activity_id=act.id).update({"activity_id": None})
    db.delete(act)


def set_share(db: Session, actor: Actor, act: LibraryActivity, level: str, consent: bool) -> None:
    """Sharing more widely needs the maker's consent (stored with its wording); narrowing is always allowed."""
    if act.source != "local" or not can_edit_text(actor, act):
        _forbid("Only the teacher who made this activity (or the school admin) can change who it is shared with.")
    if level not in ("private", "school", "community"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Share with 'private', 'school' or 'community'.")
    order = {s: i for i, s in enumerate(SHARE_STATES)}
    current = "community" if act.share_state == "community_ok" else act.share_state
    if level == current:
        return
    widening = order[level] > order[current]
    teacher_made = act.owner_teacher_id is not None
    if widening and teacher_made and actor.id != act.owner_teacher_id:
        _forbid("Only the teacher who made this activity can choose to share it more widely.")
    if widening and (teacher_made or level == "community") and not consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Please agree to the sharing terms first.")
    before = act.share_state
    if widening:
        act.share_consent_at, act.share_consent_by, act.share_consent_text = datetime.utcnow(), actor.key, CONSENT_TEXT
    act.share_state = level
    audit(db, actor, "share", "activity", act.id, before={"share_state": before}, after={"share_state": level})


def set_default(db: Session, actor: Actor, stage: str, activity_id: Optional[str], confirm_partial: bool) -> Dict[str, Any]:
    if not actor.is_admin:
        _forbid("Only the school admin can choose the default activity.")
    row = db.query(StageActivityDefault).filter_by(school_id=actor.school_id, teacher_id=None, stage=stage).first()
    before = row.activity_id if row else None
    covers = True
    if activity_id:
        act = get_visible(db, actor, activity_id)
        if act.stage != stage:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"That activity belongs to the {act.stage} stage.")
        v = view(act, _setting(db, actor.school_id, act.id), actor)
        if not v["usable_in_excel"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"It cannot be the default: {v['not_usable_reason']}")
        covers = v["covers_all"]
        if not covers and not confirm_partial:
            raise HTTPException(status.HTTP_409_CONFLICT, {
                "message": "This activity does not cover every subject of the stage.",
                "missing_subjects": v["missing_subjects"]})
    if row is None:
        row = StageActivityDefault(school_id=actor.school_id, teacher_id=None, stage=stage)
        db.add(row)
    row.activity_id, row.covers_all_confirmed, row.updated_by = activity_id, covers, actor.key
    audit(db, actor, "set_default", "stage_default", activity_id, before={"stage": stage, "activity_id": before},
          after={"stage": stage, "activity_id": activity_id})
    return {"stage": stage, "activity_id": activity_id, "covers_all": covers}


def _clear_default_if(db: Session, actor: Actor, act: LibraryActivity) -> None:
    row = db.query(StageActivityDefault).filter_by(school_id=actor.school_id, teacher_id=None,
                                                   stage=act.stage, activity_id=act.id).first()
    if row:
        row.activity_id = None
        audit(db, actor, "clear_default", "stage_default", act.id, before={"stage": act.stage, "activity_id": act.id})


# ---------------------------------------------------------------------------
# Sync from PARAKH (read-only)
# ---------------------------------------------------------------------------

class _Throttle:
    def __init__(self, interval: float = MIN_INTERVAL):
        self.interval, self.last = interval, 0.0

    def wait(self):
        delay = self.last + self.interval - time.monotonic()
        if delay > 0:
            _sleep(delay)
        self.last = time.monotonic()


def _call(throttle: _Throttle, fn: Callable, *args) -> Any:
    """A portal read with throttling and retries (1 s, 2 s, 4 s). An expired session or a refused
    request (HTTP 4xx) is not retried - asking again would get the same answer."""
    last: Exception = PortalError("no attempt made")
    for attempt in range(RETRIES):
        throttle.wait()
        try:
            return fn(*args)
        except PortalError as exc:
            if "expired" in str(exc) or "does not allow" in str(exc) or re.search(r"HTTP 4\d\d", str(exc)):
                raise
            last = exc
        except requests.RequestException as exc:
            last = exc
        _sleep(2 ** attempt)
    raise PortalError(f"PARAKH did not answer after {RETRIES} tries ({last}).")


def _all_pages(throttle: _Throttle, fetch: Callable[[int], Dict[str, Any]], on_page: Callable[[int], None]) -> List[Dict[str, Any]]:
    records, seen = [], set()
    for page_no in range(1, MAX_PAGES + 1):
        on_page(page_no)
        data = _call(throttle, fetch, page_no)
        page = data.get("records") or []
        new = [r for r in page if r.get("id") not in seen]
        seen.update(r.get("id") for r in new)
        records.extend(new)
        total = data.get("count") or data.get("total_count")
        if not new or len(page) < PAGE_SIZE or (total and len(records) >= int(total)):
            return records
    raise PortalError(f"PARAKH kept returning pages after {MAX_PAGES} pages; the sync was stopped to be safe.")


def _plain(text: Any) -> str:
    """PARAKH stores some captions HTML-escaped, sometimes twice ('Dance &amp;amp; Movement')."""
    text = str(text or "")
    for _ in range(3):
        text, before = html.unescape(text), text
        if text == before:
            break
    return " ".join(text.split())


def _normalise(rec: Dict[str, Any], subject_codes: Dict[int, str]) -> Dict[str, Any]:
    try:
        content = json.loads(rec.get("activity_data_json") or "{}")
    except ValueError:
        content = {}
    dt = content.get("dt") or {}
    snapshot = {k: rec.get(k) for k in ("id", "activity_caption", "hpc_stage", "grade_id", "domain_ids", "is_active",
                                        "created_on", "activity_data_json")}
    return {
        "portal_id": int(rec["id"]), "code": _plain(rec.get("activity_caption"))[:200] or f"#{rec['id']}",
        "content": dt, "portal_subjects": [subject_codes[i] for i in rec.get("domain_ids") or [] if i in subject_codes],
        "grade_id": rec.get("grade_id"), "has_pictures": any(str(x or "").strip() for x in dt.get("img") or []),
        "used_counter": rec.get("used_counter"), "snapshot": snapshot,
        # used_counter changes all the time, so it is left out of the change check
        "hash": hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    }


_start_lock = threading.Lock()          # the "already running?" check and the new job happen together (L-1)


def start_sync(db: Session, actor: Actor, stages: List[str], started_by: Optional[str] = None) -> Tuple[ActivitySyncJob, bool]:
    """Returns (job, already_running). One sync per school at a time."""
    with _start_lock:
        db.expire_all()                     # see a job another request has just committed
        running = (db.query(ActivitySyncJob).filter(ActivitySyncJob.school_id == actor.school_id,
                                                    ActivitySyncJob.status.in_(("QUEUED", "RUNNING")))
                   .order_by(ActivitySyncJob.created_at.desc()).first())
        if running:
            return running, True
        job = ActivitySyncJob(school_id=actor.school_id, stages=",".join(stages), started_by=started_by or actor.key,
                              step="Waiting to start", progress=0)
        db.add(job)
        db.commit()
        return job, False


def run_sync(job_id: str, client: Portal, actor: Actor, with_my_activities: bool) -> None:
    """Background task. Reads everything first; writes in one transaction only if every read worked."""
    db = SessionLocal()
    try:
        job = db.get(ActivitySyncJob, job_id)
        stages = job.stages.split(",")
        throttle = _Throttle()
        calls_per_stage = 2 + (1 if with_my_activities else 0)
        done = 0

        def step(text: str):
            job.status, job.step = "RUNNING", text
            job.progress = min(90, int(done / (len(stages) * calls_per_stage) * 90))
            db.commit()

        fetched: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for stage in stages:
            step(f"Reading the {stage} subjects from PARAKH")
            cats = _call(throttle, client.activity_categories, stage)
            codes = {int(c["id"]): c.get("ent_code") for c in cats if str(c.get("id", "")).isdigit()}
            done += 1
            step(f"Reading {stage} activities from PARAKH")
            global_recs = _all_pages(throttle, lambda p: client.activity_bank_page(p, PAGE_SIZE, stage),
                                     lambda p: step(f"Reading {stage} activities from PARAKH (page {p})"))
            global_recs = [r for r in global_recs if str(r.get("hpc_stage", "")).upper() == stage.upper()]
            done += 1
            mine: List[Dict[str, Any]] = []
            if with_my_activities:
                step(f"Reading your own {stage} activities from PARAKH")
                mine = _all_pages(throttle, lambda p: client.my_activities_page(stage, p, PAGE_SIZE), lambda p: None)
                done += 1
            fetched[stage] = {"portal_global": [_normalise(r, codes) for r in global_recs],
                              "portal_teacher": [_normalise(r, codes) for r in mine]}

        step("Saving to the library")
        counts = _apply(db, actor, fetched, with_my_activities)
        job.status, job.step, job.progress, job.counts = "COMPLETED", "Done", 100, counts
        job.finished_at = datetime.utcnow()
        audit(db, actor, "sync", "activity_sync", job.id, after=counts)
        db.commit()
    except Exception as exc:                        # nothing was written: the old library stays as it was
        db.rollback()
        job = db.get(ActivitySyncJob, job_id)
        job.status, job.finished_at = "FAILED", datetime.utcnow()
        job.error = str(exc) if isinstance(exc, PortalError) else f"Unexpected problem: {exc}"
        job.step = "Stopped - your library was not changed"
        db.commit()
    finally:
        db.close()


def _apply(db: Session, actor: Actor, fetched: Dict[str, Dict[str, List[Dict[str, Any]]]],
           with_my_activities: bool) -> Dict[str, Dict[str, int]]:
    now = datetime.utcnow()
    counts: Dict[str, Dict[str, int]] = {}
    for stage, by_source in fetched.items():
        c = {"new": 0, "updated": 0, "removed": 0, "unchanged": 0}
        changed: List[Dict[str, Any]] = []          # what the school admin is shown after the update
        for source, records in by_source.items():
            if source == "portal_teacher" and not with_my_activities:
                continue
            q = db.query(LibraryActivity).filter(LibraryActivity.source == source, LibraryActivity.stage == stage)
            if source == "portal_teacher":
                q = q.filter(LibraryActivity.owner_teacher_id == actor.id)
            existing = {a.portal_id: a for a in q.all()}
            if source == "portal_global" and not records and any(a.upstream_status == "present" for a in existing.values()):
                raise PortalError(f"PARAKH returned no {stage} activities. The existing list was kept; try again later.")
            seen = set()
            for rec in records:
                seen.add(rec["portal_id"])
                act = existing.get(rec["portal_id"])
                if act is None:
                    act = (db.query(LibraryActivity).filter_by(source=source, portal_id=rec["portal_id"]).first())
                if act is None:
                    act = LibraryActivity(source=source, stage=stage, portal_id=rec["portal_id"], first_seen_at=now,
                                          created_by="sync", owner_school_id=actor.school_id if source == "portal_teacher" else None,
                                          owner_teacher_id=actor.id if source == "portal_teacher" else None)
                    db.add(act)
                    c["new"] += 1
                    changed.append({"code": rec["code"], "change": "new"})
                elif act.snapshot_hash != rec["hash"] or act.upstream_status != "present" or act.stage != stage:
                    c["updated"] += 1
                    changed.append({"code": rec["code"], "change": "changed"})
                else:
                    c["unchanged"] += 1
                act.stage, act.code, act.content = stage, rec["code"], rec["content"]
                act.portal_subjects, act.grade_id, act.has_pictures = rec["portal_subjects"], rec["grade_id"], rec["has_pictures"]
                act.used_counter, act.original_snapshot, act.snapshot_hash = rec["used_counter"], rec["snapshot"], rec["hash"]
                act.upstream_status, act.removed_at, act.last_synced_at, act.updated_by = "present", None, now, "sync"
            for portal_id, act in existing.items():
                if portal_id not in seen and act.upstream_status == "present":
                    act.upstream_status, act.removed_at, act.updated_by = "removed", now, "sync"   # kept: cards may use it
                    c["removed"] += 1
                    changed.append({"code": act.code, "change": "removed"})
        c["changed"] = changed[:100]
        counts[stage] = c
    return counts


def job_view(job: ActivitySyncJob) -> Dict[str, Any]:
    return {"id": job.id, "stages": job.stages.split(","), "status": job.status, "step": job.step,
            "progress": job.progress, "counts": job.counts, "error": job.error, "automatic": job.started_by == "auto",
            "started_at": _iso(job.created_at), "finished_at": _iso(job.finished_at)}


def last_syncs(db: Session, school_id: str) -> Dict[str, Any]:
    """Latest job overall, the last successful sync time per stage, and when the shared copy of PARAKH's
    bank was last updated (by any school's admin) - what teachers see."""
    jobs = (db.query(ActivitySyncJob).filter(ActivitySyncJob.school_id == school_id)
            .order_by(ActivitySyncJob.created_at.desc()).limit(50).all())
    per_stage = {}
    for j in jobs:
        if j.status == "COMPLETED":
            for s in j.stages.split(","):
                per_stage.setdefault(s, _iso(j.finished_at))
    return {"latest": job_view(jobs[0]) if jobs else None, "last_synced": per_stage,
            "bank_updated": {s: _iso(bank_updated(db, s)) for s in STAGES if bank_updated(db, s)}}


# ---------------------------------------------------------------------------
# Teachers read activities from here; the school admin's session keeps them up to date
# ---------------------------------------------------------------------------

AUTO_SYNC_AFTER_HOURS = 24
_STAGE_BY_CODE = {s.upper(): s for s in STAGES}


def bank_updated(db: Session, stage: str) -> Optional[datetime]:
    """When PARAKH's Activity Bank for a stage was last copied here (the copy is shared by every school)."""
    from sqlalchemy import func
    return (db.query(func.max(LibraryActivity.last_synced_at))
            .filter(LibraryActivity.source == "portal_global", LibraryActivity.stage == stage).scalar())


def bank_activities(stage_code: str) -> Dict[int, Dict[str, Any]]:
    """The Activity Bank as PARAKH's own lists give it (for Lookups), from the app's copy: no PARAKH call.
    Picture activities are left out, as before."""
    stage = _STAGE_BY_CODE.get(str(stage_code).upper())
    if not stage:
        return {}
    with SessionLocal() as db:
        rows = (db.query(LibraryActivity).filter(LibraryActivity.source == "portal_global", LibraryActivity.stage == stage,
                                                 LibraryActivity.upstream_status == "present").all())
        out = {}
        for a in rows:
            if a.has_pictures or a.portal_id is None:
                continue
            snap = a.original_snapshot or {}
            out[a.portal_id] = {"id": a.portal_id, "activity_caption": snap.get("activity_caption") or a.code,
                                "hpc_stage": stage.upper(), "domain_ids": list(snap.get("domain_ids") or []),
                                "content": {"dt": a.content or {}}}
        return out


def stale_stages(db: Session) -> List[str]:
    limit = datetime.utcnow().timestamp() - AUTO_SYNC_AFTER_HOURS * 3600
    return [s for s in STAGES if (bank_updated(db, s) is None or bank_updated(db, s).timestamp() < limit)]


def maybe_auto_sync(school_id: str, client_for=None) -> Optional[str]:
    """Starts an automatic update of the stages not updated for a day, with the school admin's PARAKH session
    (read-only, the same sync as the Update button). At most one automatic try per school a day; nothing
    happens without a session. Returns the job id when one was started."""
    import threading
    from datetime import timedelta
    from backend.models.entities import School
    from backend.services import hpc_sessions
    with SessionLocal() as db:
        stages = stale_stages(db)
        if not stages:
            return None
        since = datetime.utcnow() - timedelta(hours=AUTO_SYNC_AFTER_HOURS)
        if (db.query(ActivitySyncJob).filter(ActivitySyncJob.school_id == school_id, ActivitySyncJob.started_by == "auto",
                                             ActivitySyncJob.created_at >= since).first()):
            return None
        school = db.get(School, school_id)
        if school is None:
            return None
        try:
            client = (client_for or (lambda s: hpc_sessions.portal_for("school", s.id)))(school)
        except HTTPException:
            return None                              # not connected: the next connect or tick tries again
        actor = Actor("SCHOOL_ADMIN", school.id, school.id, school.admin_name or "")
        job, running = start_sync(db, actor, stages, started_by="auto")
        if running:
            return None
        job_id = job.id
    threading.Thread(target=run_sync, args=(job_id, client, actor, False), daemon=True).start()
    return job_id


def auto_sync_tick(session_exists=None) -> List[str]:
    """Hourly: every school whose admin has a PARAKH session gets its automatic update when it is due."""
    from backend.models.entities import School
    from backend.services import hpc_sessions
    exists = session_exists or (lambda school_id: hpc_sessions.session_path("school", school_id).exists())
    with SessionLocal() as db:
        if not stale_stages(db):
            return []
        ids = [s.id for s in db.query(School).all()]
    return [j for j in (maybe_auto_sync(i) for i in ids if exists(i)) if j]


def start_auto_sync_timer(every_seconds: int = 3600) -> None:
    import threading

    def loop():
        import time as _time
        while True:
            _time.sleep(every_seconds)
            try:
                auto_sync_tick()
            except Exception as exc:                 # never stops the server; tried again next hour
                print(f"[auto-sync] skipped: {exc}")
    threading.Thread(target=loop, daemon=True, name="activity-auto-sync").start()


def recover_interrupted_syncs() -> int:
    """At startup: a sync that was running when the server stopped will never finish."""
    db = SessionLocal()
    try:
        jobs = db.query(ActivitySyncJob).filter(ActivitySyncJob.status.in_(("QUEUED", "RUNNING"))).all()
        for j in jobs:
            j.status, j.finished_at = "FAILED", datetime.utcnow()
            j.error, j.step = "The server restarted during the sync. Nothing was changed; please sync again.", "Stopped"
        db.commit()
        return len(jobs)
    finally:
        db.close()



# Lookups (backend.hpc.stages.common) reads the Activity Bank from the app's copy from now on.
from backend.hpc.stages import common as _common  # noqa: E402
_common.ACTIVITY_SOURCE = bank_activities
