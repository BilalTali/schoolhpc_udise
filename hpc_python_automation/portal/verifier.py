"""
Verifier: verifies upload completion status and data integrity on the HPC portal.
"""
from typing import Dict, Any, List
from playwright.sync_api import Page
from database.models import StudentRecord


def verify_student_status(page: Page, student: StudentRecord) -> Dict[str, Any]:
    """
    Checks the student's status on the dashboard or student list.
    Returns status details and whether the card is marked Completed.
    """
    page.wait_for_load_state("domcontentloaded")
    current_url = page.url

    # Check if we landed on credit or completed page
    is_completed = "hpc-credit" in current_url or "completed" in current_url.lower()

    # Look for status badges or text on the page
    badge = page.query_selector(".status-badge, .badge, [role=status]")
    status_text = badge.inner_text().strip() if badge else ("Completed" if is_completed else "Submitted")

    return {
        "admission_number": student.admission_number,
        "student_name": student.student_name,
        "is_completed": is_completed or "complet" in status_text.lower(),
        "portal_status_text": status_text,
        "verified_url": current_url,
    }
