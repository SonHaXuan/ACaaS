#!/usr/bin/env python3
"""
ACaaS End-to-End Demo Script (Python Version).
Demonstrates the full lifecycle:
1. Create ABAC policy at Cloud PMS
2. Edge sync client pulls update into Local Policy Store
3. Direct Edge PDP evaluation
4. PEP access request + Data Minimization pipeline
5. Role-based Deny enforcement
6. Draining offline audit logs to LogChain
7. HIPAA compliance report & audit replay verification
"""
from __future__ import annotations

import json
import sys
import time
import httpx

BASE_PMS   = "http://localhost:8001"
BASE_CLOUD_PDP = "http://localhost:8002"
BASE_PDP   = "http://localhost:8003"
BASE_PEP   = "http://localhost:8005"
BASE_AUDIT = "http://localhost:8001"
BASE_SYNC  = "http://localhost:8006"


def main() -> None:
    print("=== ACaaS Demo (Python) ===")
    print()

    with httpx.Client(timeout=10.0) as client:
        # 0. Reset demo policy if exists
        try:
            client.delete(f"{BASE_PMS}/policies/demo-p1")
        except Exception:
            pass

        # 1. Create an ABAC policy
        print("1. Creating policy: doctor/cardiology can READ EHR...")
        policy_payload = {
            "policy_id": "demo-p1",
            "rule": {
                "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
                "resource": {"data_type": "EHR", "sensitivity": 3},
                "action": "read",
                "condition": {"time_range": None, "location": None, "extra": {}},
                "effect": "PERMIT"
            },
            "criticality": 4.0
        }
        resp = client.post(f"{BASE_PMS}/policies/", json=policy_payload)
        resp.raise_for_status()
        print(json.dumps(resp.json(), indent=2))
        print()

        # 1b. Wait for edge sync
        print("1b. Waiting for edge sync to apply the new policy...")
        synced = False
        for _ in range(25):
            try:
                h = client.get(f"{BASE_PDP}/health").json()
                if h.get("last_sync_version", 0) >= 1 or h.get("cached_policies", 0) >= 1:
                    print(f"Edge sync ready: {h}")
                    synced = True
                    break
            except Exception:
                pass
            time.sleep(1)
        if not synced:
            print("Warning: Edge sync did not confirm in time, continuing anyway...")
        print()

        # 2. List policies
        print("2. Listing all policies on PMS...")
        pols = client.get(f"{BASE_PMS}/policies/").json()
        print(json.dumps(pols, indent=2))
        print()

        # 3. Check sync server status
        print("3. Checking sync server status...")
        try:
            status = client.get(f"{BASE_SYNC}/status").json()
            print(json.dumps(status, indent=2))
        except Exception as e:
            print(f"Sync server status: {e}")
        print()

        # 4. Direct PDP evaluation
        print("4. Edge PDP evaluation: doctor reads EHR (expect PERMIT)...")
        pdp_req = {
            "subject_id": "dr-smith",
            "role": "doctor",
            "department": "cardiology",
            "clearance_level": 2,
            "patient_id": "P123",
            "resource_type": "EHR",
            "action": "read",
            "location": "hospital-1"
        }
        pdp_res = client.post(f"{BASE_PDP}/evaluate", json=pdp_req).json()
        print(json.dumps(pdp_res, indent=2))
        print()

        # 5. PEP access with data minimization
        print("5. PEP access request with EHR record (full pipeline)...")
        pep_req = {
            "subject_id": "dr-smith",
            "role": "doctor",
            "department": "cardiology",
            "clearance_level": 2,
            "patient_id": "P123",
            "resource_type": "EHR",
            "action": "read",
            "location": "hospital-1",
            "ehr_record": {
                "patient_id": "P123",
                "name": "Nguyen Van A",
                "date_of_birth": "1985-07-21",
                "postal_code": "70000",
                "ethnicity": "Vietnamese",
                "gender": "M",
                "diagnosis": "hypertension",
                "medication": "amlodipine 5mg",
                "lab_results": {"hba1c": 5.6},
                "vitals": {"bp": "120/80"}
            }
        }
        pep_res = client.post(f"{BASE_PEP}/access", json=pep_req)
        pep_json = pep_res.json()
        print(json.dumps(pep_json, indent=2))
        permit_req_id = pep_json.get("request_id")
        print()

        # 6. Deny case
        print("6. PEP access: nurse requesting EHR (expect DENY for wrong role)...")
        deny_req = {
            "subject_id": "nurse-mai",
            "role": "nurse",
            "clearance_level": 1,
            "patient_id": "P456",
            "resource_type": "EHR",
            "action": "write",
            "location": "clinic-2"
        }
        deny_res = client.post(f"{BASE_PEP}/access", json=deny_req)
        print(f"Status Code: {deny_res.status_code}")
        print(json.dumps(deny_res.json(), indent=2))
        print()

        # 6b. Wait for audit logs
        print("6b. Waiting for queued audit logs to drain...")
        for _ in range(15):
            try:
                logs = client.get(f"{BASE_AUDIT}/audit/logs").json()
                req_ids = [l.get("request_id") for l in logs]
                if permit_req_id in req_ids:
                    print(f"Audit log ready: found request {permit_req_id} (total {len(logs)} events)")
                    break
            except Exception:
                pass
            time.sleep(1)
        print()

        # 7. HIPAA report
        print("7. HIPAA compliance report...")
        report = client.get(f"{BASE_AUDIT}/audit/compliance/hipaa").json()
        print(json.dumps(report, indent=2))
        print()

        # 8. Cloud PDP direct evaluation
        print("8. Cloud PDP direct evaluation (port 8002)...")
        cloud_pdp_res = client.post(f"{BASE_CLOUD_PDP}/evaluate", json=pdp_req).json()
        print(json.dumps(cloud_pdp_res, indent=2))
        print()

        # 9. Audit Replay check (P0.5)
        if permit_req_id:
            print(f"9. Audit Replay for request_id '{permit_req_id}'...")
            try:
                replay_res = client.get(f"{BASE_AUDIT}/audit/replay", params={"request_id": permit_req_id}).json()
                print(json.dumps(replay_res, indent=2))
            except Exception as e:
                print(f"Replay response: {e}")
            print()

    print("=== Demo complete ===")


if __name__ == "__main__":
    main()
