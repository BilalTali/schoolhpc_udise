"""
School Register (docs/school_register_plan.md): the school's students as PARAKH lists them, and which PARAKH teacher
is class teacher of which grade and section. Filled by the school's fetch; teachers read their students from here.

A student is identified by (school, stage, PARAKH student id) - never by name. The PARAKH identity (name, APAAR,
grade, section ...) is only ever written by a fetch from PARAKH; nothing the school types (Excel) changes it.
"""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from backend.database import Base
from backend.models.entities import generate_uuid


class RegisterStudent(Base):
    __tablename__ = "register_students"
    __table_args__ = (UniqueConstraint("school_id", "stage", "parakh_student_id", name="uq_register_student"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)                       # Foundational / Preparatory / Middle
    parakh_student_id = Column(String(30), nullable=False)          # PARAKH's student (HPC) id
    hpc_login_id = Column(String(50), nullable=True)                 # std_reg_id
    student_name = Column(String(200), nullable=False)               # exactly as PARAKH has it
    apaar_id = Column(String(30), nullable=True)                     # from PARAKH (source: PARAKH)
    grade = Column(String(40), nullable=True)
    grade_id = Column(Integer, nullable=True)
    section = Column(String(20), nullable=True)
    section_id = Column(Integer, nullable=True)
    gender = Column(String(20), nullable=True)
    dob = Column(String(20), nullable=True)
    admission_number = Column(String(50), nullable=True)
    hpc_status = Column(String(30), nullable=True)                   # PARAKH's own status at the last fetch
    source = Column(JSON, nullable=True)                             # PARAKH's list row and record details, as read
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    missing_since = Column(DateTime, nullable=True)                  # PARAKH no longer lists the student


class RegisterTeacherClass(Base):
    """One grade/section a PARAKH teacher is mapped to (PARAKH lets only that teacher edit its cards)."""
    __tablename__ = "register_teacher_classes"
    __table_args__ = (UniqueConstraint("school_id", "parakh_teacher_id", "grade_id", "section_id",
                                       name="uq_register_teacher_class"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    parakh_teacher_id = Column(String(30), nullable=False)
    teacher_name = Column(String(200), nullable=True)
    login_hints = Column(JSON, nullable=True)                        # the PARAKH teacher record's ids/logins (matching)
    app_teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    grade_id = Column(Integer, nullable=False)
    section_id = Column(Integer, nullable=False)
    source = Column(String(30), nullable=False, default="parakh_school")    # parakh_school | teacher_session
    fetched_at = Column(DateTime, default=datetime.utcnow)
