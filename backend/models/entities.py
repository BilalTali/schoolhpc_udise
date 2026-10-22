"""
SQLAlchemy Entity Models for Multi-Tenant School & Teacher System
Both School Admins and Teachers maintain their own isolated HPC PARAKH sessions.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from backend.database import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class School(Base):
    __tablename__ = "schools"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    # Strictly unique official 11-digit UDISE+ code (One School = One Registration)
    udise_code = Column(String(11), unique=True, nullable=False, index=True)
    school_name = Column(String(255), nullable=False)
    state = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    block = Column(String(100), nullable=True)
    admin_name = Column(String(150), nullable=False)
    admin_email = Column(String(191), unique=True, nullable=False, index=True)
    admin_phone = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    # School's own HPC PARAKH credentials (stored by school admin on their dashboard)
    hpc_login_id = Column(String(100), nullable=True)           # Official HPC login ID for school
    hpc_password_encrypted = Column(String(255), nullable=True) # Plain-text stored (will encrypt later)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    teachers = relationship("Teacher", back_populates="school", cascade="all, delete-orphan")
    hpc_session = relationship("SchoolHpcSession", back_populates="school", uselist=False, cascade="all, delete-orphan")


class SchoolHpcSession(Base):
    """Stores the isolated HPC PARAKH session for a School Admin."""
    __tablename__ = "school_hpc_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), unique=True, nullable=False)
    hpc_user_name = Column(String(150), nullable=True)       # Name returned by PARAKH after login
    hpc_school_name = Column(String(255), nullable=True)     # School name from PARAKH
    hpc_role = Column(String(50), default="SCHOOL")
    is_active = Column(Boolean, default=False)
    session_storage_path = Column(String(512), nullable=False)  # Path to storage_state.json
    last_authenticated_at = Column(DateTime, nullable=True)

    # Relationships
    school = relationship("School", back_populates="hpc_session")


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_name = Column(String(150), nullable=False)
    employee_code = Column(String(50), nullable=True)
    username = Column(String(100), unique=True, nullable=False, index=True)  # Teacher login username
    mobile_number = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    assigned_stage = Column(String(30), default="Preparatory", nullable=False)  # Preparatory or Middle
    assigned_grade = Column(String(20), default="Grade 3", nullable=False)      # e.g. Grade 3, Grade 6
    assigned_section = Column(String(10), default="A", nullable=False)          # e.g. A, B
    # Teacher's own HPC PARAKH credentials (set by teacher on their own dashboard)
    hpc_login_id = Column(String(100), nullable=True)            # Official HPC login ID for teacher
    hpc_password_encrypted = Column(String(255), nullable=True)  # Stored HPC password
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    school = relationship("School", back_populates="teachers")
    hpc_session = relationship("TeacherHpcSession", back_populates="teacher", uselist=False, cascade="all, delete-orphan")
    jobs = relationship("UploadJob", back_populates="teacher", cascade="all, delete-orphan")


class TeacherHpcSession(Base):
    """Stores the isolated HPC PARAKH session for a Teacher (one per teacher)."""
    __tablename__ = "teacher_hpc_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), unique=True, nullable=False)
    hpc_user_name = Column(String(150), nullable=True)       # Name returned by PARAKH after login
    hpc_school_name = Column(String(255), nullable=True)     # School name from PARAKH
    hpc_role = Column(String(50), default="TEACHER")
    is_active = Column(Boolean, default=False)
    session_storage_path = Column(String(512), nullable=False)  # Path to storage_state.json
    last_authenticated_at = Column(DateTime, nullable=True)

    # Relationships
    teacher = relationship("Teacher", back_populates="hpc_session")


# ---------------------------------------------------------------------------
# Legacy alias (kept for backward compatibility during migration)
# ---------------------------------------------------------------------------
TeacherParakhSession = TeacherHpcSession


class UploadJob(Base):
    __tablename__ = "upload_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    detected_stage = Column(String(30), nullable=False)
    status = Column(String(30), default="PENDING")  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    total_students = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    teacher = relationship("Teacher", back_populates="jobs")
    records = relationship("StudentRecord", back_populates="job", cascade="all, delete-orphan")


class StudentRecord(Base):
    __tablename__ = "student_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("upload_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    admission_number = Column(String(50), nullable=False)
    student_name = Column(String(150), nullable=False)
    grade = Column(String(20), nullable=True)
    section = Column(String(10), nullable=True)
    status = Column(String(30), default="PENDING")  # PENDING, IN_PROGRESS, SUCCESS, FAILED
    error_message = Column(Text, nullable=True)
    screenshot_evidence = Column(String(255), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    job = relationship("UploadJob", back_populates="records")
