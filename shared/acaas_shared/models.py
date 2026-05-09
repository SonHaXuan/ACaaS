from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubjectAttributes(BaseModel):
    role: str
    department: str
    clearance_level: int = 1


class ResourceAttributes(BaseModel):
    resource_type: str
    sensitivity: str
    owner_patient_id: str | None = None


class Conditions(BaseModel):
    locations: list[str] = Field(default_factory=list)
    time_range: list[int] | None = None
    require_assigned_department: bool = False
    emergency_only: bool = False


class PolicyRule(BaseModel):
    policy_id: str
    description: str = ""
    subject: SubjectAttributes
    resource: ResourceAttributes
    actions: list[str]
    conditions: Conditions = Field(default_factory=Conditions)
    effect: Literal["allow", "deny"]
    priority: int = 100


class PolicyRecord(BaseModel):
    policy_id: str
    version: int
    hash: str
    created_at: str
    updated_at: str
    status: Literal["active", "disabled"] = "active"
    rule: PolicyRule


class AccessRequest(BaseModel):
    subject: SubjectAttributes
    resource: ResourceAttributes
    action: str
    environment: dict[str, Any] = Field(default_factory=dict)


class AccessDecision(BaseModel):
    allowed: bool
    matched_policy_id: str | None = None
    matched_policy_version: int | None = None
    reason: str
    evaluated_at: str = Field(default_factory=utc_now)


class PolicyUpsertRequest(BaseModel):
    rule: PolicyRule


class SyncResponse(BaseModel):
    latest_version: int
    updates: list[PolicyRecord]


class AuditEvent(BaseModel):
    event_id: str
    decision: AccessDecision
    request: AccessRequest
    patient_id: str | None = None
    edge_node_id: str
    created_at: str = Field(default_factory=utc_now)

