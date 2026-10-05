"""
ACaaS End-to-End Integration Test Suite.
Verifies the complete flow across Cloud PMS, PolicyChain/SyncChain,
Edge Store, Edge PDP, PEP, Data Minimizer, Offline Queue, and Audit Replay.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_module(rel_path: str, mod_name: str):
    full_path = os.path.join(ROOT, rel_path)
    module_dir = os.path.dirname(full_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location(mod_name, full_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pms_mod = _load_module("cloud/policy-manager/main.py", "pms_main_int")
sync_mod = _load_module("sync/server/sync_server.py", "sync_main_int")
pdp_mod = _load_module("edge/lightweight-pdp/main.py", "pdp_main_int")
minimizer_mod = _load_module("edge/data-minimizer/main.py", "minimizer_main_int")
pep_mod = _load_module("edge/pep/main.py", "pep_main_int")
store_mod = _load_module("edge/local-policy-store/store.py", "store_int")
queue_mod = _load_module("edge/offline-queue/offline_queue.py", "queue_int")

pms_db_mod = _load_module("cloud/policy-manager/db.py", "pms_db_int")

from blockchain.mock import fabric


@pytest.fixture(autouse=True)
def setup_test_dbs(monkeypatch):
    temp_dir = tempfile.mkdtemp()
    pms_db = os.path.join(temp_dir, "pms_test.db")
    edge_db = os.path.join(temp_dir, "edge_test.db")
    queue_db = os.path.join(temp_dir, "queue_test.db")

    monkeypatch.setenv("QUEUE_DB_PATH", queue_db)
    monkeypatch.setenv("PMS_DB_PATH", pms_db)
    monkeypatch.setenv("STORE_DB_PATH", edge_db)

    monkeypatch.setattr(pms_db_mod, "DB_PATH", pms_db)
    pms_db_mod.init_db()
    if "db" in sys.modules:
        monkeypatch.setattr(sys.modules["db"], "DB_PATH", pms_db)
        sys.modules["db"].init_db()

    monkeypatch.setattr(store_mod, "DB_PATH", edge_db)
    monkeypatch.setattr(store_mod, "_global_conn", None)
    store_mod.init()
    if "store" in sys.modules:
        monkeypatch.setattr(sys.modules["store"], "DB_PATH", edge_db)
        monkeypatch.setattr(sys.modules["store"], "_global_conn", None)
        sys.modules["store"].init()

    monkeypatch.setattr(queue_mod, "DB_PATH", queue_db)
    queue_mod._init()
    if "offline_queue" in sys.modules:
        monkeypatch.setattr(sys.modules["offline_queue"], "DB_PATH", queue_db)
        sys.modules["offline_queue"]._init()
    if hasattr(pep_mod, "offline_queue") and pep_mod.offline_queue is not None:
        monkeypatch.setattr(pep_mod.offline_queue, "DB_PATH", queue_db)
        pep_mod.offline_queue._init()
    yield
    store_mod._global_conn = None
    if "store" in sys.modules:
        sys.modules["store"]._global_conn = None





def test_end_to_end_edge_flow(monkeypatch) -> None:
    pms_client = TestClient(pms_mod.app)
    sync_client = TestClient(sync_mod.app)
    pdp_client = TestClient(pdp_mod.app)
    minimizer_client = TestClient(minimizer_mod.app)
    pep_client = TestClient(pep_mod.app)

    # Wire PEP inter-service HTTP calls to in-process TestClients
    def fake_pep_post(url: str, payload: dict, timeout: int = 5):
        if url.endswith("/evaluate"):
            res = pdp_client.post("/evaluate", json=payload)
            return res.json()
        if url.endswith("/minimize"):
            res = minimizer_client.post("/minimize", json=payload)
            return res.json()
        return None

    def fake_escalate(pdp_payload: dict, cloud_pdp_url: str = None, timeout: int = 5):
        res = pdp_client.post("/evaluate", json=pdp_payload)
        out = res.json()
        out["evaluated_by"] = "cloud-pdp-mocked"
        return out

    monkeypatch.setattr(pep_mod, "_post", fake_pep_post)
    monkeypatch.setattr(pep_mod, "escalate_to_cloud", fake_escalate)

    # 1. Cloud PMS: Create Policy
    policy_id = "test-cardio-read"
    create_payload = {
        "policy_id": policy_id,
        "rule": {
            "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
            "resource": {"data_type": "EHR", "sensitivity": 3},
            "action": "read",
            "condition": {"time_range": None, "location": None, "extra": {}},
            "effect": "PERMIT",
        },
        "criticality": 3.5,
    }
    pms_res = pms_client.post("/policies/", json=create_payload)
    assert pms_res.status_code == 201
    p_data = pms_res.json()
    assert p_data["policy_id"] == policy_id
    assert p_data["version"] == 1
    policy_hash = p_data["hash"]

    # 2. Sync Server: Pull delta for edge node
    delta_res = sync_client.get("/delta/edge-node-1?from_version=0")
    assert delta_res.status_code == 200
    events = delta_res.json()["events"]
    assert len(events) >= 1
    event = [e for e in events if e["policy_id"] == policy_id][0]
    assert event["new_version"] == 1

    # 3. Edge Store: Apply policy and verify hash
    rule_str = json.dumps(event["policy_body"], sort_keys=True)
    applied = store_mod.upsert(
        policy_id=policy_id,
        rule_json=rule_str,
        version=event["new_version"],
        policy_hash=event["hash"],
        effect=event["policy_body"]["effect"],
    )
    assert applied is True
    assert store_mod.verify_hash(policy_id, policy_hash) is True

    # 4. INV_mono rollback rejection test
    rollback_applied = store_mod.upsert(
        policy_id=policy_id,
        rule_json=rule_str,
        version=1,  # same or lower version
        policy_hash=event["hash"],
        effect="DENY",
    )
    assert rollback_applied is False, "INV_mono violation: rollback version must be rejected"

    # 5. Direct Edge PDP Evaluation
    eval_req = {
        "subject_id": "dr-jones",
        "role": "doctor",
        "department": "cardiology",
        "clearance_level": 2,
        "patient_id": "P999",
        "resource_type": "EHR",
        "action": "read",
        "location": "ward-1",
    }
    pdp_res = pdp_client.post("/evaluate", json=eval_req)
    assert pdp_res.status_code == 200
    pdp_decision = pdp_res.json()
    assert pdp_decision["decision"] == "PERMIT"
    assert pdp_decision["policy_id"] == policy_id
    assert pdp_decision["cache_hit"] is True

    # 6. PEP Full Access Pipeline with Data Minimization
    access_req = {
        **eval_req,
        "ehr_record": {
            "patient_id": "P999",
            "name": "Jane Doe",
            "date_of_birth": "1988-04-12",
            "postal_code": "90210",
            "diagnosis": "arrhythmia",
            "medication": "metoprolol",
        },
    }
    pep_res = pep_client.post("/access", json=access_req)
    assert pep_res.status_code == 200
    pep_data = pep_res.json()
    assert pep_data["decision"] == "PERMIT"
    assert pep_data["policy_id"] == policy_id
    permit_request_id = pep_data["request_id"]
    minimized_data = pep_data["data"]
    assert minimized_data is not None
    # Verify pseudonymization replaced patient_id
    assert minimized_data["patient_id"] != "P999"
    # Verify DOB generalized to decade
    assert minimized_data["date_of_birth"] == "1980-1989"

    # 7. Deny Case: Nurse requesting without authorization
    deny_req = {
        "subject_id": "nurse-nancy",
        "role": "nurse",
        "department": "cardiology",
        "clearance_level": 1,
        "patient_id": "P999",
        "resource_type": "EHR",
        "action": "read",
    }
    pep_deny_res = pep_client.post("/access", json=deny_req)
    assert pep_deny_res.status_code == 403

    # 8. Offline Queue & LogChain Drain
    pending_count = queue_mod.queue_size()
    assert pending_count >= 2  # doctor PERMIT + nurse DENY
    drained = queue_mod.drain_to_logchain(fabric)
    assert drained == pending_count
    assert queue_mod.queue_size() == 0

    # 9. Audit Replay Verification (P0.5)
    replay_res = pms_client.get(f"/audit/replay?request_id={permit_request_id}")
    assert replay_res.status_code == 200
    replay_data = replay_res.json()
    assert replay_data["matched"] is True
    assert replay_data["original_decision"] == "PERMIT"
    assert replay_data["replayed_decision"] == "PERMIT"
