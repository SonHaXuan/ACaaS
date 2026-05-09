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
