"""
Which Manual activities on students' cards this app wrote itself.

Every activity chosen in the grid goes on a card as PARAKH's "Create Manually" kind, which has no bank id.
The app must know which Manual copies are its own (and which library activity each one is), so the grid can
show them again and a save can update exactly those - and never touch a Manual activity a teacher typed on
the PARAKH website.

After each successful save the card's activity ids (unique: they start with the card's hpc id) are
recorded with the library key they came from. Files: data/own_activities/<owner>.json, IDs only.
"""
import json
import threading
from typing import Any, Dict, List

from backend.config import DATA_DIR
from backend.services.safe_paths import inside

OWN_DIR = DATA_DIR / "own_activities"
_lock = threading.Lock()


def _path(owner: str):
    return inside(OWN_DIR, f"{owner}.json")


def load(owner: str) -> Dict[str, str]:
    """card activity id -> library key (e.g. "142411_88_2" -> "P85")."""
    try:
        return json.loads(_path(owner).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def remember(owner: str, part_b: List[Dict[str, Any]], typed: Dict[str, str]) -> None:
    """Called after a save: the card's Manual copies of library activities are recorded; activities linked to
    the bank (or gone) need no record."""
    with _lock:
        owned = load(owner)
        before = dict(owned)
        for act in part_b or []:
            act_id = str(act.get("id") or "")
            if not act_id:
                continue
            dt = act.get("dt") or {}
            key = owned.get(act_id) or typed.get(act.get("nm") or "")
            if dt.get("act_bank_id"):
                owned.pop(act_id, None)
            elif key:
                owned[act_id] = key
        if owned != before:
            OWN_DIR.mkdir(parents=True, exist_ok=True)
            tmp = _path(owner).with_suffix(".tmp")
            tmp.write_text(json.dumps(owned, sort_keys=True), encoding="utf-8")
            tmp.replace(_path(owner))
