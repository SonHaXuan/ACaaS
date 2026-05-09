"""ACaaS Cloud PDP — feature-complete policy decision point."""
import sys, os, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from evaluator import evaluate
from blockchain.mock import fabric

# Import PMS db for policy retrieval (shared process in dev; separate service in prod)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../policy-manager"))
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


@app.post("/evaluate")
def evaluate_request(req: EvalRequest):
    t0 = time.time()
    req_id = req.request_id or str(uuid.uuid4())[:8]
    policies = [p.to_dict() for p in pms_db.list_policies()]
    decision, policy_id, reason = evaluate(req.dict(), policies)
    latency_ms = (time.time() - t0) * 1000

    log_entry = {
        "request_id": req_id,
        "subject_id": req.subject_id,
        "patient_id": req.patient_id,
        "resource_type": req.resource_type,
        "action": req.action,
        "decision": decision,
        "policy_id": policy_id,
        "reason": reason,
        "evaluated_by": "cloud-pdp",
        "latency_ms": round(latency_ms, 3),
    }
    fabric.append_log(log_entry)

    return {**log_entry, "request_id": req_id}


@app.get("/health")
def health():
    return {"status": "ok", "service": "cloud-pdp"}


if __name__ == "__main__":
    import uvicorn
    pms_db.init_db()
    uvicorn.run("main:app", host="0.0.0.0",
                port=int(os.environ.get("CLOUD_PDP_PORT", 8002)), reload=True)
