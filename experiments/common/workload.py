"""
Synthetic Workload Generation for ACaaS experiments (P1.1).
Generates deterministic subjects, EHR records, ABAC policies, and access requests
with fixed seeds for perfect reproducibility.
"""
from __future__ import annotations

import random
from typing import Any

ROLES = ["doctor", "nurse", "researcher", "admin"]
DEPARTMENTS = ["cardiology", "oncology", "neurology", "pediatrics", "emergency"]
ACTIONS = ["read", "write", "update"]
RESOURCE_TYPES = ["EHR", "lab_result", "prescription", "vital_sign"]
DIAGNOSES = [
    "hypertension", "type_2_diabetes", "cardiac_arrhythmia",
    "asthma", "pneumonia", "coronary_artery_disease", "chronic_kidney_disease"
]
MEDICATIONS = [
    "amlodipine 5mg", "metformin 500mg", "atorvastatin 20mg",
    "lisinopril 10mg", "albuterol inhaler", "aspirin 81mg", "omeprazole 20mg"
]
ETHNICITIES = ["Vietnamese", "Han", "Malay", "Filipino", "European", "African"]


def generate_subjects(n: int = 100, seed: int = 42) -> list[dict[str, Any]]:
    """Generate deterministic subjects with role, department, and clearance level."""
    rng = random.Random(seed)
    subjects: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        role = rng.choice(ROLES)
        dept = rng.choice(DEPARTMENTS)
        clearance = rng.randint(1, 3)
        subjects.append({
            "subject_id": f"sub-{role}-{i:04d}",
            "role": role,
            "department": dept,
            "clearance_level": clearance,
        })
    return subjects


def generate_ehr_records(
    n: int = 100,
    seed: int = 42,
    size_class: str = "medium",
) -> list[dict[str, Any]]:
    """
    Generate realistic EHR records.
    Size classes:
      - 'small': core demographics and single condition (~300 bytes)
      - 'medium': adds vitals, multiple labs, medication list (~1 KB)
      - 'large': adds extensive clinical history and consultation notes (~5 KB)
    """
    rng = random.Random(seed)
    records: list[dict[str, Any]] = []

    for i in range(1, n + 1):
        year = rng.randint(1945, 2015)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        dob = f"{year:04d}-{month:02d}-{day:02d}"
        postal = f"{rng.randint(10000, 99999)}"
        gender = rng.choice(["M", "F"])
        ethnicity = rng.choice(ETHNICITIES)
        diag = rng.choice(DIAGNOSES)
        med = rng.choice(MEDICATIONS)

        rec: dict[str, Any] = {
            "patient_id": f"P-{i:06d}",
            "name": f"Patient_{i:06d}",
            "date_of_birth": dob,
            "postal_code": postal,
            "ethnicity": ethnicity,
            "gender": gender,
            "diagnosis": diag,
            "medication": med,
            "lab_results": {
                "hba1c": round(rng.uniform(4.5, 9.5), 1),
                "cholesterol": rng.randint(140, 260),
                "fasting_glucose": rng.randint(70, 160),
            },
            "vitals": {
                "bp": f"{rng.randint(105, 155)}/{rng.randint(65, 95)}",
                "heart_rate": rng.randint(58, 98),
                "temp": round(rng.uniform(36.2, 38.5), 1),
            },
        }

        if size_class == "medium":
            rec["notes"] = f"Routine evaluation for {diag}. Patient advised on {med} compliance. Follow-up in 30 days."
            rec["allergies"] = ["penicillin"] if rng.random() < 0.2 else []
            rec["encounter_id"] = f"ENC-{rng.randint(10000, 99999)}"
        elif size_class == "large":
            rec["notes"] = (
                f"Comprehensive specialist examination for complex {diag}. Detailed family history reviewed. "
                "Multiple comorbid presentations monitored over 12 months. Differential diagnostics completed. "
                * 8
            )
            rec["allergies"] = ["penicillin", "sulfa", "latex"]
            rec["encounter_history"] = [
                {"date": f"202{k}-0{k+1}-15", "type": "outpatient", "summary": f"Review {diag}"}
                for k in range(5)
            ]
            rec["genomic_markers"] = {"cyp2c19": "*1/*2", "hla_b_5701": "negative"}

        records.append(rec)
    return records


def generate_policies(
    n: int = 20,
    seed: int = 42,
    tier: str = "EDGE",
) -> list[dict[str, Any]]:
    """Generate deterministic ABAC policies for Policy Manager."""
    rng = random.Random(seed)
    policies: list[dict[str, Any]] = []

    for i in range(1, n + 1):
        role = rng.choice(ROLES)
        dept = rng.choice(DEPARTMENTS)
        clearance = rng.choice([1, 2])
        res_type = rng.choice(RESOURCE_TYPES)
        action = rng.choice(ACTIONS)
        effect = "PERMIT" if rng.random() < 0.9 else "DENY"

        policies.append({
            "policy_id": f"policy-synth-{i:03d}",
            "rule": {
                "subject": {
                    "role": role,
                    "department": dept,
                    "clearance_level": clearance,
                },
                "resource": {
                    "data_type": res_type,
                    "sensitivity": clearance + 1,
                },
                "action": action,
                "condition": {
                    "time_range": None,
                    "location": None,
                    "extra": {},
                },
                "effect": effect,
            },
            "criticality": round(rng.uniform(1.0, 5.0), 1),
            "deployment_tier": tier,
        })
    return policies


def generate_access_requests(
    n: int = 1000,
    seed: int = 42,
    permit_ratio: float = 0.8,
    include_records: bool = True,
    known_policies: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate synthetic access requests with controlled permit/deny target ratio.
    If known_policies is given, derives matching attributes to ensure permit/deny.
    """
    rng = random.Random(seed)
    policies = known_policies or generate_policies(n=10, seed=seed)
    permit_policies = [p for p in policies if p["rule"]["effect"] == "PERMIT"]
    records = generate_ehr_records(n=min(n, 200), seed=seed) if include_records else []

    requests: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        should_permit = (rng.random() < permit_ratio) and bool(permit_policies)
        patient_rec = records[i % len(records)] if records else None
        patient_id = patient_rec["patient_id"] if patient_rec else f"P-{i:05d}"

        if should_permit:
            target_p = rng.choice(permit_policies)
            sub_rule = target_p["rule"]["subject"]
            res_rule = target_p["rule"]["resource"]
            req = {
                "subject_id": f"sub-{sub_rule['role']}-{i:04d}",
                "role": sub_rule["role"],
                "department": sub_rule["department"],
                "clearance_level": sub_rule["clearance_level"],
                "patient_id": patient_id,
                "resource_type": res_rule["data_type"],
                "action": target_p["rule"]["action"],
                "location": f"clinic-{rng.randint(1, 5)}",
            }
        else:
            # Generate random attributes unlikely to match or explicit wrong role
            role = rng.choice(["intern", "visitor", "volunteer", "unregistered"])
            req = {
                "subject_id": f"sub-{role}-{i:04d}",
                "role": role,
                "department": rng.choice(DEPARTMENTS),
                "clearance_level": 1,
                "patient_id": patient_id,
                "resource_type": "EHR",
                "action": "read",
                "location": f"clinic-{rng.randint(1, 5)}",
            }

        if include_records and patient_rec:
            req["ehr_record"] = patient_rec

        requests.append(req)

    return requests
