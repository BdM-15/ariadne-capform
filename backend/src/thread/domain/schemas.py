from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from thread.domain.enums import (
    CapturePhaseBand,
    LifecycleState,
    MilestoneGate,
    PacketFieldAnswerStatus,
    PacketFieldRouteKind,
    PacketFieldValueKind,
    PacketSection,
    ResearchLens,
    ReviewState,
    TrustLevel,
)


class ProvenanceLink(BaseModel):
    kind: str
    ref: str
    excerpt: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class OpportunityCreate(BaseModel):
    name: str
    capture_phase_band: CapturePhaseBand = CapturePhaseBand.EVERGREEN
    entry_reason: str = "new_lead"
    award_key: str | None = None
    naics_code: str | None = None


class OpportunityOut(BaseModel):
    id: UUID
    name: str
    slug: str
    lifecycle_state: str
    current_milestone_gate: str
    capture_phase_band: str
    urgency_score: float
    freshness_at: datetime
    pending_review_count: int = 0
    intel_provenance: dict[str, Any] | None = None


class PacketFieldDefinitionOut(BaseModel):
    key: str
    label: str
    question: str
    section: PacketSection
    value_kind: PacketFieldValueKind
    required_gates: list[MilestoneGate]
    route_kind: PacketFieldRouteKind
    reference_slide: str


class PacketFieldAnswerOut(BaseModel):
    field_key: str
    value: str | None = None
    status: PacketFieldAnswerStatus
    trust_level: TrustLevel
    review_state: ReviewState | None = None
    provenance: list[ProvenanceLink] = Field(default_factory=list)


class PacketView(BaseModel):
    opportunity_id: UUID
    milestone_gate: MilestoneGate
    fields: list[PacketFieldAnswerOut]


class ActionMatrixItemCreate(BaseModel):
    action: str
    owner: str | None = None
    due_date: date | None = None
    linked_field_keys: list[str] = Field(default_factory=list)


class ActionMatrixItemOut(ActionMatrixItemCreate):
    id: UUID
    status: str = "open"


class ReviewRecordOut(BaseModel):
    id: UUID
    entity_type: str
    entity_id: str
    trust_level: TrustLevel
    review_state: ReviewState
    reviewer_note: str | None = None


class ReviewDecision(BaseModel):
    note: str | None = None
    edited_value: str | None = None


class ResearchRunCreate(BaseModel):
    opportunity_id: UUID | None = None
    lens: ResearchLens
    query: str
    max_sources: int = Field(default=5, ge=1, le=10)


class ResearchProviderOut(BaseModel):
    id: str
    name: str
    role: str
    priority: int
    status: str
    detail: str


class ResearchRunOut(BaseModel):
    run_id: str
    status: str
    lens: str
    query: str
    source_count: int
    finding_count: int
    interpretation: str | None = None
    review_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class HealthOut(BaseModel):
    status: str
    version: str
    postgres_ready: bool
    intel_row_count: int | None = None
    grok_configured: bool
    ollama_reachable: bool = False
    vault_healthy: bool = False
    research_providers: dict[str, str] = Field(default_factory=dict)
    langgraph_enabled: bool = False
    langgraph_studio_port: int = 9623
    langsmith_configured: bool = False
    langsmith_tracing: bool = False