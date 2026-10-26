"""
Activity Library tables.

library_activities        one row per activity: PARAKH's global Activity Bank (shared by every
                          school), a teacher's own PARAKH activities ("My activities"), and
                          activities made in this app (local).
school_activity_settings  each school's layer on top: display name, edited texts and subjects,
                          on/off. Edits never touch the portal copy in library_activities.
stage_activity_defaults   the default activity per school and stage (teacher_id is for the
                          class-level choice added later).
activity_sync_jobs        background syncs from the portal, with progress and counts.
audit_log                 who changed what, when.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from backend.database import Base
from backend.models.entities import generate_uuid

SOURCES = ("portal_global", "portal_teacher", "local")
# Sharing of a teacher's local activity, only ever widened with the teacher's consent:
#   private       the teacher (and their school admin) only
#   school        everyone in the teacher's school
#   community     shared with other schools, waiting for the platform admin's review
#   community_ok  approved: every school can use it
SHARE_STATES = ("private", "school", "community", "community_ok")


class LibraryActivity(Base):
    __tablename__ = "library_activities"
    __table_args__ = (UniqueConstraint("source", "portal_id", name="uq_library_source_portal_id"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source = Column(String(20), nullable=False, index=True)
    stage = Column(String(20), nullable=False, index=True)          # Foundational | Preparatory | Middle
    portal_id = Column(Integer, nullable=True)                      # PARAKH's id; null for local activities
    owner_school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True)
    owner_teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True, index=True)
    code = Column(String(200), nullable=False)                      # PARAKH's activity_caption
    title = Column(String(200), nullable=True)                      # local activities only
    content = Column(JSON, nullable=False)                          # gl, cpt, desc, awr, sen, cre, approaches, ...
    portal_subjects = Column(JSON, nullable=True)                   # subject codes PARAKH lists for it
    subjects = Column(JSON, nullable=True)                          # local activities: subjects covered
    grade_id = Column(Integer, nullable=True)
    has_pictures = Column(Boolean, default=False)
    used_counter = Column(Integer, nullable=True)
    tier = Column(String(10), default="free", nullable=False)       # free | paid (rules come with entitlements)
    original_snapshot = Column(JSON, nullable=True)                 # the portal record as last synced
    snapshot_hash = Column(String(64), nullable=True)
    upstream_status = Column(String(10), default="present", nullable=False)   # present | removed
    removed_at = Column(DateTime, nullable=True)
    first_seen_at = Column(DateTime, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    share_state = Column(String(15), default="private", nullable=False)
    share_consent_at = Column(DateTime, nullable=True)
    share_consent_by = Column(String(36), nullable=True)
    share_consent_text = Column(Text, nullable=True)                # the exact wording the teacher agreed to
    version = Column(Integer, default=1, nullable=False)
    created_by = Column(String(60), nullable=True)                  # "<role>:<id>", or "sync"
    updated_by = Column(String(60), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SchoolActivitySetting(Base):
    __tablename__ = "school_activity_settings"
    __table_args__ = (UniqueConstraint("school_id", "activity_id", name="uq_school_activity"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_id = Column(String(36), ForeignKey("library_activities.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name = Column(String(200), nullable=True)
    edited = Column(JSON, nullable=True)                            # {"desc": [...], "awr": [...], "subjects": [...]}
    status = Column(String(10), default="active", nullable=False)   # active | disabled
    version = Column(Integer, default=1, nullable=False)
    updated_by = Column(String(60), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StageActivityDefault(Base):
    __tablename__ = "stage_activity_defaults"
    __table_args__ = (UniqueConstraint("school_id", "teacher_id", "stage", name="uq_stage_default"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = Column(String(36), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=True)
    stage = Column(String(20), nullable=False)
    activity_id = Column(String(36), ForeignKey("library_activities.id", ondelete="SET NULL"), nullable=True)
    covers_all_confirmed = Column(Boolean, default=True)            # False: saved despite the coverage warning
    updated_by = Column(String(60), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ActivitySyncJob(Base):
    __tablename__ = "activity_sync_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    school_id = Column(String(36), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True)
    stages = Column(String(60), nullable=False)                     # "Preparatory" or "Foundational,Preparatory,Middle"
    status = Column(String(15), default="QUEUED", nullable=False)   # QUEUED | RUNNING | COMPLETED | FAILED
    step = Column(String(200), nullable=True)                       # what it is doing now, in plain words
    progress = Column(Integer, default=0)                           # 0-100
    counts = Column(JSON, nullable=True)                            # {stage: {new, updated, removed, unchanged}}
    error = Column(Text, nullable=True)
    started_by = Column(String(60), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    at = Column(DateTime, default=datetime.utcnow, index=True)
    actor = Column(String(60), nullable=False)                      # "<role>:<id>" or "sync"
    actor_name = Column(String(150), nullable=True)
    school_id = Column(String(36), nullable=True, index=True)
    entity = Column(String(40), nullable=False)
    entity_id = Column(String(36), nullable=True, index=True)
    action = Column(String(40), nullable=False)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
