"""Unit tests for the three-stage Data Minimizer pipeline."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../edge/data-minimizer"))

from pseudonymizer import pseudonymize_record, pseudonymize_id
from k_anonymity import generalize_record, check_k_anonymity
from field_redactor import redact, MASKED

SAMPLE_RECORD = {
    "patient_id": "P123",
    "name": "John Doe",
    "date_of_birth": "1985-07-21",
    "postal_code": "70000",
    "ethnicity": "Vietnamese",
    "gender": "M",
    "diagnosis": "hypertension",
    "medication": "amlodipine 5mg",
    "lab_results": {"hba1c": 5.6},
    "vitals": {"bp": "120/80"},
}


# ── Stage 1: Pseudonymization ─────────────────────────────────────────────

def test_pseudonymize_replaces_patient_id():
    result = pseudonymize_record(SAMPLE_RECORD)
    assert result["patient_id"] != "P123"
    assert len(result["patient_id"]) == 32  # HMAC hex truncated


def test_pseudonymize_is_deterministic():
    r1 = pseudonymize_id("P123")
    r2 = pseudonymize_id("P123")
    assert r1 == r2


def test_pseudonymize_different_ids_produce_different_tokens():
    assert pseudonymize_id("P123") != pseudonymize_id("P456")


# ── Stage 2: k-anonymity generalization ──────────────────────────────────

def test_dob_generalized_to_decade():
    result = generalize_record({"date_of_birth": "1985-07-21"})
    assert result["date_of_birth"] == "1980-1989"


def test_postal_code_truncated():
    result = generalize_record({"postal_code": "70012"})
    assert result["postal_code"] == "700**"


def test_ethnicity_grouped():
    result = generalize_record({"ethnicity": "Vietnamese"})
    assert result["ethnicity"] == "Southeast Asian"


def test_k_anonymity_check():
    records = [
        {"dob_range": "1980-1989", "postal": "700**", "eth": "Southeast Asian"},
    ] * 10
    ok, min_size = check_k_anonymity(
        records,
        qi_fields=["dob_range", "postal", "eth"],
        k=5,
    )
    assert ok
    assert min_size >= 5


# ── Stage 3: Field redaction ──────────────────────────────────────────────

def test_doctor_sees_diagnosis():
    result = redact(SAMPLE_RECORD, "doctor")
    assert result["diagnosis"] == "hypertension"


def test_nurse_cannot_see_diagnosis():
    result = redact(SAMPLE_RECORD, "nurse")
    assert result["diagnosis"] == MASKED


def test_researcher_cannot_see_medication():
    result = redact(SAMPLE_RECORD, "researcher")
    assert result["medication"] == MASKED


def test_unknown_role_masks_all_sensitive():
    result = redact(SAMPLE_RECORD, "unknown_role")
    assert result["diagnosis"] == MASKED
    assert result["medication"] == MASKED
    assert result["lab_results"] == MASKED
