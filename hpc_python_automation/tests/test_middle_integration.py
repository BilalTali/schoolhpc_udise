import pytest
from database.models import StudentRecord
from portal.uploader import fill_middle_student, _ensure_middle_part_b_complete

def test_middle_stage_model_and_functions():
    student = StudentRecord(
        admission_number="267M",
        student_name="ARBAZ IQBAL",
        grade="Grade 6",
        section="A",
        raw_data={
            "student_id": "144972",
            "section": "A",
            "ambition": "Scientist",
            "good_at": "Science experiments",
            "teacher_remarks": "Outstanding student"
        }
    )
    assert student.student_name == "ARBAZ IQBAL"
    assert student.grade == "Grade 6"
    assert callable(fill_middle_student)
    assert callable(_ensure_middle_part_b_complete)
