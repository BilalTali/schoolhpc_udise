"""
Slowing down password guessing on the app's own login (finding H-8).

Per username: after PER_NAME failed attempts within WINDOW, each further attempt has to wait - 1 s after the
first extra failure, then twice as long each time (at most MAX_WAIT). Never a hard lockout: the right person
can always sign in once the wait is over, and 15 minutes without failures clears the count.
Per network address: the same, but much looser (PER_ADDRESS), because a whole school can share one address.
A successful login clears its username's count. Kept in memory: a restart clears it.
"""
import threading
import time
from typing import Dict, List, Optional

WINDOW = 15 * 60
PER_NAME = 5
PER_ADDRESS = 50
MAX_WAIT = 15 * 60

_lock = threading.RLock()
_failures: Dict[str, List[float]] = {}          # "name:<id>" / "addr:<ip>" -> times of failed attempts
_clock = time.time


def _recent(key: str, now: float) -> List[float]:
    times = [t for t in _failures.get(key, []) if now - t < WINDOW]
    _failures[key] = times
    return times


def _wait(times: List[float], allowed: int, now: float) -> int:
    """Seconds still to wait, or 0."""
    extra = len(times) - allowed
    if extra < 0:
        return 0
    delay = min(2 ** extra, MAX_WAIT)
    return max(0, int(times[-1] + delay - now + 0.999))


def check(identifier: str, address: Optional[str]) -> int:
    """Seconds this attempt has to wait (0: go ahead)."""
    now = _clock()
    with _lock:
        waits = [_wait(_recent(f"name:{identifier.strip().lower()}", now), PER_NAME, now)]
        if address:
            waits.append(_wait(_recent(f"addr:{address}", now), PER_ADDRESS, now))
    return max(waits)


def failed(identifier: str, address: Optional[str]) -> None:
    now = _clock()
    with _lock:
        _failures.setdefault(f"name:{identifier.strip().lower()}", []).append(now)
        if address:
            _failures.setdefault(f"addr:{address}", []).append(now)


def succeeded(identifier: str) -> None:
    with _lock:
        _failures.pop(f"name:{identifier.strip().lower()}", None)


def reset() -> None:
    with _lock:
        _failures.clear()
