"""
The app's stored copy of students' card parts, so Bulk Entry, the Part C levels screen and the Activities grid
load from here instead of reading every student's card from PARAKH each time.

A part is read from PARAKH (GET only) the first time it is needed and then kept. Each time a screen loads from
the copy, a background check reads the same parts from PARAKH again (one at a time, within the request limit)
and updates the copy, so a change made on the PARAKH website shows up by itself; the screen asks for the
check's result and refreshes. The same parts are not checked again within CHECK_EVERY_SECONDS. "Read again
from PARAKH" reads the whole stage at once, and a save by the app drops that student's copy.

Files: data/cards/<owner>/<session>/<stage>/<student_id>.json - inside the data folder, outside OneDrive,
covered by the encrypted backups, like the snapshots. Logs carry IDs only.
"""
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.config import DATA_DIR

CARDS_DIR = DATA_DIR / "cards"
_lock = threading.RLock()                     # re-entrant: check_view is used while the lock is held


def _dir(owner: str, session: str, stage: str) -> Path:
    return CARDS_DIR / owner / str(session) / stage.lower()


def _path(owner: str, session: str, stage: str, student_id: str) -> Path:
    return _dir(owner, session, stage) / f"{student_id}.json"


def _load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"parts": {}, "read_at": {}}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parts(client, owner: str, session: str, stage: str, student_id: str, cols: Iterable[str]) -> Dict[str, Any]:
    """{col: formdata} for one student: from the stored copy, reading from PARAKH only the parts not kept yet."""
    path = _path(owner, session, stage, student_id)
    with _lock:
        stored = _load(path)
    missing = [c for c in cols if c not in stored["parts"]]
    if missing:
        fresh = {c: client.student(stage, student_id, c).get("formdata") for c in missing}
        with _lock:
            stored = _load(path)
            stored["parts"].update(fresh)
            stored["read_at"].update({c: _now() for c in fresh})
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
    return {c: stored["parts"].get(c) for c in cols}


def class_parts(client, owner: str, session: str, stage: str, student_ids: List[str], cols: Iterable[str],
                refresh: bool = False) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """Every listed student's parts, and when the oldest of them was read from PARAKH. refresh reads them all again."""
    cols = list(cols)
    if refresh:
        forget(owner, session, stage)
    with ThreadPoolExecutor(max_workers=6) as pool:
        out = dict(zip(student_ids, pool.map(lambda sid: parts(client, owner, session, stage, sid, cols), student_ids)))
    return out, oldest_read(owner, session, stage, student_ids, cols)


def oldest_read(owner: str, session: str, stage: str, student_ids: List[str], cols: Iterable[str]) -> Optional[str]:
    times = [(_load(_path(owner, session, stage, sid))["read_at"] or {}).get(c) for sid in student_ids for c in cols]
    times = [t for t in times if t]
    return min(times) if times else None


def forget(owner: str, session: str, stage: str, student_id: Optional[str] = None) -> None:
    """Drops the stored copy of one student (after a save) or of the whole stage (read again)."""
    with _lock:
        if student_id:
            _path(owner, session, stage, student_id).unlink(missing_ok=True)
        else:
            shutil.rmtree(_dir(owner, session, stage), ignore_errors=True)
            key = (owner, str(session), stage.lower())
            for k in [k for k in _checked_at if k[:3] == key]:
                _checked_at[k] = time.time()          # just read in full: no background check needed now


def forget_everywhere(owner: str, stage: str, student_id: str) -> None:
    """After a save: the student's copy is dropped in every academic session folder."""
    base = CARDS_DIR / owner
    if base.exists():
        for session_dir in base.iterdir():
            forget(owner, session_dir.name, stage, student_id)


# ---------------------------------------------------------------------------
# Checking the copy against PARAKH in the background
# ---------------------------------------------------------------------------

CHECK_EVERY_SECONDS = 10 * 60
_checks: Dict[tuple, Dict[str, Any]] = {}
_checked_at: Dict[tuple, float] = {}


def check_view(owner: str, session: str, stage: str) -> Optional[Dict[str, Any]]:
    """The latest check for this stage: progress, which students' cards changed on PARAKH (IDs only)."""
    with _lock:
        job = _checks.get((owner, str(session), stage.lower()))
        return None if job is None else {k: (list(v) if isinstance(v, (list, set)) else v)
                                         for k, v in job.items() if k != "cols"}


def _background(client):
    """The same PARAKH connection, marked so its reads give way to a screen that is loading."""
    import copy
    bg = copy.copy(client)
    bg.background = True
    return bg


def put_many(owner: str, session: str, stage: str, students) -> None:
    """Keeps every part of cards just read from PARAKH (e.g. by "Fetch from PARAKH"), so the screens open
    without reading them again; they also count as just checked."""
    now = _now()
    with _lock:
        for d in students:
            path = _path(owner, session, stage, d.student_id)
            stored = _load(path)
            stored["parts"].update(d.raw_parts)
            stored["read_at"].update({c: now for c in d.raw_parts})
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            for c in d.raw_parts:
                _checked_at[(owner, str(session), stage.lower(), c)] = time.time()


_warming: set = set()


def warm(client, owner: str, session: str, stage: str, student_ids: List[str], cols: Iterable[str]) -> bool:
    """Reads, in the background and only when no screen is loading, the parts not kept yet - so the screens
    open at once later. Returns False when a warm-up for this stage is already running."""
    key = (owner, str(session), stage.lower())
    cols = list(cols)
    with _lock:
        if key in _warming:
            return False
        _warming.add(key)

    def run():
        try:
            bg = _background(client)
            for sid in student_ids:
                parts(bg, owner, session, stage, sid, cols)
        except Exception:
            pass                                   # a screen reads what is missing itself
        finally:
            with _lock:
                _warming.discard(key)
    threading.Thread(target=run, daemon=True, name=f"warm-{stage}").start()
    return True


def start_check(client, owner: str, session: str, stage: str, student_ids: List[str], cols: Iterable[str]) -> Optional[Dict[str, Any]]:
    """Starts re-reading these parts from PARAKH unless they were checked in the last CHECK_EVERY_SECONDS or a
    check is running. Returns the check as check_view shows it."""
    key = (owner, str(session), stage.lower())
    cols = list(cols)
    now = time.time()
    with _lock:
        running = _checks.get(key)
        if running and running["status"] == "RUNNING":
            return check_view(owner, session, stage)
        due = [c for c in cols if now - _checked_at.get(key + (c,), 0) >= CHECK_EVERY_SECONDS]
        if not due or not student_ids:
            return check_view(owner, session, stage)
        for c in due:
            _checked_at[key + (c,)] = now
        job = {"id": f"{int(now * 1000)}", "status": "RUNNING", "done": 0, "total": len(student_ids),
               "changed": [], "cols": due, "error": None, "finished_at": None}
        _checks[key] = job
    threading.Thread(target=_run_check, args=(job, _background(client), owner, session, stage, list(student_ids), due),
                     daemon=True).start()
    return check_view(owner, session, stage)


def _run_check(job, client, owner, session, stage, student_ids, cols) -> None:
    try:
        for sid in student_ids:
            path = _path(owner, session, stage, sid)
            fresh = {c: client.student(stage, sid, c).get("formdata") for c in cols}     # GET only, paced
            with _lock:
                stored = _load(path)
                differs = any(c in stored["parts"] and stored["parts"][c] != fresh[c] for c in cols)
                stored["parts"].update(fresh)
                stored["read_at"].update({c: _now() for c in cols})
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
                tmp.replace(path)
                if differs:
                    job["changed"].append(sid)
                job["done"] += 1
        job["status"] = "COMPLETED"
    except Exception as exc:                      # the copy stays as it was; the next screen load tries again
        job["status"], job["error"] = "FAILED", f"Could not check PARAKH for changes ({exc})."
        with _lock:
            for c in cols:
                _checked_at.pop((owner, str(session), stage.lower(), c), None)
    finally:
        job["finished_at"] = _now()
