"""
ACaaS Fog Policy Cache Service.
Caches hot policies with TTL and version-based invalidation.
Reduces cloud round-trips for intermediate nodes (Section 4.1).
"""
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from blockchain.mock import fabric

DEFAULT_TTL = int(os.environ.get("FOG_CACHE_TTL", "3600"))  # 1 hour for fog

app = FastAPI(title="ACaaS Fog Policy Cache", version="1.0.0")

_cache: dict[str, dict] = {}  # policy_id → {policy, version, expires_at}
_cache_lock = threading.RLock()


def _is_valid(entry: dict) -> bool:
    if time.time() > entry["expires_at"]:
        return False
    # Version check against PolicyChain
    chain_v, chain_hash = fabric.get_policy_version(entry["policy_id"])
    return entry["version"] == chain_v


@app.get("/policy/{policy_id}")
def get_cached_policy(policy_id: str):
    with _cache_lock:
        entry = _cache.get(policy_id)
    if entry and _is_valid(entry):
        return {"source": "fog-cache", "policy": entry["policy"],
                "version": entry["version"]}
    # Miss — fetch from cloud PMS
    cloud_url = os.environ.get("PMS_URL", "http://localhost:8001")
    try:
        import urllib.request
        with urllib.request.urlopen(
            f"{cloud_url}/policies/{policy_id}", timeout=3
        ) as resp:
            policy_data = json.loads(resp.read())
        with _cache_lock:
            _cache[policy_id] = {
                "policy_id": policy_id,
                "policy": policy_data,
                "version": policy_data["version"],
                "expires_at": time.time() + DEFAULT_TTL,
            }
        return {"source": "cloud", "policy": policy_data,
                "version": policy_data["version"]}
    except Exception:
        raise HTTPException(503, "Policy not found in cache or cloud")


@app.delete("/policy/{policy_id}")
def invalidate(policy_id: str):
    with _cache_lock:
        _cache.pop(policy_id, None)
    return {"invalidated": policy_id}


@app.get("/stats")
def stats():
    with _cache_lock:
        total = len(_cache)
        valid = sum(1 for e in _cache.values() if _is_valid(e))
    return {"cached_policies": total, "valid": valid,
            "hit_rate_hint": f"{valid}/{total}"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "fog-policy-cache"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0",
                port=int(os.environ.get("FOG_CACHE_PORT", 8007)), reload=True)
