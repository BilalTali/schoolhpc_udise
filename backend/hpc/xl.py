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


def as_text_answer(cell, field) -> None:
    """Text answers use Excel's Text format, so Excel keeps what is typed (007 stays 007) (M-13). Numbers -
    attendance and marks (which are stored as text fields) - keep the normal format: they still add up and the
    live checks still compare them as numbers."""
    if field.kind == "text" and not field.key.endswith(("_max", "_obtained")):
        cell.number_format = "@"


def _intended(wb) -> Set[Tuple[str, str]]:
    return wb.__dict__.setdefault(_KEY, set())


MAX_UNPACKED = 80 * 1024 * 1024             # a class workbook unpacks to a few MB; far more is a "zip bomb"


def unpacked_size_ok(source) -> bool:
    """An .xlsx is a zip: checks what it would unpack to before openpyxl opens it (a small upload must not expand to
    gigabytes in memory). source: a path or the file's bytes. False when too large or not a zip at all."""
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source) as z:
            infos = z.infolist()
            return len(infos) <= 2000 and sum(i.file_size for i in infos) <= MAX_UNPACKED
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
