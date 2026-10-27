"""
Database tables: schools, their teachers, and upload jobs with one row per student.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base
from backend.services import secrets_box


def generate_uuid() -> str:
    return str(uuid.uuid4())


class School(Base):
    __tablename__ = "schools"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    udise_code = Column(String(11), unique=True, nullable=False, index=True)   # one registration per school
    school_name = Column(String(255), nullable=False)
    state = Column(String(100), nullable=False)
    district = Column(String(100), nullable=False)
    block = Column(String(100), nullable=True)
    admin_name = Column(String(150), nullable=False)
    admin_email = Column(String(191), unique=True, nullable=False, index=True)
    admin_phone = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    # The school's own HPC portal login, used server-side only; the password is encrypted at rest
    hpc_login_id = Column(String(100), nullable=True)
    hpc_password_encrypted = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    # sign-in tokens carry this number; logging out with the old Bearer token or changing the password moves
    # it on, which ends every token issued before (M-2)
    token_epoch = Column(Integer, nullable=True, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    teachers = relationship("Teacher", back_populates="school", cascade="all, delete-orphan")

    @property
    def hpc_password(self):
        return secrets_box.decrypt(self.hpc_password_encrypted)

    @hpc_password.setter
    def hpc_password(self, value):
        self.hpc_password_encrypted = secrets_box.encrypt(value)


class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_name = Column(String(150), nullable=False)
    employee_code = Column(String(50), nullable=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    mobile_number = Column(String(20), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    plain_password = Column(String(255), nullable=True)      # legacy: no longer written; old values kept encrypted
    assigned_stage = Column(String(150), default="Preparatory", nullable=False)   # e.g. "Preparatory, Middle"
    assigned_grade = Column(String(150), default="Grade 3", nullable=False)
    assigned_section = Column(String(50), default="A", nullable=False)
    # The teacher's own HPC portal login, used server-side only; the password is encrypted at rest
    hpc_login_id = Column(String(100), nullable=True)
    hpc_password_encrypted = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    # sign-in tokens carry this number; logging out with the old Bearer token or changing the password moves
    # it on, which ends every token issued before (M-2)
    token_epoch = Column(Integer, nullable=True, default=0)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    school = relationship("School", back_populates="teachers")
    jobs = relationship("UploadJob", back_populates="teacher", cascade="all, delete-orphan")

    @property
    def hpc_password(self):
        return secrets_box.decrypt(self.hpc_password_encrypted)

    @hpc_password.setter
    def hpc_password(self, value):
        self.hpc_password_encrypted = secrets_box.encrypt(value)

    @property
    def stages(self):
        return [s.strip() for s in (self.assigned_stage or "").split(",") if s.strip()] or ["Preparatory"]


class RefreshToken(Base):
    """A signed-in browser session; revoked on logout, rotation or suspected reuse."""
    __tablename__ = "refresh_tokens"

    id = Column(String(36), primary_key=True)            # the token's jti
    user_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    remember = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class UploadJob(Base):
    """One uploaded workbook being synced to the portal."""
    __tablename__ = "upload_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=True)
    detected_stage = Column(String(30), nullable=False)
    status = Column(String(30), default="PENDING")   # PENDING, IN_PROGRESS, COMPLETED, PARTIAL_SUCCESS, FAILED
    # the teacher's id while the job is PENDING or IN_PROGRESS, empty after: unique, so the database itself
    # refuses a second active job for the same teacher (H-3)
    active_teacher_id = Column(String(36), nullable=True, unique=True)
    total_students = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    unverified_count = Column(Integer, default=0)     # kept for the web app; always 0 now
    reconciliation_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    teacher = relationship("Teacher", back_populates="jobs")
    records = relationship("StudentRecord", back_populates="job", cascade="all, delete-orphan")


class StudentRecord(Base):
    """The outcome for one student in an upload job."""
    __tablename__ = "student_records"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    job_id = Column(String(36), ForeignKey("upload_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=True)
    admission_number = Column(String(50), nullable=False)    # holds the portal student id
    student_name = Column(String(150), nullable=False)
    student_key = Column(String(100), nullable=True, index=True)
    grade = Column(String(20), nullable=True)
    section = Column(String(10), nullable=True)
    status = Column(String(30), default="PENDING")   # PENDING, IN_PROGRESS, SUCCESS, FAILED, INVALID, SKIPPED
    attempt_count = Column(Integer, default=0)
    verification_result = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    screenshot_evidence = Column(String(255), nullable=True)
    completed_at = Column(DateTime, nullable=True)

    job = relationship("UploadJob", back_populates="records")


def encrypt_stored_passwords(db) -> int:
    """One-time migration: encrypts passwords that older versions stored as plain text."""
    changed = 0
    for row in [*db.query(School).all(), *db.query(Teacher).all()]:
        for column in ("hpc_password_encrypted", "plain_password"):
            value = getattr(row, column, None)
            if value and not secrets_box.is_encrypted(value):
                setattr(row, column, secrets_box.encrypt(value))
                changed += 1
    db.commit()
    return changed
