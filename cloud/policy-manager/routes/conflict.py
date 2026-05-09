"""Conflict detection and resolution endpoint (Section 4.1)."""
from __future__ import annotations
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from fastapi import APIRouter
import db
from shared.models.policy import Policy
from models import ConflictReport

router = APIRouter(prefix="/conflicts", tags=["conflicts"])


def _policies_overlap(a: Policy, b: Policy) -> bool:
    """Two policies conflict if same subject+resource+action but different effect."""
    if a.rule.action != b.rule.action:
        return False
    if a.rule.resource.data_type != b.rule.resource.data_type:
        return False
    if a.rule.subject.role != b.rule.subject.role:
        return False
    if a.rule.effect == b.rule.effect:
        return False
    return True


@router.get("/", response_model=list[ConflictReport])
def detect_conflicts():
    policies = db.list_policies()
    conflicts: list[ConflictReport] = []
    seen = set()
    for i, pa in enumerate(policies):
        for pb in policies[i + 1:]:
            if _policies_overlap(pa, pb):
                key = tuple(sorted([pa.policy_id, pb.policy_id]))
                if key not in seen:
                    seen.add(key)
                    # Auto-resolution: deny-overrides (Section 3.1)
                    deny_policy = pa if pa.rule.effect == "DENY" else pb
                    conflicts.append(ConflictReport(
                        conflict_id=str(uuid.uuid4())[:8],
                        policy_ids=[pa.policy_id, pb.policy_id],
                        description=(
                            f"Overlapping rule for role={pa.rule.subject.role}, "
                            f"resource={pa.rule.resource.data_type}, "
                            f"action={pa.rule.action}"
                        ),
                        resolved=True,
                        resolution=f"deny-overrides: enforcing {deny_policy.policy_id}",
                    ))
    return conflicts
