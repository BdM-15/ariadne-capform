from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class Quest(BaseModel):
    id: Optional[UUID] = None
    quest_id: str
    objective: str
    target_hero: str
    status: str = "backlog"
    est_minutes: Optional[int] = None
    base_xp: Optional[int] = None
    est_pwin_delta: Optional[float] = None
    actual_minutes: Optional[int] = None
    xp_earned: Optional[int] = None
    pwin_delta_realized: Optional[float] = None
    evidence: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class HeroActivity(BaseModel):
    hero: str
    action_type: str
    quest_id: Optional[str] = None
    description: str
    xp_gained: Optional[int] = None
    pwin_impact: Optional[float] = None

class PwinRecord(BaseModel):
    pwin_value: float
    notes: Optional[str] = None

class AgentLog(BaseModel):
    hero: str
    task: Optional[str] = None
    model_used: Optional[str] = None
    status: str
    duration_ms: Optional[int] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None

class DashboardMetrics(BaseModel):
    active_quests: int
    completed_quests: int
    active_heroes: int
    current_pwin: float
    total_xp_earned: int