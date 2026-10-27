"""
Building file paths from values that came from a request (ids, stages, file names) without letting
them reach outside the folder they belong to (findings C-1, C-2).

Two rules, used together everywhere the app keeps files:
  name(value)          the value must be one plain file or folder name: no path separators, no "..",
                       no drive or absolute path, no control characters (NUL included)
  inside(base, *parts) joins the parts under base and checks the result is still inside base
Both raise UnsafePath; backend/main.py turns that into a 400 answer.
"""
import re
from pathlib import Path
from typing import Union

_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')      # separators, drive colons, wildcards, control characters


class UnsafePath(ValueError):
    """A value that would make a path leave its folder."""


def name(value: Union[str, int], what: str = "name") -> str:
    """value as a single safe path component, or UnsafePath."""
    text = str(value)
    if not text or text.strip() != text or text in (".", "..") or text.endswith(".") or _BAD.search(text):
        raise UnsafePath(f"That {what} is not allowed.")
    return text


def inside(base: Path, *parts: Union[str, int]) -> Path:
    """base / parts, after checking every part is a plain name and the result stays inside base."""
    path = Path(base).joinpath(*(name(p) for p in parts))
    root = Path(base).resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise UnsafePath("That name is not allowed.")
    return path
