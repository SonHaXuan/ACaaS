from acaas_shared.minimizer import minimize_record


def test_minimizer_redacts_low_access() -> None:
    record = {
        "patient_id": "P123",
        "age": 47,
        "address": "12 Example Street",
        "diagnosis": "atrial fibrillation",
    }
    result = minimize_record(record, access_level=1)
    assert len(result["patient_id"]) == 32
    # assert result["patient_id"].startswith("psn-")
    assert "age" not in result
    assert result["age_group"] == "40-49"
    assert "address" not in result
    assert "diagnosis" not in result

