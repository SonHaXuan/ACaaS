"""
Stage 3 of the Data Minimizer pipeline: Role-based field redaction.
Unauthorized fields are replaced with [MASKED] so downstream tooling
sees a fixed schema (Section 4.3).

Visible field sets by role (paper Section 4.3):
  physician  → all clinical fields (diagnosis, medication, lab results, vitals)
  nurse      → vitals + active_medication only
  researcher → de-identified fields only (no diagnosis, no medication details)
  admin      → demographics only
  default    → no sensitive fields
"""
from __future__ import annotations

MASKED = "[MASKED]"

ROLE_VISIBLE: dict[str, set[str]] = {
    "doctor": {
        "patient_id", "diagnosis", "medication", "lab_results",
        "vitals", "allergies", "chief_complaint", "treatment_plan",
        "date_of_birth", "gender", "postal_code", "ethnicity",
    },
    "physician": {  # alias
        "patient_id", "diagnosis", "medication", "lab_results",
        "vitals", "allergies", "chief_complaint", "treatment_plan",
        "date_of_birth", "gender", "postal_code", "ethnicity",
    },
    "nurse": {
        "patient_id", "vitals", "active_medication", "allergies",
        "date_of_birth", "gender",
    },
    "researcher": {
        "patient_id",       # already pseudonymized
        "date_of_birth",    # already generalized
        "postal_code",      # already generalized
        "ethnicity",        # already generalized
        "gender",
        "diagnosis",        # category only, not free-text
    },
    "admin": {
        "patient_id", "date_of_birth", "gender", "postal_code",
        "ethnicity", "insurance_id",
    },
}

SENSITIVE_FIELDS = {
    "diagnosis", "medication", "active_medication", "lab_results",
    "allergies", "chief_complaint", "treatment_plan", "insurance_id",
}


def redact(record: dict, role: str) -> dict:
    """Redact fields not in the role's visible set."""
    visible = ROLE_VISIBLE.get(role, set())
    result = {}
    for key, value in record.items():
        if key in SENSITIVE_FIELDS and key not in visible:
            result[key] = MASKED
        else:
            result[key] = value
    return result
