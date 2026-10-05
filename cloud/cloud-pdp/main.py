"""ACaaS Cloud PDP — feature-complete policy decision point."""
import sys, os, time, uuid

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from evaluator import evaluate
from blockchain.mock import fabric

# Import PMS db for policy retrieval (shared process in dev; separate service in prod)
PMS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../policy-manager"))
if PMS_DIR not in sys.path:
    sys.path.append(PMS_DIR)
import db as pms_db

app = FastAPI(title="ACaaS Cloud PDP", version="1.0.0")


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
    t0 = time.time()
    req_id = req.request_id or str(uuid.uuid4())[:8]
    policies = [p.to_dict() for p in pms_db.list_policies()]
    decision, policy_id, reason = evaluate(req.dict(), policies)
    latency_ms = (time.time() - t0) * 1000

    policy_version = 0
    policy_hash = ""
    if policy_id:
        p_obj = pms_db.get_policy(policy_id)
        if p_obj:
            policy_version = p_obj.version
            policy_hash = p_obj.hash

    log_entry = {
        "request_id": req_id,
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
        "evaluated_by": "cloud-pdp",
        "latency_ms": round(latency_ms, 3),
        "evaluated_at": time.time(),
    }
    fabric.append_log(log_entry)

    return {**log_entry, "request_id": req_id}


@app.get("/health")
def health():
    return {"status": "ok", "service": "cloud-pdp"}


if __name__ == "__main__":
    import uvicorn
    pms_db.init_db()
    port = int(os.environ.get("CLOUD_PDP_PORT", 8002))
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "warning")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)

