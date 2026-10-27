"""
Copies of a student's PARAKH record, taken just before the app writes to it.

Every save to PARAKH goes through sync.sync_student, which refuses to write unless a snapshot was
taken first (see before_save there). A snapshot is the record and every part's formdata exactly as
PARAKH returned them, so the values can be restored later (restore = a new save of these values,
shown as a preview first).

Files: data/snapshots/<owner>/<stage>/<student_id>/<UTC time>.json  (owner: "teacher_<id>" / "school_<id>")
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from backend.config import DATA_DIR
from backend.hpc.sync import StudentData
from backend.services.safe_paths import inside

SNAPSHOT_DIR = DATA_DIR / "snapshots"


def _dir(owner: str, stage: str, student_id: str) -> Path:
    d = inside(SNAPSHOT_DIR, owner, stage.lower(), str(student_id))
    d.mkdir(parents=True, exist_ok=True)
    return d


def take(owner: str, stage: str, data: StudentData, reason: str) -> Path:
    """Writes the snapshot (atomically) and returns its path. Raises if it cannot be written."""
    now = datetime.now(timezone.utc)
    path = _dir(owner, stage, data.student_id) / f"{now:%Y%m%dT%H%M%S%fZ}.json"
    body = {"taken_at": now.isoformat(timespec="seconds"), "owner": owner, "stage": stage,
            "student_id": data.student_id, "reason": reason, "record": data.record, "parts": data.raw_parts}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    json.loads(path.read_text(encoding="utf-8"))            # read back: never save to PARAKH on a broken copy
    return path


def hook(owner: str, stage: str, reason: str):
    """The before_save function sync_student needs."""
    return lambda data: take(owner, stage, data, reason)


def list_for(owner: str, stage: str, student_id: str) -> List[Dict[str, Any]]:
    d = inside(SNAPSHOT_DIR, owner, stage.lower(), str(student_id))
    out = []
    for p in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        body = json.loads(p.read_text(encoding="utf-8"))
        out.append({"file": p.name, "taken_at": body["taken_at"], "reason": body.get("reason", "")})
    return out


def prune(max_age_days: int = 400, keep_last: int = 2) -> int:
    """Retention: snapshots older than max_age_days are removed, except each student's newest keep_last
    (so a restore point always exists). Returns how many files were removed."""
    if not SNAPSHOT_DIR.exists():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_days * 86400
    removed = 0
    for student in (d for d in SNAPSHOT_DIR.glob("*/*/*") if d.is_dir()):
        files = sorted(student.glob("*.json"))                   # names sort by time
        for p in files[:-keep_last] if keep_last else files:
            taken = datetime.strptime(p.stem, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc).timestamp()
            if taken < cutoff:
                p.unlink()
                removed += 1
    return removed


def load(owner: str, stage: str, student_id: str, file: str) -> StudentData:
    path = inside(SNAPSHOT_DIR, owner, stage.lower(), str(student_id), file)
    body = json.loads(path.read_text(encoding="utf-8"))
    return StudentData(str(body["student_id"]), body["record"], body["parts"])
