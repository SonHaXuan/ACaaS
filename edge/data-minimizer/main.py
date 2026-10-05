"""
ACaaS Data Minimizer Service (edge tier).
Three-stage pipeline per Section 4.3:
  Stage 1 — Pseudonymization (HMAC-SHA256)
  Stage 2 — k-anonymity generalization
  Stage 3 — Role-based field redaction

Invoked by PEP after PDP returns PERMIT, before data leaves the edge.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from pseudonymizer import pseudonymize_record
from k_anonymity import generalize_record
from field_redactor import redact

app = FastAPI(title="ACaaS Data Minimizer", version="1.0.0")


class MinimizeRequest(BaseModel):
    record: dict
    role: str
    apply_pseudonymization: bool = True
    apply_k_anonymity: bool = True
    apply_redaction: bool = True


class MinimizeResponse(BaseModel):
    minimized_record: dict
    stages_applied: list[str]


@app.post("/minimize", response_model=MinimizeResponse)
def minimize(req: MinimizeRequest):
    record = dict(req.record)
    stages: list[str] = []

    if req.apply_pseudonymization:
        record = pseudonymize_record(record)
        stages.append("pseudonymization")

    if req.apply_k_anonymity:
        record = generalize_record(record)
        stages.append("k-anonymity-generalization")

    if req.apply_redaction:
        record = redact(record, req.role)
        stages.append("field-redaction")

    return MinimizeResponse(minimized_record=record, stages_applied=stages)


@app.get("/health")
def health():
    return {"status": "ok", "service": "data-minimizer"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DATA_MINIMIZER_PORT", 8004))
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "warning")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)

