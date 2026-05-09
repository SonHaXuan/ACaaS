"""Pydantic models for the Policy Manager REST API."""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
import time


class SubjectAttrsIn(BaseModel):
    role: str
    department: Optional[str] = None
    clearance_level: int = Field(default=1, ge=1, le=5)


class ResourceAttrsIn(BaseModel):
    data_type: str
    sensitivity: int = Field(default=1, ge=1, le=5)


class TimeRangeIn(BaseModel):
    start: str  # "HH:MM"
    end: str


class ConditionIn(BaseModel):
    time_range: Optional[TimeRangeIn] = None
    location: Optional[str] = None
    extra: dict = {}


class PolicyRuleIn(BaseModel):
    subject: SubjectAttrsIn
    resource: ResourceAttrsIn
    action: str              # read | write | delete
    condition: ConditionIn
    effect: str              # PERMIT | DENY


class CreatePolicyRequest(BaseModel):
    policy_id: str
    rule: PolicyRuleIn
    criticality: float = Field(default=1.0, ge=0.0, le=5.0)


class UpdatePolicyRequest(BaseModel):
    rule: Optional[PolicyRuleIn] = None
    criticality: Optional[float] = None


class PolicyResponse(BaseModel):
    policy_id: str
    version: int
    hash: str
    rule: dict
    criticality: float
    deployment_tier: str
    created_at: float
    updated_at: float


class ConflictReport(BaseModel):
    conflict_id: str
    policy_ids: list[str]
    description: str
    resolved: bool
    resolution: Optional[str] = None
