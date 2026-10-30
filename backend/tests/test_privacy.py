"""M-12: the web app loads nothing from other websites - no fonts, scripts or styles from third parties."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# udiseplus.gov.in: the Home page's links to the UDISE+ services (opened in a new tab; nothing is loaded from them)
ALLOWED = ("hpc.parakh.ncert.gov.in", "udiseplus.gov.in", "127.0.0.1", "localhost", "example.com", "www.w3.org", "test")


def test_the_web_app_loads_nothing_from_other_websites():
    found = []
    files = [ROOT / "frontend" / "index.html"] + [p for p in (ROOT / "frontend" / "src").rglob("*")
                                                  if p.suffix in (".ts", ".tsx", ".css", ".html") and ".test." not in p.name]
    for path in files:
        for url in re.findall(r"https?://([a-zA-Z0-9.-]+)", path.read_text(encoding="utf-8")):
            if not url.endswith(ALLOWED):
                found.append(f"{path.relative_to(ROOT)}: {url}")
    assert found == []


def test_the_fonts_come_with_the_app():
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")
    assert "@fontsource/inter" in main and "@fontsource/jetbrains-mono" in main
