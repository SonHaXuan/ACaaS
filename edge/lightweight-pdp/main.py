"""
ACaaS Edge Lightweight PDP — REST endpoint.
Responds to PEP queries in <10ms from local policy store.
Falls back to cloud PDP when policy is missing or version is stale.
"""
from __future__ import annotations

import sys, os, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../local-policy-store"))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from evaluator import evaluate
import store
import urllib.request, json

CLOUD_PDP_URL = os.environ.get("CLOUD_PDP_URL", "http://localhost:8002")

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


def _cloud_fallback(req: EvalRequest) -> dict | None:
    try:
        payload = json.dumps(req.dict()).encode()
        r = urllib.request.Request(
            f"{CLOUD_PDP_URL}/evaluate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(r, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


@app.post("/evaluate")
def evaluate_request(req: EvalRequest):
    req_id = req.request_id or str(uuid.uuid4())[:8]
    decision, policy_id, reason, latency_ms = evaluate(req.dict())

    # If no local policy matched, fallback to cloud PDP
    if decision == "DENY" and policy_id is None:
        cloud_result = _cloud_fallback(req)
        if cloud_result:
            cloud_result["evaluated_by"] = "cloud-pdp-fallback"
            return cloud_result

    return {
        "request_id": req_id,
        "subject_id": req.subject_id,
        "patient_id": req.patient_id,
        "decision": decision,
        "policy_id": policy_id,
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
    uvicorn.run("main:app", host="0.0.0.0",
                port=int(os.environ.get("EDGE_PDP_PORT", 8003)), reload=True)
