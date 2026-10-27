"""M-9: every outside package the app imports is in requirements.txt, so a fresh install starts."""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# import name -> name on PyPI
PYPI = {"PIL": "pillow", "jwt": "pyjwt", "multipart": "python-multipart", "pymysql": "pymysql"}


def _imported_top_level():
    names = set()
    for path in list((ROOT / "backend").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        if "tests" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def test_requirements_list_every_outside_package_the_app_imports():
    local = {"backend", "backup_db", "scripts"} | {p.stem for p in (ROOT / "scripts").glob("*.py")}
    outside = {n for n in _imported_top_level() if n not in sys.stdlib_module_names and n not in local}
    listed = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            listed.add(line.split(">")[0].split("=")[0].split("<")[0].strip().lower())
    missing = sorted(PYPI.get(n, n).lower() for n in outside if PYPI.get(n, n).lower() not in listed)
    assert missing == [], f"imported but not in requirements.txt: {missing}"
