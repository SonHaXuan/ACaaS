"""ACaaS AccessRequest and AccessDecision data models."""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AccessRequest:
    request_id: str
    subject_id: str
    role: str
    department: Optional[str]
    clearance_level: int
    patient_id: str
    resource_type: str       # EHR | lab_result | medication | vitals
    action: str              # read | write | delete
    location: Optional[str]  # hospital_id
    timestamp: float = field(default_factory=time.time)
    device_id: Optional[str] = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class AccessDecision:
    request_id: str
    subject_id: str
    decision: str            # PERMIT | DENY | NA
    policy_id: Optional[str]
    policy_version: Optional[int]
    reason: str
    evaluated_at: float = field(default_factory=time.time)
    evaluated_by: str = "edge-pdp"   # edge-pdp | cloud-pdp | fog-cache
    latency_ms: float = 0.0
    minimized_data: Optional[dict] = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()
