from __future__ import annotations

import hashlib
import hmac
import os
from collections import Counter
from copy import deepcopy
from typing import Any

# Per-study HMAC key — matches Claude-ICSOC pseudonymizer (Section 3.3)
_STUDY_KEY = os.environ.get("STUDY_KEY", "dev-study-secret-key").encode()

_ETHNICITY_MAP = {
    "Vietnamese": "Southeast Asian", "Chinese": "East Asian",
    "Japanese": "East Asian", "Korean": "East Asian",
    "Thai": "Southeast Asian", "Filipino": "Southeast Asian",
    "Caucasian": "European", "African American": "African",
    "Hispanic": "Latin American", "Indian": "South Asian",
}


def pseudonymize(value: str) -> str:
    """SHA-256 digest (legacy, no key)."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"psn-{digest[:12]}"


def pseudonymize_hmac(value: str, key: bytes = _STUDY_KEY) -> str:
    """HMAC-SHA256(k_study, id) per Section 3.3 — preserves referential integrity."""
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def generalize_age(age: int) -> str:
    low = (age // 10) * 10
    return f"{low}-{low + 9}"


def generalize_dob(dob: str) -> str:
    """'1985-07-21' → '1980-1989' (Section 4.3 Stage 2)."""
    try:
        decade = (int(dob[:4]) // 10) * 10
        return f"{decade}-{decade + 9}"
    except Exception:
        return dob


def generalize_postal(postal: str) -> str:
    return postal[:3] + "**" if len(postal) >= 3 else postal


def generalize_ethnicity(eth: str) -> str:
    return _ETHNICITY_MAP.get(eth, "Other")


def check_k_anonymity(records: list[dict[str, Any]],
                       qi_fields: list[str], k: int = 10) -> tuple[bool, int]:
    """Verify k-anonymity on a dataset (Section 3.3, Eq. 4)."""
    keys = [tuple(str(r.get(f, "")) for f in qi_fields) for r in records]
    counts = Counter(keys)
    min_size = min(counts.values()) if counts else 0
    return min_size >= k, min_size


def enforce_k_anonymity(
    records: list[dict[str, Any]],
    qi_fields: list[str] | None = None,
    k: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Enforces k-anonymity by grouping and suppressing outliers."""
    from collections import defaultdict
    fields = qi_fields or ["date_of_birth", "postal_code", "ethnicity", "gender"]
    groups = defaultdict(list)
    for rec in records:
        qi_tuple = tuple(str(rec.get(f, "")) for f in fields)
        groups[qi_tuple].append(rec)

    sanitized: list[dict[str, Any]] = []
    suppressed = 0
    for qi_tuple, group in groups.items():
        if len(group) >= k:
            sanitized.extend(group)
        else:
            suppressed += len(group)
    return sanitized, suppressed


def minimize_record(record: dict[str, Any], access_level: int) -> dict[str, Any]:
    """
    Three-stage minimization pipeline (Section 4.3):
      Stage 1 — Pseudonymization
      Stage 2 — QI generalization (k-anonymity)
      Stage 3 — Field redaction by access_level
    """
    data = deepcopy(record)

    # Stage 1: pseudonymize direct identifiers
    for field in ("patient_id", "national_id", "name", "phone", "email", "ssn", "mrn"):
        if field in data and data[field]:
            data[field] = pseudonymize_hmac(str(data[field]))

    # Stage 2: generalize quasi-identifiers
    if "age" in data and isinstance(data["age"], int):
        data["age_group"] = generalize_age(data["age"])
        del data["age"]
    if "date_of_birth" in data:
        data["date_of_birth"] = generalize_dob(str(data["date_of_birth"]))
    if "postal_code" in data:
        data["postal_code"] = generalize_postal(str(data["postal_code"]))
    if "ethnicity" in data:
        data["ethnicity"] = generalize_ethnicity(str(data["ethnicity"]))

    # Stage 3: field redaction by access level
    if access_level < 3:
        for key in ("address", "phone", "email", "notes"):
            data.pop(key, None)
    if access_level < 2:
        for key in ("diagnosis", "medications"):
            data.pop(key, None)

    return data

