"""
The app's stored copy of students' card parts, so Bulk Entry, the Part C levels screen and the Activities grid
load from here instead of reading every student's card from PARAKH each time.

A part is read from PARAKH (GET only) the first time it is needed and then kept. It is read again when the
teacher presses "Read again from PARAKH" (the whole stage), and for one student after the app saves that
student's card (its copy is dropped, so the next view reads it fresh).

Files: data/cards/<owner>/<session>/<stage>/<student_id>.json - inside the data folder, outside OneDrive,
covered by the encrypted backups, like the snapshots. Logs carry IDs only.
"""
import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.config import DATA_DIR

CARDS_DIR = DATA_DIR / "cards"
_lock = threading.Lock()


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


def forget_everywhere(owner: str, stage: str, student_id: str) -> None:
    """After a save: the student's copy is dropped in every academic session folder."""
    base = CARDS_DIR / owner
    if base.exists():
        for session_dir in base.iterdir():
            forget(owner, session_dir.name, stage, student_id)
