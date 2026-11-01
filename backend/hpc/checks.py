"""
Warnings about a card's content that PARAKH would accept but that read wrong (they never block a save):

  Part C notes (C1, C3)   the same note under several subjects, a stock phrase not written from the levels, a note
                          written for other levels than the ones ticked, "written work" under a subject without it,
                          and for Foundational "age-appropriate"/"developing" when all three levels are Advanced
  Part C vs Part B (C4)   a Part C level two steps away from that subject's activity rating (Beginner vs Advanced)

`row` holds a card's values as the workbook/card editor keeps them (c_<domain>_awareness = "Proficient" ...).
"""
import re
from typing import Any, Dict, Iterable, List, Optional

from backend.hpc import notes, suggestions

STOCK = {p.strip().lower() for p in suggestions._REMARK + suggestions._DESCRIPTOR}
PRAISE = re.compile(r"\b(good understanding|excellent|very good|strong skills|strong|outstanding)\b", re.I)
CONCERN = re.compile(r"\b(needs support|needs more practice|basic concepts|weak|struggles)\b", re.I)
WRITTEN = re.compile(r"\bwrit(ten|ing)\b", re.I)
GENERATED = re.compile(r"^Strength - (\w+) \((\w+)\): .*To improve - (\w+) \((\w+)\)", re.S)


def _text(value: Any) -> str:
    return str(value if value is not None else "").strip()


def note_of(row: Dict[str, Any], domain: str) -> str:
    return _text(row.get(f"c_{domain}_remark", row.get(f"c_{domain}_descriptor")))


def part_c_warnings(stage: str, domains: List[str], names: List[str], row: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen: Dict[str, List[str]] = {}
    foundational = stage.lower().startswith("found")
    for domain, name in zip(domains, names):
        text = note_of(row, domain)
        levels = notes.levels_from_row(row, domain)
        if not text:
            continue
        seen.setdefault(text.lower(), []).append(name)
        ranks = [notes.RANK[v] for v in levels.values() if v]
        complete = len(ranks) == 3
        if text.lower() in STOCK:
            out.append(f"{name}: the note is a stock phrase, not written from this subject's levels")
        made = GENERATED.match(text)
        if made and complete:
            said = {made.group(1).lower(): made.group(2), made.group(3).lower(): made.group(4)}
            if any(levels.get(a) != lvl for a, lvl in said.items() if a in levels):
                out.append(f"{name}: the note was written for other levels than the ones ticked - write it again")
        if domain not in notes.WRITTEN and WRITTEN.search(text):
            out.append(f"{name}: the note mentions written work, which is not part of this subject")
        if complete and not made:
            if all(r == 1 for r in ranks) and PRAISE.search(text):
                out.append(f"{name}: the note praises ('{PRAISE.search(text).group(0)}') but all three levels are Beginner")
            if all(r == 3 for r in ranks) and CONCERN.search(text):
                out.append(f"{name}: the note says '{CONCERN.search(text).group(0)}' but all three levels are Advanced")
        if foundational and complete and all(r == 3 for r in ranks) and re.search(r"age-appropriate|developing", text, re.I):
            out.append(f"{name}: all three levels are Advanced; 'age-appropriate'/'developing' undersells them")
    for text, subjects in seen.items():
        if len(subjects) > 1:
            out.append(f"The same note is under {len(subjects)} subjects ({', '.join(subjects)}); each needs its own")
    return out


def part_b_vs_c(domains: List[str], names: List[str], row: Dict[str, Any], part_b: Optional[Iterable[dict]]) -> List[str]:
    """C4: a Part C level that differs by two steps from the subject's activity rating for the same ability."""
    out = []
    by_subject = notes.activity_levels(part_b or [])
    for domain, name in zip(domains, names):
        levels = notes.levels_from_row(row, domain)
        for activity in by_subject.get(domain, []):
            for ability in notes.ABILITIES:
                c, b = levels.get(ability), activity.get(ability)
                if c and b and abs(notes.RANK[c] - notes.RANK[b]) >= 2:
                    out.append(f"{name}: {ability.capitalize()} is {c} in Part C but {b} in its Part B activity")
    return out
