from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.audit_service.main import app as audit_app
from services.data_minimizer.main import app as minimizer_app
from services.edge_gateway.main import app as edge_app
from services.policy_manager.main import app as policy_app
from services.sync_service.main import app as sync_app


def serve(app, port: int) -> uvicorn.Server:
    config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(0.8)
    return server


def main() -> None:
    (ROOT / "data/ledger/access_logs.jsonl").write_text("", encoding="utf-8")
    servers = [
        serve(policy_app, 8001),
        serve(sync_app, 8002),
        serve(minimizer_app, 8003),
        serve(audit_app, 8004),
        serve(edge_app, 8005),
    ]

    with httpx.Client(timeout=10) as client:
        print(client.post("http://127.0.0.1:8005/edge/sync").json())
        response = client.post(
            "http://127.0.0.1:8005/edge/access",
            json={
                "request": {
                    "subject": {
                        "role": "doctor",
                        "department": "cardiology",
                        "clearance_level": 2,
                    },
                    "resource": {
                        "resource_type": "EHR",
                        "sensitivity": "medium",
                        "owner_patient_id": "P123",
                    },
                    "action": "read",
                    "environment": {
                        "location": "clinic-a",
                        "hour": 9,
                        "assigned_department": "cardiology",
                    },
                }
            },
        )
        print(json.dumps(response.json(), indent=2))
        logs = client.get("http://127.0.0.1:8004/audit/events").json()
        print(json.dumps({"audit_events": logs}, indent=2))

    for server in servers:
        server.should_exit = True


if __name__ == "__main__":
    main()
