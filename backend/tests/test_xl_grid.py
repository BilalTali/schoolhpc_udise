"""Every table the app writes has clear cell borders: a filled (fill-in) cell hides Excel's own gridlines."""
from openpyxl import Workbook
from openpyxl.styles import Border, PatternFill, Side

from backend.hpc.xl import grid_sheets

FULL = ("left", "right", "top", "bottom")


def boxed(cell):
    return all(getattr(getattr(cell.border, s, None), "style", None) == "thin" for s in FULL)


def test_tables_get_borders_from_the_headings_down_and_blank_rows_stay_blank():
    wb = Workbook()
    ws = wb.active
    ws.title = "Students"
    ws["A1"] = "Student details - fill the yellow cells"            # a title above the table: no box
    for c, t in enumerate(["Name", "Class", "Father"], 1):
        ws.cell(row=2, column=c, value=t).fill = PatternFill("solid", fgColor="E2E8F0")
    ws.cell(row=3, column=1, value="ADAF JAN")
    ws.cell(row=3, column=3).fill = PatternFill("solid", fgColor="FFF7CC")   # an empty fill-in cell
    ws.cell(row=5, column=1, value="Second table")                  # row 4 is a blank separator
    info = wb.create_sheet("Instructions")
    info["A1"] = "How to fill"
    info["A2"].fill = PatternFill("solid", fgColor="FFF7CC")
    grid_sheets(wb)
    assert not boxed(ws["A1"])
    assert all(boxed(ws.cell(row=r, column=c)) for r in (2, 3, 5) for c in (1, 2, 3))
    assert not any(boxed(ws.cell(row=4, column=c)) for c in (1, 2, 3))
    assert not boxed(info["A2"])


def test_a_sheet_with_its_own_borders_is_left_alone():
    wb = Workbook()
    ws = wb.active
    ws["A1"].fill = PatternFill("solid", fgColor="E2E8F0")
    ws["A1"].border = Border(bottom=Side(style="medium"))
    ws["B2"] = "x"
    grid_sheets(wb)
    assert ws["A1"].border.bottom.style == "medium" and not boxed(ws["B2"]) and not boxed(ws["A1"])
