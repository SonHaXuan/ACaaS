"""
ACaaS Policy Sync Service — cloud-side server.
Streams policy update events from SyncChain to subscribed edge nodes.
Implements Phases A (cloud commit), B (online propagation), C (offline delta)
from Section 4.2.

Uses a simple HTTP long-poll streaming approach in this implementation
(replace with actual gRPC from shared/proto/sync.proto in production).
"""
from __future__ import annotations
import sys, os, json, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from blockchain.mock import fabric

app = FastAPI(title="ACaaS Policy Sync Server", version="1.0.0")

# Registry: edge_node_id → last_acked_version
_edge_registry: dict[str, int] = {}
_registry_lock = threading.Lock()


class RegisterRequest(BaseModel):
    edge_node_id: str
    last_known_version: int = 0


@app.post("/register")
def register_edge(req: RegisterRequest):
    """Edge registers itself with its last known version."""
    with _registry_lock:
        _edge_registry[req.edge_node_id] = req.last_known_version
    return {"status": "registered", "edge_node_id": req.edge_node_id}


@app.get("/stream/{edge_node_id}")
def stream_updates(edge_node_id: str, last_version: int = Query(default=0)):
    """
    Server-Sent Events stream — Phase B online propagation.
    Edge keeps this connection open; server pushes events as they arrive.
    """
    def event_generator():
        last_v = last_version
        while True:
            events = fabric.get_delta(last_v)
            for ev in events:
                yield f"data: {json.dumps(ev)}\n\n"
                last_v = max(last_v, ev.get("new_version", 0))
            time.sleep(0.5)  # poll interval

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/delta/{edge_node_id}")
def get_delta(edge_node_id: str,
              from_version: int = Query(default=0),
              to_version: int = Query(default=0)):
    """
    Phase C offline-to-online delta sync.
    Returns missed updates [from_version+1 .. to_version].
    """
    events = fabric.get_delta(from_version, to_version)
    return {
        "edge_node_id": edge_node_id,
        "from_version": from_version,
        "to_version": to_version,
        "events": events,
        "count": len(events),
    }


@app.post("/ack/{edge_node_id}")
def ack_update(edge_node_id: str, policy_id: str, version: int):
    with _registry_lock:
        current = _edge_registry.get(edge_node_id, 0)
        _edge_registry[edge_node_id] = max(current, version)
    return {"ok": True}


@app.get("/status")
def sync_status():
    with _registry_lock:
        registry = dict(_edge_registry)
    current_version = max(fabric._versions.values(), default=0)
    return {
        "current_version": current_version,
        "edge_nodes": [
            {
                "edge_node_id": k,
                "last_version": v,
                "lag": current_version - v,
            }
            for k, v in registry.items()
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "policy-sync-server"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sync_server:app", host="0.0.0.0",
                port=int(os.environ.get("SYNC_SERVER_PORT", 8006)), reload=True)
