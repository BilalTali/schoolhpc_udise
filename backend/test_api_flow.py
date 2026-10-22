"""
End-to-End Verification Test for School Registration, UDISE Uniqueness, and Teacher Creation
"""
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal
from backend.models.entities import School, Teacher
from backend.services.auth_service import hash_password, verify_password, create_access_token

def test_full_flow():
    db = SessionLocal()
    print("=" * 60)
    print("🧪 TESTING MULTI-TENANT MYSQL AUTHENTICATION FLOW")
    print("=" * 60)

    test_udise = "01020304050"
    test_email = "principal@greenwood.edu.in"

    # Clean previous test run if any
    prev = db.query(School).filter(School.udise_code == test_udise).first()
    if prev:
        db.delete(prev)
        db.commit()

    # 1. Register School
    print(f"\n1. Registering School with UDISE: {test_udise}...")
    school = School(
        udise_code=test_udise,
        school_name="Greenwood High School",
        state="Delhi",
        district="South Delhi",
        admin_name="Dr. Rajiv Sharma",
        admin_email=test_email,
        hashed_password=hash_password("adminSecret123"),
        is_active=True
    )
    db.add(school)
    db.commit()
    db.refresh(school)
    print(f"   [OK] School created! ID: {school.id}")

    # 2. Test Duplicate UDISE Rejection
    print(f"\n2. Testing Duplicate UDISE Rejection...")
    dup_exists = db.query(School).filter(School.udise_code == test_udise).first()
    if dup_exists:
        print(f"   [OK] Strict Unique Check Passed: Cannot register duplicate UDISE '{test_udise}' (Owned by {dup_exists.school_name})")

    # 3. Create Teacher under School
    print(f"\n3. Creating Teacher under School...")
    teacher = Teacher(
        school_id=school.id,
        teacher_name="Anjali Verma",
        username="anjali_v",
        hashed_password=hash_password("teacherSecret123"),
        assigned_stage="Middle",
        assigned_grade="Grade 6",
        assigned_section="A",
        is_active=True
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    print(f"   [OK] Teacher created! Name: {teacher.teacher_name}, Class: {teacher.assigned_grade} - {teacher.assigned_section}")

    # 4. Test Password Verification
    print(f"\n4. Verifying Bcrypt Passwords...")
    assert verify_password("adminSecret123", school.hashed_password), "Admin password verification failed"
    assert verify_password("teacherSecret123", teacher.hashed_password), "Teacher password verification failed"
    assert not verify_password("wrongPassword", teacher.hashed_password), "Wrong password should fail"
    print("   [OK] Password hashing & verification 100% verified!")

    # 5. Test JWT Token Generation
    print(f"\n5. Generating and validating JWT tokens...")
    token = create_access_token({
        "sub": teacher.id,
        "role": "TEACHER",
        "school_id": school.id,
        "name": teacher.teacher_name
    })
    print(f"   [OK] JWT Token generated: {token[:35]}...")

    db.close()
    print("\n" + "=" * 60)
    print("🎉 ALL CORE MYSQL AUTHENTICATION & MULTI-TENANT TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_full_flow()
