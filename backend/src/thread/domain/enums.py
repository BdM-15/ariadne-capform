from __future__ import annotations

from enum import StrEnum


class LifecycleState(StrEnum):
    IDENTIFIED = "identified"
    QUALIFIED = "qualified"
    PURSUING = "pursuing"
    BID_DECIDED = "bid_decided"
    SUBMITTED = "submitted"
    AWARDED = "awarded"
    LOST = "lost"
    ARCHIVED = "archived"


class MilestoneGate(StrEnum):
    MILESTONE_1 = "milestone_1"
    MILESTONE_2 = "milestone_2"
    MILESTONE_3 = "milestone_3"
    MILESTONE_4 = "milestone_4"


class CapturePhaseBand(StrEnum):
    EVERGREEN = "evergreen"
    ACTIVATION = "activation"


class TrustLevel(StrEnum):
    INTAKE = "intake"
    CANDIDATE = "candidate"
    TRUSTED = "trusted"


class ReviewState(StrEnum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ROUTED = "routed"


class PacketSection(StrEnum):
    OPPORTUNITY_OVERVIEW = "opportunity_overview"
    CUSTOMER_CONTEXT = "customer_context"
    REQUIREMENTS_AND_SCOPE = "requirements_and_scope"
    COMPETITIVE_POSITION = "competitive_position"
    SOLUTION_STRATEGY = "solution_strategy"
    PRICE_TO_WIN = "price_to_win"
    RISKS_AND_GAPS = "risks_and_gaps"
    RECOMMENDATION_AND_NEXT_ACTIONS = "recommendation_and_next_actions"


class PacketFieldValueKind(StrEnum):
    TEXT = "text"
    PROSE = "prose"
    ENTITY = "entity"
    DATE = "date"
    MONEY = "money"
    PERCENTAGE = "percentage"
    DECISION = "decision"
    BOOLEAN = "boolean"


class PacketFieldAnswerStatus(StrEnum):
    UNANSWERED = "unanswered"
    ANSWERED = "answered"
    NEEDS_REVIEW = "needs_review"
    GAP = "gap"
    ASSUMPTION = "assumption"


class PacketFieldRouteKind(StrEnum):
    SOURCE_BACKED_ANSWER = "source_backed_answer"
    RESEARCH_OR_MCP = "research_or_mcp"
    SOURCE_PROFILE_LOOKUP = "source_profile_lookup"
    MODEL_SYNTHESIS = "model_synthesis"
    CUSTOMER_CALL_PLAN = "customer_call_plan"


class ResearchLens(StrEnum):
    CUSTOMER_RESEARCH = "customer_research"
    COMPETITIVE_POSITIONING = "competitive_positioning"
    PRODUCT_POSITIONING = "product_positioning"
    PRICE_TO_WIN = "price_to_win"
    CALL_PLAN_CRO = "call_plan_cro"