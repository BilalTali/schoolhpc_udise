"""
Pydantic Schemas for Validation and API Contracts
"""
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
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
    password: str = Field(..., min_length=6, description="Admin password (min 6 characters)")

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

    class Config:
        from_attributes = True


class TeacherCreateRequest(BaseModel):
    teacher_name: str = Field(..., min_length=2, max_length=150)
    employee_code: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=100, description="Login username for teacher")
    mobile_number: Optional[str] = None
    password: str = Field(..., min_length=6, description="Initial teacher password")
    assigned_stage: str = Field("Preparatory", description="Preparatory or Middle")
    assigned_grade: str = Field("Grade 3", description="Assigned class, e.g., Grade 3 or Grade 6")
    assigned_section: str = Field("A", description="Assigned section, e.g., A, B, C")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        clean = v.strip().lower().replace(" ", "_")
        if len(clean) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        return clean


class TeacherResponse(BaseModel):
    id: str
    school_id: str
    teacher_name: str
    employee_code: Optional[str]
    username: str
    mobile_number: Optional[str]
    assigned_stage: str
    assigned_grade: str
    assigned_section: str
    is_active: bool
    last_login: Optional[datetime]
    parakh_connected: bool = False
    parakh_user: Optional[str] = None
    # Whether HPC credentials have been saved
    has_hpc_credentials: bool = False

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="UDISE code/email for School Admin, or username for Teacher")
    password: str = Field(...)
    role: str = Field("AUTO", description="'SCHOOL_ADMIN', 'TEACHER', or 'AUTO'")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str
    school_id: Optional[str] = None
    school_name: Optional[str] = None
    assigned_stage: Optional[str] = None
    assigned_grade: Optional[str] = None
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


class UploadJobResponse(BaseModel):
    job_id: str
    status: str
    total_students: int
    success_count: int
    failed_count: int
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


class HpcSessionStatusResponse(BaseModel):
    logged_in: bool
    user: Optional[str] = None
    school: Optional[str] = None
    role: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Legacy schemas (kept for backward compatibility)
# ---------------------------------------------------------------------------

class ParakhDirectLoginRequest(BaseModel):
    login_id: str = Field(..., description="HPC Login ID / Teacher code / Mobile")
    password: str = Field(..., description="PARAKH portal password")
    captcha_id: str = Field(..., description="Captcha identifier from GET /captcha")
    captcha_answer: str = Field(..., description="Answer to the arithmetic captcha")


class ParakhVerifyOtpRequest(BaseModel):
    otp: str = Field(..., min_length=4, max_length=10, description="Verification code sent to teacher phone")
