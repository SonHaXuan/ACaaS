"""
Stage 1 of the Data Minimizer pipeline: Pseudonymization.
ψ(id, k) = HMAC-SHA256(k_study, id)  (Section 3.3, Section 4.3)

This preserves referential integrity within a study while preventing
cross-study linkage as long as k_study remains secret.
"""
import hmac, hashlib, os

# Per-study secret — in production distributed via authenticated channel
STUDY_KEY = os.environ.get("STUDY_KEY", "dev-study-secret-key").encode()

DIRECT_IDENTIFIER_FIELDS = {
    "patient_id", "national_id", "phone", "name", "email", "ssn",
    "mrn",   # medical record number
}


def pseudonymize_id(identifier: str, study_key: bytes = STUDY_KEY) -> str:
    """Replace a direct identifier with an HMAC token."""
    return hmac.new(study_key, identifier.encode(), hashlib.sha256).hexdigest()[:32]


def pseudonymize_record(record: dict,
                        study_key: bytes = STUDY_KEY) -> dict:
    """Replace all direct identifier fields in an EHR record."""
    result = dict(record)
    for field in DIRECT_IDENTIFIER_FIELDS:
        if field in result and result[field]:
            result[field] = pseudonymize_id(str(result[field]), study_key)
    return result
