"""
ACaaS PEP Cloud Escalation Module.
When a policy lookup results in a local cache miss at the Edge Lightweight PDP,
the PEP escalates the evaluation to the Cloud PDP across the WAN.

Privacy guarantee (E6 / Section 4.3):
Direct identifiers ('subject_id', 'patient_id') are pseudonymized using HMAC-SHA256
BEFORE transmitting across the WAN boundary.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../data-minimizer"))
try:
    from pseudonymizer import pseudonymize_id
except ImportError:
    import hmac, hashlib
    STUDY_KEY = os.environ.get("STUDY_KEY", "dev-study-secret-key").encode()
    def pseudonymize_id(identifier: str) -> str:
        return hmac.new(STUDY_KEY, identifier.encode(), hashlib.sha256).hexdigest()[:32]

CLOUD_PDP_URL = os.environ.get("CLOUD_PDP_URL", "http://localhost:8002")


def escalate_to_cloud(pdp_payload: dict, cloud_pdp_url: Optional[str] = None, timeout: int = 5) -> dict | None:
    """
    Pseudonymize direct identifiers and forward request to Cloud PDP.
    Returns Cloud PDP evaluation result or None if unreachable.
    """
    url = (cloud_pdp_url or CLOUD_PDP_URL).rstrip("/")
    escalated_payload = dict(pdp_payload)
    if "subject_id" in escalated_payload and escalated_payload["subject_id"]:
        escalated_payload["subject_id"] = pseudonymize_id(str(escalated_payload["subject_id"]))
    if "patient_id" in escalated_payload and escalated_payload["patient_id"]:
        escalated_payload["patient_id"] = pseudonymize_id(str(escalated_payload["patient_id"]))

    try:
        data = json.dumps(escalated_payload).encode("utf-8")
        req = urllib.request.Request(
            f"{url}/evaluate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            res["evaluated_by"] = "cloud-pdp-escalation"
            return res
    except Exception:
        return None
