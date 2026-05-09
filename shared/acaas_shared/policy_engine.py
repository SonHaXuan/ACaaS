from __future__ import annotations

from acaas_shared.models import AccessDecision, AccessRequest, PolicyRecord


def _matches_subject(policy: PolicyRecord, request: AccessRequest) -> bool:
    s = policy.rule.subject
    q = request.subject
    return (
        s.role == q.role
        and s.department == q.department
        and q.clearance_level >= s.clearance_level
    )


def _matches_resource(policy: PolicyRecord, request: AccessRequest) -> bool:
    r = policy.rule.resource
    q = request.resource
    if r.resource_type != q.resource_type or r.sensitivity != q.sensitivity:
        return False
    if r.owner_patient_id and q.owner_patient_id and r.owner_patient_id != q.owner_patient_id:
        return False
    return True


def _matches_conditions(policy: PolicyRecord, request: AccessRequest) -> bool:
    conditions = policy.rule.conditions
    env = request.environment
    if conditions.locations:
        if env.get("location") not in conditions.locations:
            return False
    if conditions.time_range:
        hour = int(env.get("hour", 0))
        start, end = conditions.time_range
        if hour < start or hour > end:
            return False
    if conditions.require_assigned_department:
        if env.get("assigned_department") != request.subject.department:
            return False
    if conditions.emergency_only and not env.get("emergency", False):
        return False
    return True


def evaluate_policies(policies: list[PolicyRecord], request: AccessRequest) -> AccessDecision:
    active = sorted(
        [policy for policy in policies if policy.status == "active"],
        key=lambda item: item.rule.priority,
    )
    deny_match: PolicyRecord | None = None
    allow_match: PolicyRecord | None = None

    for policy in active:
        if request.action not in policy.rule.actions:
            continue
        if not _matches_subject(policy, request):
            continue
        if not _matches_resource(policy, request):
            continue
        if not _matches_conditions(policy, request):
            continue
        if policy.rule.effect == "deny":
            deny_match = policy
            break
        if allow_match is None:
            allow_match = policy

    if deny_match:
        return AccessDecision(
            allowed=False,
            matched_policy_id=deny_match.policy_id,
            matched_policy_version=deny_match.version,
            reason="Denied by matching policy",
        )
    if allow_match:
        return AccessDecision(
            allowed=True,
            matched_policy_id=allow_match.policy_id,
            matched_policy_version=allow_match.version,
            reason="Allowed by matching policy",
        )
    return AccessDecision(allowed=False, reason="No matching policy")
