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

def mondrian_partition(partition: list[dict], k: int, qi_fields: list[str]) -> list[list[dict]]:
    """Recursively partition data using Mondrian multidimensional generalization."""
    if len(partition) < 2 * k:
        return [partition]
        
    for dim in qi_fields:
        values = [str(r.get(dim, "")) for r in partition]
        unique_vals = list(set(values))
        if len(unique_vals) > 1:
            values.sort()
            median_val = values[len(values)//2]
            
            lhs = [r for r in partition if str(r.get(dim, "")) <= median_val]
            rhs = [r for r in partition if str(r.get(dim, "")) > median_val]
            
            if len(lhs) >= k and len(rhs) >= k:
                return mondrian_partition(lhs, k, qi_fields) + mondrian_partition(rhs, k, qi_fields)
                
    return [partition]

def enforce_k_anonymity(
    records: list[dict],
    qi_fields: list[str] | None = None,
    k: int = DEFAULT_K,
) -> tuple[list[dict], int]:
    """
    Enforce k-anonymity on a cohort of EHR records using Multi-dimensional generalization (Mondrian):
    1. Base 1D Generalizes quasi-identifiers.
    2. Groups into equivalence classes using Mondrian.
    3. For each partition, generalizations are applied so they are truly identical QI vectors.
    4. Suppresses partitions of size < k.

    Returns:
        (sanitized_records, suppressed_count)
    """
    fields = qi_fields or ["date_of_birth", "postal_code", "ethnicity", "gender"]
    generalized_base = [generalize_record(r) for r in records]

    partitions = mondrian_partition(generalized_base, k, fields)
    
    sanitized: list[dict] = []
    suppressed = 0
    
    for part in partitions:
        if len(part) >= k:
            # Apply group generalization to ensure identical QIs
            group_gen = {}
            for dim in fields:
                unique_vals = sorted(list(set(str(r.get(dim, "")) for r in part)))
                if len(unique_vals) > 1:
                    group_gen[dim] = f"{unique_vals[0]}~{unique_vals[-1]}"
                else:
                    group_gen[dim] = unique_vals[0] if unique_vals else ""
            
            for r in part:
                for dim in fields:
                    r[dim] = group_gen[dim]
                sanitized.append(r)
        else:
            suppressed += len(part)

    return sanitized, suppressed
