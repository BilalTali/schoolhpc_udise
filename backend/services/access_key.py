"""
The portal's access key: before anyone can use the app (sign in, any screen), the browser must be unlocked with a
secret key the app admin sets on the admin page and gives to the people who may use it.

The key is stored only as a bcrypt hash in the data folder (data/.access_key.json) with a version number. Unlocking
sets an httpOnly cookie (30 days) that names the version; changing the key raises the version, so every browser
must enter the new key. While no key is set the portal is open (so the admin can sign in and set one).
Forgotten key: delete data/.access_key.json on the server - the portal is open again until a new key is set.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from backend.config import DATA_DIR, JWT_ALGORITHM, JWT_SECRET

COOKIE = "ta_gate"
DAYS = 30
MIN_LENGTH = 6
_lock = threading.RLock()


def _path():
    return DATA_DIR / ".access_key.json"


def _load() -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return data if data.get("hash") else None
    except (OSError, ValueError):
        return None


def is_set() -> bool:
    return _load() is not None


def status() -> Dict[str, Any]:
    data = _load()
    return {"set": data is not None, "version": data["version"] if data else 0,
            "set_at": data.get("set_at") if data else None}


def set_key(key: str) -> int:
    """Sets (or changes) the key; every browser must enter the new one. Returns the new version."""
    key = (key or "").strip()
    if len(key) < MIN_LENGTH:
        raise ValueError(f"The access key needs at least {MIN_LENGTH} characters.")
    with _lock:
        version = (_load() or {}).get("version", 0) + 1
        data = {"hash": bcrypt.hashpw(key.encode("utf-8"), bcrypt.gensalt()).decode("ascii"), "version": version,
                "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return version


def clear() -> None:
    """No key: the portal is open to anyone who reaches it (the sign-in still protects every account)."""
    with _lock:
        try:
            _path().unlink()
        except FileNotFoundError:
            pass


def check(key: str) -> bool:
    data = _load()
    if data is None:
        return True
    return bcrypt.checkpw((key or "").strip().encode("utf-8"), data["hash"].encode("ascii"))


def cookie_value() -> str:
    data = _load() or {"version": 0}
    exp = datetime.now(timezone.utc) + timedelta(days=DAYS)
    return jwt.encode({"typ": "gate", "ver": data["version"], "exp": exp}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def unlocked(cookie: Optional[str]) -> bool:
    """True when no key is set, or the cookie was given for the current key."""
    data = _load()
    if data is None:
        return True
    if not cookie:
        return False
    try:
        payload = jwt.decode(cookie, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return False
    return payload.get("typ") == "gate" and payload.get("ver") == data["version"]
