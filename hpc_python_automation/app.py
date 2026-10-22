"""
HPC Automation CLI Application.

Usage:
  python app.py generate-template             # Generates blank Excel template with dropdowns
  python app.py validate data/my_class.xlsx   # Validates Excel data before uploading
  python app.py upload data/my_class.xlsx     # Uploads validated records to HPC portal
  python app.py status                        # Views SQLite upload logs and sync status
  python app.py inventory                     # Re-generates canonical schema from audit data
"""
import sys
import argparse
from pathlib import Path

# Fix Windows console encoding issues with emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from excel.template_generator import build_preparatory_template
from excel.importer import import_preparatory_workbook
from excel.validator import validate_workbook_records
from database.repository import UploadRepository
from audit.field_inventory import build_inventory


def cmd_generate_template(args):
    print("\n[INFO] Generating HPC Preparatory Excel Template...")
    out_file = build_preparatory_template()
    print(f"[OK] Template ready at: {out_file}\n")


def cmd_validate(args):
    file_path = Path(args.file)
    print(f"\n[INFO] Validating workbook: {file_path}...")
    records = import_preparatory_workbook(file_path)
    print(f"Found {len(records)} student record(s).")
    
    report = validate_workbook_records(records)
    print("\n" + report.summary())
    for err in report.errors:
        print(f"  [ERROR] {err}")
    for warn in report.warnings:
        print(f"  [WARN]  {warn}")
    print()


def cmd_upload(args):
    from portal.uploader import upload_batch_students

    file_path = Path(args.file)
    print(f"\n[INFO] Preparing upload for workbook: {file_path}...")
    records = import_preparatory_workbook(file_path)
    
    # Pre-validation check
    report = validate_workbook_records(records)
    if not report.is_valid:
        print(f"\n[ERROR] Aborting upload: {len(report.errors)} validation error(s) found.")
        for err in report.errors[:5]:
            print(f"  - {err}")
        print("\nPlease fix errors in Excel before uploading.")
        sys.exit(1)

    print(f"[OK] Validation passed for {len(records)} students. Starting portal upload...")
    results = upload_batch_students(records, headless=args.headless)
    print(f"\n[SUMMARY] Upload Complete! Success: {results['success']}, Failed: {results['failed']}\n")


def cmd_status(args):
    repo = UploadRepository()
    logs = repo.get_all_logs()
    print("\n[STATUS] LOCAL HPC UPLOAD STATUS:")
    print("-" * 75)
    print(f"{'Adm No':<12} | {'Student Name':<25} | {'Status':<12} | {'Completed At'}")
    print("-" * 75)
    if not logs:
        print("No upload attempts recorded yet.")
    for l in logs:
        comp = str(l.completed_at)[:19] if l.completed_at else "-"
        print(f"{l.admission_number:<12} | {l.student_name:<25} | {l.status.value:<12} | {comp}")
    print("-" * 75 + "\n")


def cmd_inventory(args):
    print("\n[INFO] Re-building field inventory and canonical schema...")
    schemas = build_inventory()
    prep = schemas["Preparatory"]
    print(f"[OK] Extracted {prep['total_unique_fields']} unique fields for Preparatory Stage.\n")


def cmd_fetch_students(args):
    from portal.student_fetcher import fetch_students_from_portal, generate_prepopulated_excel
    
    stage = args.stage or "Preparatory"
    students = fetch_students_from_portal(stage=stage, headless=args.headless)
    if not students:
        print("[WARN] No students found. Please verify you are logged in as a teacher with an assigned class.")
        return

    out_path = Path(args.out) if args.out else None
    excel_file = generate_prepopulated_excel(students, stage=stage, output_file=out_path)
    print(f"\n[SUCCESS] Successfully pre-populated {len(students)} student(s) into Excel!")
    print(f"File location: {excel_file}")
    print("Teachers can now open this file, adjust ratings/remarks, and run 'python app.py upload'!\n")


def cmd_ui(args):
    import subprocess
    print("\n[INFO] Launching HPC Automation Web Interface...")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "frontend.py"])


def main():
    parser = argparse.ArgumentParser(description="HPC Python Automation Toolkit")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ui
    p_ui = subparsers.add_parser("ui", help="Launch interactive Streamlit web interface")
    p_ui.set_defaults(func=cmd_ui)

    # fetch-students
    p_fetch = subparsers.add_parser("fetch-students", help="Fetch student roster from portal and generate pre-filled Excel")
    p_fetch.add_argument("--stage", default="Preparatory", help="HPC stage (Preparatory or Middle)")
    p_fetch.add_argument("--out", help="Custom output Excel path")
    p_fetch.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    p_fetch.set_defaults(func=cmd_fetch_students)

    # generate-template
    p_gen = subparsers.add_parser("generate-template", help="Generate fresh Excel data entry template")
    p_gen.set_defaults(func=cmd_generate_template)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate filled Excel workbook")
    p_val.add_argument("file", help="Path to student Excel file")
    p_val.set_defaults(func=cmd_validate)

    # upload
    p_up = subparsers.add_parser("upload", help="Upload validated Excel file to HPC portal")
    p_up.add_argument("file", help="Path to student Excel file")
    p_up.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    p_up.set_defaults(func=cmd_upload)

    # status
    p_stat = subparsers.add_parser("status", help="Show upload history and status from local database")
    p_stat.set_defaults(func=cmd_status)

    # inventory
    p_inv = subparsers.add_parser("inventory", help="Re-extract canonical stage schemas from audit data")
    p_inv.set_defaults(func=cmd_inventory)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
