"""
Excel cells the app writes: text stays text (finding H-5).

openpyxl stores any string starting with "=" as a formula, so a name or answer like "=Kashmiri" became a formula:
lost on upload, or "#NAME?" once Excel had saved the file (and "=CMD|..." in a name is formula injection).
The app's own formulas are written with formula(); keep_text() then turns every other formula-looking cell
back into plain text just before the file is saved.
"""
from typing import Set, Tuple

_KEY = "_teacher_assist_formulas"


def formula(ws, row: int, column: int, text: str):
    """Writes one of the app's own formulas (attendance %, totals) and remembers that it is meant."""
    cell = ws.cell(row=row, column=column, value=text)
    _intended(ws.parent).add((ws.title, cell.coordinate))
    return cell


def keep_text(wb) -> int:
    """Every formula cell the app did not mean becomes a text cell. Returns how many were turned back."""
    intended = _intended(wb)
    changed = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f" and (ws.title, cell.coordinate) not in intended:
                    cell.data_type = "s"
                    changed += 1
    return changed


def _intended(wb) -> Set[Tuple[str, str]]:
    return wb.__dict__.setdefault(_KEY, set())
