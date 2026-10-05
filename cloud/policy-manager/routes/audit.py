"""Audit and compliance endpoints — HIPAA / GDPR reports from LogChain."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from fastapi import APIRouter, Query
from blockchain.mock import fabric

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
def get_audit_logs(
    subject_id: str | None = Query(default=None),
    patient_id: str | None = Query(default=None),
):
    """Return immutable LogChain entries — basis for HIPAA audit trail."""
    return fabric.get_logs(subject_id=subject_id, patient_id=patient_id)


@router.get("/policy-chain")
def get_policy_chain():
    """Return all PolicyChain commits — GDPR data-governance evidence."""
    return fabric.policy_chain.all()


@router.get("/compliance/hipaa")
def hipaa_report():
    logs = fabric.get_logs()
    return {
        "total_access_events": len(logs),
        "permit_events": sum(1 for l in logs if l.get("decision") == "PERMIT"),
        "deny_events": sum(1 for l in logs if l.get("decision") == "DENY"),
        "unique_subjects": len({l.get("subject_id") for l in logs}),
        "unique_patients": len({l.get("patient_id") for l in logs}),
    }


@router.get("/replay")
def replay_decision(request_id: str = Query(...)):
    """
    Replay an access decision end-to-end (Section 4.4 / P0.5):
    Retrieves the logged decision from LogChain, reconstructs request attributes
    and policy at the recorded version, and re-executes the evaluator.
    """
    import importlib.util
    from fastapi import HTTPException
    import db as pms_db

    logs = fabric.get_logs()
    target = None
    for l in reversed(logs):
        if l.get("request_id") == request_id:
            target = l
            break

    if not target:
        raise HTTPException(status_code=404, detail=f"Log entry for request_id '{request_id}' not found")

    policy_id = target.get("policy_id")
    policy_version = target.get("policy_version", 0)
    original_decision = target.get("decision", "DENY")

    req_context = {
        "subject_id": target.get("subject_id"),
        "role": target.get("role", "doctor"),
        "department": target.get("department"),
        "clearance_level": target.get("clearance_level", 1),
        "patient_id": target.get("patient_id"),
        "resource_type": target.get("resource_type", "EHR"),
        "action": target.get("action", "read"),
        "location": target.get("location"),
    }

    policies = []
    if policy_id:
        p_obj = pms_db.get_policy(policy_id)
        if p_obj:
            policies.append(p_obj.to_dict())
        else:
            # Fallback to sync chain records
            sync_events = fabric.sync_chain.all()
            for ev in sync_events:
                if ev.get("policy_id") == policy_id:
                    policies.append({"policy_id": policy_id, "rule": ev.get("policy_body", {})})
                    break

    # Load evaluator from cloud-pdp
    eval_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../cloud-pdp/evaluator.py"))
    spec = importlib.util.spec_from_file_location("cloud_pdp_eval", eval_path)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail="Cannot load evaluator module")
    eval_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(eval_mod)

    replayed_decision, matched_pid, reason = eval_mod.evaluate(req_context, policies)
    return {
        "request_id": request_id,
        "matched": (replayed_decision == original_decision),
        "original_decision": original_decision,
        "replayed_decision": replayed_decision,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "reason": reason,
    }

