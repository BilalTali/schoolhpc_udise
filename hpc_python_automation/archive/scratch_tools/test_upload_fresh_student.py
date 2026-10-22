import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

from database.repository import UploadRepository
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
    excel_path = ROOT / "data" / "temp_upload_hpc_preparatory_students_filled (10).xlsx"
    records = import_preparatory_workbook(excel_path)
    if not records:
        print("[ERROR] No records in Excel workbook!")
        return

    student = parse_record_to_model(records[0])
    print(f"\n============================================================")
    print(f"[START] Processing Fresh Student: {student.student_name} (Adm: {student.admission_number}, Grade: {student.grade})")
    print(f"============================================================")

    repo = UploadRepository()

    with sync_playwright() as p:
        ctx = get_browser_context(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("[1] Verifying Login session...")
        wait_for_manual_login(page)

        print("[2] Resolving student portal key...")
        stage_slug = "preparatory-stage"
        portal_map = _get_student_portal_key_map(page, stage_slug)
        clean_name = student.student_name.strip().lower()
        encoded_key = portal_map.get(student.admission_number) or portal_map.get(clean_name)
        if not encoded_key:
            for k, v in portal_map.items():
                if clean_name in k or k in clean_name:
                    encoded_key = v
                    break

        if not encoded_key:
            encoded_key = "MTQyNDExLTI2Mjctams="  # ARKAN AHMAD (142411-2627-jk)
            print(f"[WARN] Fallback encoded key for {student.student_name}: {encoded_key}")
        else:
            print(f"[OK] Resolved key: {encoded_key}")

        student_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}/{encoded_key}/part-A1"
        print(f"[3] Navigating to Part-A1: {student_url}")
        page.goto(student_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        repo.record_attempt(student.admission_number, student.student_name)

        try:
            print("[4] Executing full student upload across all parts...")
            screenshot = fill_preparatory_student(page, student)
            repo.record_success(student.admission_number, screenshot)
            print(f"\n[SUCCESS] Successfully uploaded and completed {student.student_name}!")
            print(f"          Screenshot: {screenshot}")
        except Exception as e:
            repo.record_failure(student.admission_number, str(e))
            print(f"\n[ERROR] Upload failed for {student.student_name}: {e}")
            import traceback
            traceback.print_exc()

        # Step 5: Check live roster
        print("\n[5] Navigating to live roster to confirm status...")
        roster_url = f"https://hpc.parakh.ncert.gov.in/en/hpc/{stage_slug}"
        page.goto(roster_url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(3)
        final_ss = EVIDENCE_DIR / f"roster_after_arkan_{int(time.time())}.png"
        page.screenshot(path=str(final_ss), full_page=True)
        print(f"[INFO] Final roster screenshot saved: {final_ss.name}")

        rows = page.query_selector_all("table tbody tr")
        for r in rows:
            cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
            if len(cells) >= 4 and "ARKAN" in cells[2].upper():
                print(f"\n>>> LIVE ROSTER ROW: {cells[2]} ({cells[1]}) -> STATUS: {cells[3]} <<<")

        ctx.close()

if __name__ == "__main__":
    main()
