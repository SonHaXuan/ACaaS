"""
ACaaS Policy Sync Service — cloud-side server.
Streams policy update events from SyncChain to subscribed edge nodes.
Implements Phases A (cloud commit), B (online propagation), C (offline delta)
from Section 4.2.
"""
from __future__ import annotations
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from blockchain.mock import fabric

app = FastAPI(title="ACaaS Policy Sync Server", version="1.0.0")

# Registry: edge_node_id → {"last_global_seq": int, "ack_ts": float}
_edge_registry: dict[str, dict[str, float]] = {}
_registry_lock = threading.Lock()
TIME_SCALE = float(os.environ.get("ACAAS_TIME_SCALE", "1.0"))


class RegisterRequest(BaseModel):
    edge_node_id: str
    last_known_global_seq: int = 0
    last_known_version: int = 0


@app.post("/register")
def register_edge(req: RegisterRequest):
    """Edge registers itself with its last known global sequence number."""
    initial_seq = max(req.last_known_global_seq, req.last_known_version)
    with _registry_lock:
        _edge_registry[req.edge_node_id] = {
            "last_global_seq": initial_seq,
            "ack_ts": time.time(),
        }
    return {"status": "registered", "edge_node_id": req.edge_node_id, "last_global_seq": initial_seq}


@app.get("/stream/{edge_node_id}")
def stream_updates(
    edge_node_id: str,
    last_global_seq: int = Query(default=0, alias="last_version"),
):
    """
    Server-Sent Events stream — Phase B online propagation.
    Edge keeps this connection open; server pushes events as they arrive.
    """
    def event_generator():
        last_seq = last_global_seq
        while True:
            events = fabric.get_delta(last_seq)
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"
                last_seq = max(last_seq, ev.get("global_seq", 0))
            time.sleep(0.05 * TIME_SCALE)  # low-latency push loop

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/delta/{edge_node_id}")
def get_delta(
    edge_node_id: str,
    from_global_seq: int = Query(default=0, alias="from_version"),
    to_global_seq: int = Query(default=0, alias="to_version"),
):
    """
    Phase C offline-to-online delta sync.
    Returns missed updates [from_global_seq+1 .. to_global_seq].
    """
    events = fabric.get_delta(from_global_seq, to_global_seq)
    return {
        "edge_node_id": edge_node_id,
        "from_global_seq": from_global_seq,
        "to_global_seq": to_global_seq,
        "events": events,
        "count": len(events),
    }


@app.post("/ack/{edge_node_id}")
def ack_update(
    edge_node_id: str,
    policy_id: str = Query(default=""),
    version: int = Query(default=0),
    global_seq: int = Query(default=0),
):
    acked_seq = max(global_seq, version)
    with _registry_lock:
        entry = _edge_registry.get(edge_node_id, {"last_global_seq": 0, "ack_ts": 0.0})
        entry["last_global_seq"] = max(int(entry.get("last_global_seq", 0)), acked_seq)
        entry["ack_ts"] = time.time()
        _edge_registry[edge_node_id] = entry
    return {"ok": True, "edge_node_id": edge_node_id, "last_global_seq": entry["last_global_seq"]}


@app.get("/status")
def sync_status():
    with _registry_lock:
        registry = {k: dict(v) for k, v in _edge_registry.items()}
    current_global_seq = fabric.get_current_global_seq()
    return {
        "current_global_seq": current_global_seq,
        "current_version": current_global_seq,
        "edge_nodes": [
            {
                "edge_node_id": k,
                "last_global_seq": int(v.get("last_global_seq", 0)),
                "last_version": int(v.get("last_global_seq", 0)),
                "lag": max(0, current_global_seq - int(v.get("last_global_seq", 0))),
                "last_ack_ts": v.get("ack_ts", 0.0),
            }
            for k, v in registry.items()
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "policy-sync-server"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SYNC_SERVER_PORT", 8006))
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "warning")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)

