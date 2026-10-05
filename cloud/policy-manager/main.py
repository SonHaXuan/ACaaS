"""
ACaaS Policy Manager Service (PMS) — Cloud Tier
FastAPI REST API for CRUD on ABAC/RBAC/ReBAC policies.
Backed by SQLite (dev) / PostgreSQL (production).
Every write is also committed to the Hyperledger Fabric PolicyChain.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from fastapi import FastAPI
import db
from routes.policies import router as policies_router
from routes.conflict import router as conflict_router
from routes.audit import router as audit_router

app = FastAPI(
    title="ACaaS Policy Manager Service",
    description="Privacy-Preserving Access Control as a Service — Cloud PMS",
    version="1.0.0",
)

app.include_router(policies_router)
app.include_router(conflict_router)
app.include_router(audit_router)


@app.on_event("startup")
def startup():
    db.init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "policy-manager"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PMS_PORT", 8001))
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "warning")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)
