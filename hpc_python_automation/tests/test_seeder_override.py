import openpyxl
from pathlib import Path
from excel.importer import import_preparatory_workbook, _read_global_seeder

def test_sheet1_as_seeder(tmp_path: Path):
    """Verifies that a sheet named 'Sheet 1' acts as the global seeder and overrides defaults."""
    wb = openpyxl.Workbook()
    # Sheet 1: Seeder
    ws1 = wb.active
    ws1.title = "Sheet 1"
    ws1.cell(row=1, column=1, value="Parameter Key")
    ws1.cell(row=1, column=2, value="Parameter Description")
    ws1.cell(row=1, column=3, value="Configured Global Value")
    
    ws1.cell(row=2, column=1, value="apr_working_days")
    ws1.cell(row=2, column=3, value=18)
    
    ws1.cell(row=3, column=1, value="may_working_days")
    ws1.cell(row=3, column=3, value=20)

    ws1.cell(row=4, column=1, value="max_summative_marks")
    ws1.cell(row=4, column=3, value=50)

    # Sheet 2: Student Data
    ws2 = wb.create_sheet(title="HPC_Students")
    ws2.cell(row=2, column=1, value="Student Name")
    ws2.cell(row=2, column=2, value="Admission Number")
    ws2.cell(row=2, column=3, value="APR Working Days")
    
    ws2.cell(row=3, column=1, value="student_name")
    ws2.cell(row=3, column=2, value="admission_number")
    ws2.cell(row=3, column=3, value="apr_working_days")  # stale column in student data
    
    ws2.cell(row=4, column=1, value="Test Student")
    ws2.cell(row=4, column=2, value="101")
    ws2.cell(row=4, column=3, value="22")  # old stale default 22
    
    file_path = tmp_path / "test_seeder.xlsx"
    wb.save(file_path)

    defaults = _read_global_seeder(wb)
    assert defaults["apr_working_days"] == "18"
    assert defaults["may_working_days"] == "20"
    assert defaults["max_summative_marks"] == "50"

    records = import_preparatory_workbook(file_path)
    assert len(records) == 1
    rec = records[0]["data"]
    # Verify Sheet 1 seeder OVERRODE the stale '22' in the student row
    assert rec["apr_working_days"] == "18"
    assert rec["may_working_days"] == "20"
    assert rec["max_summative_marks"] == "50"
    # Total working days sum
    assert int(rec["working_days"]) > 0
