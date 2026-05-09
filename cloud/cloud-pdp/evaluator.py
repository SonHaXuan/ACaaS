"""
Cloud PDP: feature-complete policy evaluator backed by Open Policy Agent.
Falls back to a pure-Python ABAC engine when OPA is not reachable,
so the service degrades gracefully in development.
"""
from __future__ import annotations
import os, json, time, datetime
import urllib.request, urllib.error
from typing import Any

OPA_URL = os.environ.get("OPA_URL", "http://localhost:8181")
OPA_POLICY_PATH = "/v1/data/acaas/allow"


def _check_time_range(tr: dict | None) -> bool:
    if not tr:
        return True
    now = datetime.datetime.now().strftime("%H:%M")
    return tr["start"] <= now <= tr["end"]


def _check_location(required: str | None, actual: str | None) -> bool:
    if not required or required == "*":
        return True
    return required == actual


def evaluate_python(request: dict, policy: dict) -> tuple[str, str]:
    """
    Pure-Python XACML-lite ABAC evaluation.
    Returns (effect, reason).
    deny-overrides combinator: DENY beats PERMIT (Section 3.1).
    """
    rule = policy.get("rule", {})
    subj = rule.get("subject", {})
    res  = rule.get("resource", {})
    cond = rule.get("condition", {})

    # subject match
    if subj.get("role") and subj["role"] != request.get("role"):
        return "NA", "role mismatch"
    if subj.get("department") and subj["department"] != request.get("department"):
        return "NA", "department mismatch"
    if subj.get("clearance_level", 1) > request.get("clearance_level", 1):
        return "NA", "clearance insufficient"

    # resource match
    if res.get("data_type") and res["data_type"] != request.get("resource_type"):
        return "NA", "resource type mismatch"

    # action match
    if rule.get("action") and rule["action"] != request.get("action"):
        return "NA", "action mismatch"

    # condition check
    if not _check_time_range(cond.get("time_range")):
        return "DENY", "outside allowed time window"
    if not _check_location(cond.get("location"), request.get("location")):
        return "NA", "location mismatch"

    return rule.get("effect", "DENY"), "matched"


def evaluate_opa(request: dict, policies: list[dict]) -> tuple[str, str]:
    """Call OPA REST API with the request context."""
    payload = json.dumps({
        "input": {
            "request": request,
            "policies": policies,
        }
    }).encode()
    try:
        req = urllib.request.Request(
            f"{OPA_URL}{OPA_POLICY_PATH}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read())
            allowed = result.get("result", {}).get("allow", False)
            return ("PERMIT" if allowed else "DENY"), "OPA decision"
    except Exception:
        return None, "OPA unreachable"


def evaluate(request: dict, policies: list[dict]) -> tuple[str, str, str]:
    """
    Evaluate an access request against the full policy set.
    Returns (decision, matched_policy_id, reason).
    Deny-overrides: if any matching policy returns DENY → DENY.
    """
    # Try OPA first
    opa_dec, opa_reason = evaluate_opa(request, policies)
    if opa_dec is not None:
        return opa_dec, "opa", opa_reason

    # Fallback: Python ABAC engine
    decisions: list[tuple[str, str, str]] = []  # (effect, pid, reason)
    for p in policies:
        effect, reason = evaluate_python(request, p)
        if effect != "NA":
            decisions.append((effect, p.get("policy_id", ""), reason))

    if not decisions:
        return "DENY", "", "no matching policy (default-deny)"

    # deny-overrides
    for effect, pid, reason in decisions:
        if effect == "DENY":
            return "DENY", pid, reason
    return "PERMIT", decisions[0][1], decisions[0][2]
