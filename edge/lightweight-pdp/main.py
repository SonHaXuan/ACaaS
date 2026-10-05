"""
ACaaS Edge Lightweight PDP — REST endpoint.
Responds to PEP queries in <10ms from local policy store.
Pure local decision point: no external WAN communication.
"""
from __future__ import annotations

import sys, os, time, uuid, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../local-policy-store"))
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from evaluator import evaluate
import store

app = FastAPI(title="ACaaS Edge Lightweight PDP", version="1.0.0")


class EvalRequest(BaseModel):
    request_id: Optional[str] = None
    subject_id: str
    role: str
    department: Optional[str] = None
    clearance_level: int = 1
    patient_id: str
    resource_type: str
    action: str
    location: Optional[str] = None


EvalRequest.model_rebuild()



@app.post("/evaluate")
def evaluate_request(req: EvalRequest):
    req_id = req.request_id or str(uuid.uuid4())[:8]
    decision, policy_id, reason, latency_ms = evaluate(req.dict())
    cache_hit = (policy_id is not None)

    version = 0
    policy_hash = ""
    if policy_id:
        p_row = store.get(policy_id)
        if p_row:
            version = p_row.get("version", 0)
            policy_hash = p_row.get("hash", "")

    return {
        "request_id": req_id,
        "subject_id": req.subject_id,
        "patient_id": req.patient_id,
        "decision": decision,
        "policy_id": policy_id,
        "policy_version": version,
        "policy_hash": policy_hash,
        "cache_hit": cache_hit,
        "reason": reason,
        "evaluated_by": "edge-pdp",
        "latency_ms": round(latency_ms, 3),
    }


@app.get("/health")
def health():
    policy_count = len(store.list_all())
    last_version = store.get_last_version()
    return {
        "status": "ok",
        "service": "edge-pdp",
        "cached_policies": policy_count,
        "last_sync_version": last_version,
    }


@app.on_event("startup")
def startup():
    store.init()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("EDGE_PDP_PORT", 8003))
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "warning")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)

