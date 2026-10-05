"""CRUD endpoints for ACaaS policies."""
from __future__ import annotations
import sys, os, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from fastapi import APIRouter, HTTPException, status
from dataclasses import asdict
from shared.models.policy import (
    Policy, PolicyRule, SubjectAttributes, ResourceAttributes,
    Condition, TimeRange
)
import db, adaptive
from blockchain.mock import fabric
from models import CreatePolicyRequest, UpdatePolicyRequest, PolicyResponse

router = APIRouter(prefix="/policies", tags=["policies"])


def _build_policy(req: CreatePolicyRequest) -> Policy:
    tr = req.rule.condition.time_range
    cond = Condition(
        time_range=TimeRange(tr.start, tr.end) if tr else None,
        location=req.rule.condition.location,
        extra=req.rule.condition.extra,
    )
    rule = PolicyRule(
        subject=SubjectAttributes(
            role=req.rule.subject.role,
            department=req.rule.subject.department,
            clearance_level=req.rule.subject.clearance_level,
        ),
        resource=ResourceAttributes(
            data_type=req.rule.resource.data_type,
            sensitivity=req.rule.resource.sensitivity,
        ),
        action=req.rule.action,
        condition=cond,
        effect=req.rule.effect,
    )
    policy = Policy(
        policy_id=req.policy_id,
        rule=rule,
        criticality=req.criticality,
    )
    return policy


def _to_response(p: Policy) -> PolicyResponse:
    return PolicyResponse(
        policy_id=p.policy_id,
        version=p.version,
        hash=p.hash,
        rule=asdict(p.rule),
        criticality=p.criticality,
        deployment_tier=p.deployment_tier,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


@router.post("/", response_model=PolicyResponse,
             status_code=status.HTTP_201_CREATED)
def create_policy(req: CreatePolicyRequest):
    if db.get_policy(req.policy_id):
        raise HTTPException(409, "Policy already exists")
    policy = _build_policy(req)
    cur_v, _ = fabric.get_policy_version(policy.policy_id)
    policy.version = cur_v + 1
    policy.seal()
    adaptive.update_deployment_tier(policy)
    db.upsert_policy(policy)
    fabric.commit_policy(policy.policy_id, policy.hash, policy_body=asdict(policy.rule), expected_prev_version=cur_v)
    return _to_response(policy)


@router.post("/batch", response_model=list[PolicyResponse],
             status_code=status.HTTP_201_CREATED)
def create_policies_batch(reqs: list[CreatePolicyRequest]):
    created = []
    for req in reqs:
        policy = _build_policy(req)
        existing = db.get_policy(req.policy_id)
        if existing:
            prev_v = existing.version
            policy.version = prev_v + 1
        else:
            prev_v, _ = fabric.get_policy_version(policy.policy_id)
            policy.version = prev_v + 1
        policy.seal()
        adaptive.update_deployment_tier(policy)
        db.upsert_policy(policy)
        fabric.commit_policy(policy.policy_id, policy.hash, policy_body=asdict(policy.rule), expected_prev_version=prev_v)
        created.append(_to_response(policy))
    return created


@router.get("/", response_model=list[PolicyResponse])
def list_policies():
    return [_to_response(p) for p in db.list_policies()]


@router.get("/{policy_id}", response_model=PolicyResponse)
def get_policy(policy_id: str):
    p = db.get_policy(policy_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    return _to_response(p)


@router.put("/{policy_id}", response_model=PolicyResponse)
def update_policy(policy_id: str, req: UpdatePolicyRequest):
    existing = db.get_policy(policy_id)
    if not existing:
        raise HTTPException(404, "Policy not found")

    if req.rule:
        tr = req.rule.condition.time_range
        existing.rule.condition.time_range = (
            TimeRange(tr.start, tr.end) if tr else None
        )
        existing.rule.condition.location = req.rule.condition.location
        existing.rule.subject.role = req.rule.subject.role
        existing.rule.subject.department = req.rule.subject.department
        existing.rule.resource.data_type = req.rule.resource.data_type
        existing.rule.action = req.rule.action
        existing.rule.effect = req.rule.effect
    if req.criticality is not None:
        existing.criticality = req.criticality

    prev_version = existing.version
    existing.version += 1
    existing.updated_at = time.time()
    existing.seal()
    adaptive.update_deployment_tier(existing)
    db.upsert_policy(existing)
    fabric.commit_policy(existing.policy_id, existing.hash, policy_body=asdict(existing.rule), expected_prev_version=prev_version)
    return _to_response(existing)



@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: str):
    if not db.delete_policy(policy_id):
        raise HTTPException(404, "Policy not found")
    fabric.delete_policy(policy_id)
