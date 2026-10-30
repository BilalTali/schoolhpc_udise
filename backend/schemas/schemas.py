"""
Pydantic Schemas for Validation and API Contracts
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
import re


class SchoolRegisterRequest(BaseModel):
    udise_code: str = Field(..., description="Official 11-digit unique UDISE+ school code")
    school_name: str = Field(..., min_length=3, max_length=255)
    state: str = Field(..., min_length=2, max_length=100)
    district: str = Field(..., min_length=2, max_length=100)
    block: Optional[str] = None
    admin_name: str = Field(..., min_length=2, max_length=150)
    admin_email: str = Field(..., description="Official admin email address")
    admin_phone: Optional[str] = None
    password: str = Field(..., min_length=8, description="Admin password (min 8 characters)")

    @field_validator("udise_code")
    @classmethod
    def validate_udise(cls, v: str) -> str:
        clean = v.strip()
        if not re.match(r"^\d{11}$", clean):
            raise ValueError("UDISE code must be exactly 11 numeric digits (e.g., 01020304050).")
        return clean

    @field_validator("admin_email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if "@" not in clean or "." not in clean:
            raise ValueError("Invalid email format.")
        return clean


class SchoolResponse(BaseModel):
    id: str
    udise_code: str
    school_name: str
    state: str
    district: str
    block: Optional[str]
    admin_name: str
    admin_email: str
    admin_phone: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeacherCreateRequest(BaseModel):
    teacher_name: str = Field(..., min_length=2, max_length=150)
    employee_code: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=100, description="Login username for teacher")
    mobile_number: Optional[str] = None
    password: str = Field(..., min_length=8, description="Initial teacher password (min 8 characters)")
    assigned_stage: Optional[str] = Field("Preparatory", description="Preparatory or Middle or comma-separated")
    assigned_stages: Optional[List[str]] = Field(default=None, description="Multi-selected stages, e.g. ['Preparatory', 'Middle']")
    assigned_grade: Optional[str] = Field(None, description="Assigned class, e.g., Grade 3 or Grade 6")
    assigned_grades: Optional[List[str]] = Field(default=None, description="Multi-selected grades")
    assigned_section: Optional[str] = Field(None, description="Assigned section, e.g., A, B, C")
    assigned_sections: Optional[List[str]] = Field(default=None, description="Multi-selected sections")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip().lower().replace(" ", "_")
        if len(clean) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        return clean


class TeacherUpdateRequest(BaseModel):
    teacher_name: Optional[str] = None
    employee_code: Optional[str] = None
    username: Optional[str] = None
    mobile_number: Optional[str] = None
    password: Optional[str] = Field(None, min_length=8, description="New password (min 8 characters), or leave out")
    assigned_stage: Optional[str] = None
    assigned_stages: Optional[List[str]] = None
    assigned_grade: Optional[str] = None
    assigned_grades: Optional[List[str]] = None
    assigned_section: Optional[str] = None
    assigned_sections: Optional[List[str]] = None
    is_active: Optional[bool] = None


class TeacherResponse(BaseModel):
    id: str
    school_id: str
    teacher_name: str
    employee_code: Optional[str]
    username: str
    mobile_number: Optional[str]
    assigned_stage: str
    assigned_stages: List[str] = []
    assigned_grade: str
    assigned_grades: List[str] = []
    assigned_section: str
    is_active: bool
    last_login: Optional[datetime]
    parakh_connected: bool = False
    parakh_user: Optional[str] = None
    # Whether HPC credentials have been saved
    has_hpc_credentials: bool = False

    model_config = ConfigDict(from_attributes=True)



class LoginRequest(BaseModel):
    identifier: str = Field(..., description="UDISE code/email for School, or username for Teacher")
    password: str = Field(...)
    role: str = Field("AUTO", description="'SCHOOL_ADMIN', 'TEACHER', or 'AUTO'")
    remember_me: bool = Field(False, description="Keep the browser signed in for 30 days instead of 1")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str
    school_id: Optional[str] = None
    school_name: Optional[str] = None
    udise_code: Optional[str] = None
    assigned_stage: Optional[str] = None
    assigned_stages: Optional[List[str]] = None
    assigned_grade: Optional[str] = None
    assigned_grades: Optional[List[str]] = None
    assigned_section: Optional[str] = None



class ValidationReportResponse(BaseModel):
    is_valid: bool
    total_records: int
    detected_stage: str
    error_count: int
    warning_count: int
    errors: List[dict]
    warnings: List[dict]
    seeder_working_days: str
    seeder_max_marks: str
    already_saved: int = 0                 # students saved before with these same answers: not sent again
    file_name: Optional[str] = None        # the checked file (a check shown again after a page reload)
    checked_at: Optional[str] = None


class UploadJobResponse(BaseModel):
    job_id: str
    status: str
    total_students: int = 0
    success_count: int = 0
    failed_count: int = 0
    unverified_count: int = 0
    reconciliation_count: int = 0
    file_hash: Optional[str] = None
    detected_stage: str
    created_at: datetime
    completed_at: Optional[datetime] = None



# ---------------------------------------------------------------------------
# HPC Session Schemas (used by both School and Teacher)
# ---------------------------------------------------------------------------

class HpcCredentialsRequest(BaseModel):
    """Save HPC credentials for a school or teacher."""
    hpc_login_id: str = Field(..., description="Official HPC Login ID / Mobile / Staff Code")
    hpc_password: str = Field(..., min_length=3, description="HPC portal password")


class HpcStartSessionRequest(BaseModel):
    """Trigger auto-login to HPC. Uses saved credentials if available."""
    hpc_login_id: Optional[str] = Field(None, description="Override login ID (optional if already saved)")
    hpc_password: Optional[str] = Field(None, description="Override password (optional if already saved)")


class HpcOtpRequest(BaseModel):
    """OTP verification for HPC login."""
    otp: str = Field(..., min_length=4, max_length=10, description="6-digit OTP sent to mobile")


class HpcCaptchaRequest(BaseModel):
    answer: str = Field(..., max_length=20, description="what the captcha picture shows")


class HpcSessionStatusResponse(BaseModel):
    logged_in: bool
    captcha_mode: str = "typed"                  # "typed" or "automatic (unsupported)"
    user: Optional[str] = None
    school: Optional[str] = None
    role: Optional[str] = None
    reason: Optional[str] = None
    has_credentials: bool = False
    saved_hpc_login_id: Optional[str] = None
    stages: List[str] = []          # stages the teacher can work with (app + portal)
