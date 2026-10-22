import sys
import json
from portal.student_fetcher import fetch_students_from_portal

sys.stdout.reconfigure(encoding='utf-8')

def test_fetch_middle():
    print("Testing fetch_students_from_portal(stage='Middle')...")
    students = fetch_students_from_portal(stage="Middle", headless=True)
    print(f"Successfully fetched {len(students)} Middle Stage students!")
    if students:
        print("First student sample:", json.dumps(students[0], indent=2))

if __name__ == '__main__':
    test_fetch_middle()
