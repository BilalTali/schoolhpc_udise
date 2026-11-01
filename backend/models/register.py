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


class RegisterSetting(Base):
    """What the school sets once per stage and session: working days per month (April..March) and the summative
    max marks per subject. Teachers read it; every change is kept as a version (RegisterSettingVersion)."""
    __tablename__ = "register_settings"
    __table_args__ = (UniqueConstraint("school_id", "stage", "session", name="uq_register_setting"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)
    session = Column(String(10), nullable=False)                     # PARAKH's academic year code, e.g. 2627
    values = Column(JSON, nullable=False)                            # {"working_days": [12], "max_marks": {n: m}}
    version = Column(Integer, nullable=False, default=1)
    updated_by = Column(String(60), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RegisterSettingVersion(Base):
    __tablename__ = "register_setting_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    setting_id = Column(String(36), ForeignKey("register_settings.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    values = Column(JSON, nullable=False)
    saved_by = Column(String(60), nullable=True)
    saved_at = Column(DateTime, default=datetime.utcnow)


class RegisterStudentData(Base):
    """What the school provides for one student and session: days present per month, parentage, marks obtained.
    Linked to the register's student (its PARAKH identity is never changed from here)."""
    __tablename__ = "register_student_data"
    __table_args__ = (UniqueConstraint("student_id", "session", name="uq_register_student_data"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String(36), ForeignKey("register_students.id", ondelete="CASCADE"), nullable=False, index=True)
    session = Column(String(10), nullable=False)
    present = Column(JSON, nullable=True)                            # [12] days present, April..March (None: no data)
    father_name = Column(String(150), nullable=True)
    mother_name = Column(String(150), nullable=True)
    guardian_relation = Column(String(20), nullable=True)            # Father / Mother / Guardian: whose name the card shows
    guardian_name = Column(String(150), nullable=True)               # only when the relation is Guardian
    marks = Column(JSON, nullable=True)                              # {subject n: marks obtained}
    sources = Column(JSON, nullable=True)                            # {field: "udise" | "import:<id>"}
    import_id = Column(String(36), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RegisterImport(Base):
    """One uploaded School Data workbook: checked (preview), then applied. Kept as the import history."""
    __tablename__ = "register_imports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    session = Column(String(10), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="CHECKED")  # CHECKED, APPLIED, SUPERSEDED
    summary = Column(JSON, nullable=True)                            # counts per outcome
    rows = Column(JSON, nullable=True)                               # per row: outcome, problems, changes (no PARAKH ids changed)
    created_by = Column(String(60), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    applied_at = Column(DateTime, nullable=True)
