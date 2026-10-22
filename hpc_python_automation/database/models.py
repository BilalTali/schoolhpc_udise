"""
Pydantic data models for student records, upload tracking, and validation results.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class UploadState(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class StudentRecord(BaseModel):
    admission_number: str
    student_name: str
    dob: Optional[str] = ""
    gender: Optional[str] = ""
    grade: str = "Grade 5"
    section: Optional[str] = "A"
    mother_tongue: Optional[str] = ""
    guardian_name: Optional[str] = ""
    
    # Attendance
    working_days: Optional[int] = 0
    days_present: Optional[int] = 0
    absent_frequency: Optional[str] = ""
    attendance_remarks: Optional[str] = ""

    # Interests (key -> bool)
    interests: Dict[str, bool] = Field(default_factory=dict)

    # Part-B Competency Ratings (comp_key -> rating: beginner/proficient/advance)
    competency_ratings: Dict[str, str] = Field(default_factory=dict)

    # Part-C & Credits
    teacher_rating: Optional[str] = "proficient"
    teacher_remarks: Optional[str] = ""
    credits_earned: Optional[int] = 40

    # Tracking metadata
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class StudentUploadLog(BaseModel):
    admission_number: str
    student_name: str
    stage: str = "Preparatory"
    status: UploadState = UploadState.PENDING
    attempt_count: int = 0
    last_attempt_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    screenshot_evidence: Optional[str] = None
