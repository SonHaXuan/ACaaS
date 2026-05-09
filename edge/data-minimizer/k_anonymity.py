"""
Stage 2 of the Data Minimizer pipeline: k-anonymity generalization.
Generalizes quasi-identifiers so every released record shares its QI
vector with at least k-1 others in the local dataset (Section 3.3, 4.3).

Generalizations applied:
  - date_of_birth → 10-year age range (e.g. "1980-03-15" → "1980-1989")
  - postal_code   → first 3 digits
  - ethnicity     → regional group
  - gender        → kept as-is (binary is already coarse)
"""
from __future__ import annotations
import datetime, re

ETHNICITY_MAP = {
    "Vietnamese": "Southeast Asian",
    "Chinese": "East Asian",
    "Japanese": "East Asian",
    "Korean": "East Asian",
    "Thai": "Southeast Asian",
    "Filipino": "Southeast Asian",
    "Caucasian": "European",
    "African American": "African",
    "Hispanic": "Latin American",
    "Indian": "South Asian",
}

DEFAULT_K = int(10)   # paper evaluates k ∈ {5, 10, 20}


def _generalize_dob(dob: str) -> str:
    """'1985-07-21' → '1980-1989'"""
    try:
        year = int(dob[:4])
        decade = (year // 10) * 10
        return f"{decade}-{decade + 9}"
    except Exception:
        return dob


def _generalize_postal(postal: str) -> str:
    """'70000' → '700**'"""
    return postal[:3] + "**" if len(postal) >= 3 else postal


def _generalize_ethnicity(eth: str) -> str:
    return ETHNICITY_MAP.get(eth, "Other")


def generalize_record(record: dict) -> dict:
    """Apply QI generalization to a single EHR record."""
    result = dict(record)
    if "date_of_birth" in result:
        result["date_of_birth"] = _generalize_dob(str(result["date_of_birth"]))
    if "postal_code" in result:
        result["postal_code"] = _generalize_postal(str(result["postal_code"]))
    if "ethnicity" in result:
        result["ethnicity"] = _generalize_ethnicity(str(result["ethnicity"]))
    return result


def check_k_anonymity(records: list[dict],
                       qi_fields: list[str],
                       k: int = DEFAULT_K) -> tuple[bool, int]:
    """
    Verify k-anonymity on a dataset.
    Returns (is_k_anonymous, min_group_size).
    """
    from collections import Counter
    keys = [tuple(r.get(f, "") for f in qi_fields) for r in records]
    counts = Counter(keys)
    min_size = min(counts.values()) if counts else 0
    return min_size >= k, min_size
