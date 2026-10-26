"""Class settings per teacher and stage (what the old workbook's seeder sheet held)."""
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from backend.database import Base
from backend.models.entities import generate_uuid


class ClassSetting(Base):
    __tablename__ = "class_settings"
    __table_args__ = (UniqueConstraint("teacher_id", "stage", name="uq_class_setting"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)
    values = Column(JSON, nullable=False)        # medium, rural_urban, working_days[12], max_marks{n}, declaration
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String(60), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
