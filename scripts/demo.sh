#!/usr/bin/env bash
# ACaaS End-to-End Demo Script
# Demonstrates the full happy path: create policy → sync → access request → audit
set -euo pipefail

BASE_PMS="http://localhost:8001"
BASE_PDP="http://localhost:8003"
BASE_PEP="http://localhost:8005"
BASE_AUDIT="http://localhost:8001"
BASE_SYNC="http://localhost:8006"

echo "=== ACaaS Demo ==="
echo ""

echo "0. Resetting demo policy if it already exists..."
curl -s -X DELETE "$BASE_PMS/policies/demo-p1" >/dev/null || true
docker compose exec -T redis redis-cli DEL acaas:logchain >/dev/null 2>&1 || true
echo ""

# 1. Create an ABAC policy (doctor can read EHR in cardiology)
echo "1. Creating policy: doctor/cardiology can READ EHR..."
curl -s -X POST "$BASE_PMS/policies/" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "demo-p1",
    "rule": {
      "subject": {"role": "doctor", "department": "cardiology", "clearance_level": 2},
      "resource": {"data_type": "EHR", "sensitivity": 3},
      "action": "read",
      "condition": {"time_range": null, "location": null, "extra": {}},
      "effect": "PERMIT"
    },
    "criticality": 4.0
  }' | python3 -m json.tool
echo ""

echo "1b. Waiting for edge sync to apply the new policy..."
for _ in $(seq 1 20); do
  LAST_SYNC="$(curl -fsS "$BASE_PDP/health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("last_sync_version", 0))' 2>/dev/null || echo 0)"
  if [ "${LAST_SYNC}" -ge 1 ]; then
    echo "Edge sync ready at version ${LAST_SYNC}"
    break
  fi
  sleep 1
done
echo ""

# 2. List policies
echo "2. Listing all policies..."
curl -s "$BASE_PMS/policies/" | python3 -m json.tool
echo ""

# 3. Check sync server status
echo "3. Checking sync server (PolicyChain events)..."
curl -s "$BASE_SYNC/status" | python3 -m json.tool
echo ""

# 4. Direct PDP evaluation (edge)
echo "4. Edge PDP evaluation: doctor reads EHR (expect PERMIT)..."
curl -s -X POST "$BASE_PDP/evaluate" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "dr-smith",
    "role": "doctor",
    "department": "cardiology",
    "clearance_level": 2,
    "patient_id": "P123",
    "resource_type": "EHR",
    "action": "read",
    "location": "hospital-1"
  }' | python3 -m json.tool
echo ""

# 5. PEP access with data minimization
echo "5. PEP access request with EHR record (full pipeline)..."
curl -s -X POST "$BASE_PEP/access" \
  -H "Content-Type: application/json" \
  -d '{
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
  }' | python3 -m json.tool
echo ""

# 6. Deny case: nurse trying to read with wrong clearance
echo "6. PEP access: nurse requesting EHR (expect DENY for wrong role)..."
curl -s -X POST "$BASE_PEP/access" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "nurse-mai",
    "role": "nurse",
    "clearance_level": 1,
    "patient_id": "P456",
    "resource_type": "EHR",
    "action": "write",
    "location": "clinic-2"
  }' | python3 -m json.tool || true
echo ""

echo "6b. Waiting for queued audit logs to drain..."
for _ in $(seq 1 10); do
  TOTAL_EVENTS="$(curl -fsS "$BASE_AUDIT/audit/compliance/hipaa" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("total_access_events", 0))' 2>/dev/null || echo 0)"
  if [ "${TOTAL_EVENTS}" -ge 2 ]; then
    echo "Audit log ready with ${TOTAL_EVENTS} events"
    break
  fi
  sleep 1
done
echo ""

# 7. HIPAA audit report
echo "7. HIPAA compliance report..."
curl -s "$BASE_AUDIT/audit/compliance/hipaa" | python3 -m json.tool
echo ""

# 8. Direct Cloud PDP evaluation
echo "8. Cloud PDP direct evaluation (port 8002)..."
curl -s -X POST "http://localhost:8002/evaluate" \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "dr-smith",
    "role": "doctor",
    "department": "cardiology",
    "clearance_level": 2,
    "patient_id": "P123",
    "resource_type": "EHR",
    "action": "read",
    "location": "hospital-1"
  }' | python3 -m json.tool
echo ""

# 9. Audit Replay check
echo "9. Audit Replay check on LogChain..."
LAST_REQ_ID="$(curl -fsS "$BASE_AUDIT/audit/logs" | python3 -c 'import json,sys; events=json.load(sys.stdin); print(events[-1]["request_id"] if events else "")' 2>/dev/null || echo "")"
if [ -n "$LAST_REQ_ID" ]; then
  echo "Replaying audit event for request_id: $LAST_REQ_ID"
  curl -s "$BASE_AUDIT/audit/replay?request_id=$LAST_REQ_ID" | python3 -m json.tool
fi
echo ""

echo "=== Demo complete ==="
