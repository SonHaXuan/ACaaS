from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from acaas_shared.ledger import FileLedger
from acaas_shared.models import Conditions, PolicyRecord, PolicyRule, ResourceAttributes, SubjectAttributes, utc_now
from acaas_shared.storage import JsonPolicyStore

POLICY_STORE = JsonPolicyStore(str(ROOT / "data/cloud/policies.json"))
LEDGER = FileLedger(str(ROOT / "data/ledger/ledger.json"), str(ROOT / "data/ledger/access_logs.jsonl"))


def main() -> None:
    now = utc_now()
    policies = [
        PolicyRecord(
            policy_id="doctor-read-cardiology",
            version=1,
            hash="",
            created_at=now,
            updated_at=now,
            rule=PolicyRule(
                policy_id="doctor-read-cardiology",
                description="Cardiology doctors can read medium sensitivity EHR in clinic during daytime",
                subject=SubjectAttributes(role="doctor", department="cardiology", clearance_level=2),
                resource=ResourceAttributes(resource_type="EHR", sensitivity="medium"),
                actions=["read"],
                conditions=Conditions(locations=["clinic-a", "clinic-b"], time_range=[6, 20]),
                effect="allow",
                priority=50,
            ),
        ),
        PolicyRecord(
            policy_id="intern-deny-high-sensitive",
            version=1,
            hash="",
            created_at=now,
            updated_at=now,
            rule=PolicyRule(
                policy_id="intern-deny-high-sensitive",
                description="Interns cannot access high sensitivity records",
                subject=SubjectAttributes(role="intern", department="cardiology", clearance_level=1),
                resource=ResourceAttributes(resource_type="EHR", sensitivity="high"),
                actions=["read", "write"],
                conditions=Conditions(),
                effect="deny",
                priority=10,
            ),
        ),
    ]

    from acaas_shared.ledger import canonical_policy_hash

    for policy in policies:
        policy.hash = canonical_policy_hash(policy)
        LEDGER.commit_policy(policy)

    POLICY_STORE.save_all(policies)

    ehr = {
        "P123": {
            "patient_id": "P123",
            "name": "Alice Nguyen",
            "age": 47,
            "address": "12 Example Street",
            "phone": "0900000000",
            "email": "alice@example.org",
            "diagnosis": "atrial fibrillation",
            "medications": ["warfarin"],
            "notes": "High-risk follow-up case",
        }
    }
    edge_file = ROOT / "data/edge/ehr_records.json"
    edge_file.parent.mkdir(parents=True, exist_ok=True)
    edge_file.write_text(json.dumps(ehr, indent=2), encoding="utf-8")
    print("Bootstrapped ACaaS sample data.")


if __name__ == "__main__":
    main()
