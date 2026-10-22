"""
Script to test and complete the FIRST student (AADIL AHMAD BHAT).
"""
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

from database.repository import UploadRepository
from database.models import UploadState
from excel.importer import import_preparatory_workbook
from portal.uploader import (
    parse_record_to_model,
    fill_preparatory_student,
    _get_student_portal_key_map,
)
from portal.login import get_browser_context, wait_for_manual_login

ROOT = Path(__file__).resolve().parent
EVIDENCE_DIR = ROOT / "audit_evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)

def main():
    excel_path = ROOT / "data" / "hpc_preparatory_students_filled.xlsx"
    records = import_preparatory_workbook(excel_path)
    if not records:
        print("[ERROR] No records loaded from Excel!")
        return

    first_rec = records[0]
    student = parse_record_to_model(first_rec)
    print(f"[INFO] Target Student: {student.student_name} (Adm: {student.admission_number}, Grade: {student.grade})")

    repo = UploadRepository()

    with sync_playwright() as p:
        ctx = get_browser_context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Verifying Login...")
        wait_for_manual_login(page)

        print("[2] Resolving student portal key...")
        stage_slug = "preparatory-stage"
        portal_map = _get_student_portal_key_map(page, stage_slug)
        
        encoded_key = portal_map.get(student.admission_number) or portal_map.get(student.student_name.lower())
        if not encoded_key:
            # Fallback to known cached key for student 142406
            encoded_key = "142406"
            print(f"[WARN] Not found in map, fallback to key: {encoded_key}")
        else:
            print(f"[OK] Resolved key: {encoded_key}")

        student_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}/{encoded_key}/part-A1"
        print(f"[3] Navigating to student Part-A1: {student_url}")
        page.goto(student_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        repo.record_attempt(student.admission_number, student.student_name)

        try:
            print("[4] Executing fill_preparatory_student...")
            screenshot = fill_preparatory_student(page, student)
            repo.record_success(student.admission_number, screenshot)
            print(f"[SUCCESS] Student {student.student_name} completed with screenshot: {screenshot}")
        except Exception as e:
            repo.record_failure(student.admission_number, str(e))
            print(f"[ERROR] Failed during filling: {e}")
            import traceback
            traceback.print_exc()

        # Check roster status
        print("[5] Navigating to roster to verify final status...")
        roster_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}"
        page.goto(roster_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        final_ss = EVIDENCE_DIR / f"roster_after_student1_{int(time.time())}.png"
        page.screenshot(path=str(final_ss), full_page=True)
        print(f"[INFO] Final roster screenshot saved: {final_ss.name}")

        # Check the status of first student row
        rows = page.query_selector_all("table tbody tr")
        if rows:
            for r in rows[:5]:
                cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
                print("  Roster row:", cells)

        ctx.close()

if __name__ == "__main__":
    main()
