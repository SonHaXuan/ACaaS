"""
ACaaS Policy Enforcement Point (PEP) — edge tier.
Intercepts clinical application requests, invokes the Lightweight PDP,
then invokes the Data Minimizer if PERMIT.
Logs every decision to the Offline Queue (batch-uploaded to LogChain).
"""
from __future__ import annotations

import importlib.util
import sys, os, time, uuid, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import urllib.request
from cloud_escalation import escalate_to_cloud

EDGE_PDP_URL    = os.environ.get("EDGE_PDP_URL", "http://localhost:8003")
DATA_MIN_URL    = os.environ.get("DATA_MINIMIZER_URL", "http://localhost:8004")
CLOUD_PDP_URL   = os.environ.get("CLOUD_PDP_URL", "http://localhost:8002")
OFFLINE_QUEUE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "../offline-queue"))
if OFFLINE_QUEUE_DIR not in sys.path:
    sys.path.insert(0, OFFLINE_QUEUE_DIR)

try:
    import offline_queue
except ImportError:
    offline_queue = None

OFFLINE_QUEUE_PATH = os.path.join(OFFLINE_QUEUE_DIR, "offline_queue.py")

app = FastAPI(title="ACaaS Policy Enforcement Point", version="1.0.0")


class AccessRequest(BaseModel):
    subject_id: str
    role: str
    department: Optional[str] = None
    clearance_level: int = 1
    patient_id: str
    resource_type: str
    action: str
    location: Optional[str] = None
    ehr_record: Optional[dict] = None   # raw EHR data (only for read requests)


AccessRequest.model_rebuild()



def _post(url: str, payload: dict, timeout: int = 5) -> dict | None:
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return None


def _enqueue_log(entry: dict) -> None:
    """Persist to offline queue (fire-and-forget)."""
    try:
        if offline_queue is not None:
            offline_queue.enqueue(entry)
        else:
            spec = importlib.util.spec_from_file_location("acaas_offline_queue", OFFLINE_QUEUE_PATH)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.enqueue(entry)
    except Exception:
        pass


@app.post("/access")
def enforce(req: AccessRequest):
    request_id = str(uuid.uuid4())[:8]
    t0 = time.time()

    # Step 1: invoke Lightweight PDP
    pdp_payload = {
        "request_id": request_id,
        "subject_id": req.subject_id,
        "role": req.role,
        "department": req.department,
        "clearance_level": req.clearance_level,
        "patient_id": req.patient_id,
        "resource_type": req.resource_type,
        "action": req.action,
        "location": req.location,
    }
    pdp_result = _post(f"{EDGE_PDP_URL}/evaluate", pdp_payload)

    if pdp_result is None:
        # PDP unreachable → default-deny (fail-safe per Section 4.4)
        decision = "DENY"
        reason = "PDP unreachable — fail-safe deny"
        policy_id = None
        policy_version = 0
        policy_hash = ""
        latency_ms = (time.time() - t0) * 1000
    else:
        decision   = pdp_result.get("decision", "DENY")
        reason     = pdp_result.get("reason", "")
        policy_id  = pdp_result.get("policy_id")
        policy_version = pdp_result.get("policy_version", 0)
        policy_hash = pdp_result.get("policy_hash", "")
        latency_ms = pdp_result.get("latency_ms", 0)
        cache_hit  = pdp_result.get("cache_hit", policy_id is not None)

        # If cache miss (decision DENY and no matching policy at edge), escalate to Cloud PDP
        if decision == "DENY" and not cache_hit:
            cloud_res = escalate_to_cloud(pdp_payload, CLOUD_PDP_URL)
            if cloud_res:
                decision = cloud_res.get("decision", "DENY")
                reason = cloud_res.get("reason", reason)
                policy_id = cloud_res.get("policy_id")
                policy_version = cloud_res.get("policy_version", 0)
                policy_hash = cloud_res.get("policy_hash", "")
                latency_ms = (time.time() - t0) * 1000

    # Step 2: if PERMIT + record provided → run Data Minimizer
    minimized_record = None
    if decision == "PERMIT" and req.ehr_record:
        min_payload = {
            "record": req.ehr_record,
            "role": req.role,
        }
        min_result = _post(f"{DATA_MIN_URL}/minimize", min_payload)
        if min_result:
            minimized_record = min_result.get("minimized_record")

    # Step 3: queue access log for LogChain
    log_entry = {
        "request_id": request_id,
        "edge_id": os.environ.get("EDGE_NODE_ID", "edge-node-1"),
        "subject_id": req.subject_id,
        "role": req.role,
        "department": req.department,
        "clearance_level": req.clearance_level,
        "patient_id": req.patient_id,
        "resource_type": req.resource_type,
        "action": req.action,
        "location": req.location,
        "decision": decision,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "reason": reason,
        "latency_ms": round(latency_ms, 3),
        "evaluated_at": time.time(),
    }
    _enqueue_log(log_entry)

    if decision == "DENY":
        raise HTTPException(status_code=403, detail={
            "request_id": request_id,
            "decision": "DENY",
            "reason": reason,
        })

    return {
        "request_id": request_id,
        "decision": "PERMIT",
        "reason": reason,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_hash": policy_hash,
        "latency_ms": round(latency_ms, 3),
        "data": minimized_record,
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "pep"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PEP_PORT", 8005))
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "warning")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)

