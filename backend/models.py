from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AnalysisStatus(str, Enum):
    VALIDATING = "VALIDATING"
    COMPUTING_BASELINE = "COMPUTING_BASELINE"
    UPLOADING = "UPLOADING"
    CONNECTING = "CONNECTING"
    ANALYZING = "ANALYZING"
    READING_RESULTS = "READING_RESULTS"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class KeyFinding(BaseModel):
    title: str
    evidence: str
    metric: str
    confidence: str = "medium"


class DishRecommendation(BaseModel):
    dish_name: str
    baseline_qty: int = Field(ge=0)
    recommended_qty: int = Field(ge=0)
    reason: str = ""
    risk: str = ""


class ActionItem(BaseModel):
    priority: str = "medium"
    action: str
    expected_impact: str = ""


class AIResult(BaseModel):
    executive_summary: str = ""
    key_findings: list[KeyFinding] = []
    dish_recommendations: list[DishRecommendation] = []
    action_items: list[ActionItem] = []
    limitations: list[str] = []


class ScenarioRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=100)


class AnalysisResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    progress: int = 0
    message: str = ""
    metrics: dict[str, Any] = {}
    baseline: dict[str, Any] = {}
    result: AIResult | None = None
    task_id: str | None = None
    error: str | None = None
