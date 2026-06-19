from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(64), default="identified")
    current_milestone_gate: Mapped[str] = mapped_column(String(64), default="milestone_1")
    capture_phase_band: Mapped[str] = mapped_column(String(64), default="evergreen")
    urgency_score: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    entry_reason: Mapped[str] = mapped_column(String(128), default="new_lead")
    intel_provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    field_answers: Mapped[list[PacketFieldAnswer]] = relationship(back_populates="opportunity")
    actions: Mapped[list[ActionMatrixItem]] = relationship(back_populates="opportunity")


class PacketFieldDefinition(Base):
    __tablename__ = "packet_field_definitions"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str] = mapped_column(String(128), nullable=False)
    value_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    required_gates: Mapped[list] = mapped_column(JSONB, default=list)
    route_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_slide: Mapped[str] = mapped_column(String(128), default="")


class PacketFieldAnswer(Base):
    __tablename__ = "packet_field_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    field_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="unanswered")
    trust_level: Mapped[str] = mapped_column(String(64), default="intake")
    review_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    opportunity: Mapped[Opportunity] = relationship(back_populates="field_answers")


class ActionMatrixItem(Base):
    __tablename__ = "action_matrix_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(256), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="open")
    linked_field_keys: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    opportunity: Mapped[Opportunity] = relationship(back_populates="actions")


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    trust_level: Mapped[str] = mapped_column(String(64), default="candidate")
    review_state: Mapped[str] = mapped_column(String(64), default="pending_review")
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CapabilityRun(Base):
    __tablename__ = "capability_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="pending_review")
    transcript: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OperatorTask(Base):
    __tablename__ = "operator_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_dump: Mapped[str] = mapped_column(Text, nullable=False)
    task_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(64), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    project_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    context_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    attendees: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    waiting_on: Mapped[str | None] = mapped_column(String(256), nullable=True)
    categories: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    checklist: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    llm_polish: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    opportunity: Mapped[Opportunity | None] = relationship()