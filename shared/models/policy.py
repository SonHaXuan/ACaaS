"""
ACaaS shared policy data model.
A committed policy p = (id, π, v, h, σ) per Section 3.2 of the paper.
"""
from __future__ import annotations
import hashlib, json, time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class SubjectAttributes:
    role: str                        # doctor, nurse, researcher, admin
    department: Optional[str] = None
    clearance_level: int = 1         # 1-5


@dataclass
class ResourceAttributes:
    data_type: str                   # EHR, lab_result, medication, ...
    sensitivity: int = 1             # 1-5


@dataclass
class TimeRange:
    start: str  # "HH:MM"
    end: str    # "HH:MM"


@dataclass
class Condition:
    time_range: Optional[TimeRange] = None
    location: Optional[str] = None   # hospital_id or "*"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyRule:
    """ABAC rule π : S × R × A × E → {PERMIT, DENY, NA}"""
    subject: SubjectAttributes
    resource: ResourceAttributes
    action: str              # read | write | delete
    condition: Condition
    effect: str              # PERMIT | DENY


@dataclass
class Policy:
    policy_id: str
    rule: PolicyRule
    version: int = 1
    hash: str = ""           # SHA-256 of canonical rule encoding
    issuer_sig: str = ""     # placeholder for EUF-CMA signature
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    criticality: float = 1.0       # admin-assigned, used in adaptive score
    frequency: float = 0.0         # observed access frequency
    deployment_tier: str = "cloud" # cloud | fog | edge

    def compute_hash(self) -> str:
        canonical = json.dumps(asdict(self.rule), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def seal(self) -> None:
        self.hash = self.compute_hash()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Policy":
        rule = PolicyRule(
            subject=SubjectAttributes(**d["rule"]["subject"]),
            resource=ResourceAttributes(**d["rule"]["resource"]),
            action=d["rule"]["action"],
            condition=Condition(**{
                k: TimeRange(**v) if k == "time_range" and v else v
                for k, v in d["rule"]["condition"].items()
            }),
            effect=d["rule"]["effect"],
        )
        return Policy(
            policy_id=d["policy_id"],
            rule=rule,
            version=d.get("version", 1),
            hash=d.get("hash", ""),
            issuer_sig=d.get("issuer_sig", ""),
            created_at=d.get("created_at", time.time()),
            updated_at=d.get("updated_at", time.time()),
            criticality=d.get("criticality", 1.0),
            frequency=d.get("frequency", 0.0),
            deployment_tier=d.get("deployment_tier", "cloud"),
        )
