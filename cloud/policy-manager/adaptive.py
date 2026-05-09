"""
Adaptive policy deployment scoring (Equation 5 from Section 4.4).

  score(p) = α·f(p) + β·c(p) + γ·|p|^(-1)

Four-quadrant placement:
  high-crit + high-freq  → edge   (long TTL)
  high-crit + low-freq   → fog    (1-hour TTL)
  low-crit  + high-freq  → edge   (LRU eviction)
  low-crit  + low-freq   → cloud  (never pushed to edge)
"""
from __future__ import annotations
import json
from dataclasses import asdict
from shared.models.policy import Policy

ALPHA = 0.4   # weight for frequency
BETA  = 0.4   # weight for criticality
GAMMA = 0.2   # weight for compactness (inverse size)

HIGH_CRIT = 3.0   # threshold for "high criticality"
HIGH_FREQ = 50.0  # threshold for "high frequency" (accesses / hour)


def score(policy: Policy) -> float:
    size = max(1, len(json.dumps(asdict(policy.rule))))
    return ALPHA * policy.frequency + BETA * policy.criticality + GAMMA / size


def assign_tier(policy: Policy) -> str:
    s = score(policy)
    high_c = policy.criticality >= HIGH_CRIT
    high_f = policy.frequency >= HIGH_FREQ
    if high_c and high_f:
        return "edge"
    if high_c and not high_f:
        return "fog"
    if not high_c and high_f:
        return "edge"
    return "cloud"


def update_deployment_tier(policy: Policy) -> Policy:
    policy.deployment_tier = assign_tier(policy)
    return policy
