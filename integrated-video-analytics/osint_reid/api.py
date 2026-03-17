from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, Header, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from auth import ensure_admin_access, ensure_admin_websocket
from osint_reid.config import ADMIN_API_TOKEN, SNAPSHOT_DIR
from osint_reid.db import now_utc_iso
from osint_reid.service import get_osint_service

logger = logging.getLogger("osint_reid.api")

router = APIRouter()
_state_ws_clients: set[WebSocket] = set()


def _require_admin_token(
    authorization: str | None = None,
    x_api_key: str | None = None,
    api_key: str | None = None,
) -> None:
    configured_token = os.getenv("ADMIN_API_TOKEN", ADMIN_API_TOKEN).strip()
    if not configured_token:
        return
    ensure_admin_access(authorization=authorization, x_api_key=x_api_key, api_key=api_key)


def _watchlist_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "watchlist"
    path.mkdir(exist_ok=True)
    return path


def _sanitize_watchlist_name(value: str | None) -> str:
    safe_value = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (value or "").strip())
    return safe_value.strip("._-")


def _service_or_http():
    try:
        return get_osint_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OSINT service unavailable: {exc}") from exc


def _snapshot_path(global_id: str, ts: str) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = ts.replace(":", "-")
    return SNAPSHOT_DIR / f"{global_id}_{safe_ts}.jpg"


def _watchlist_snapshot_url(global_id: str, ts: str | None) -> str | None:
    if not ts:
        return None
    return f"/api/stream/snapshot/{global_id}/{ts}.jpg"


def _load_image_from_upload(raw: bytes) -> np.ndarray:
    arr = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode image upload.")
    return image


async def ws_broadcast_incident(payload: dict[str, Any]) -> None:
    if not _state_ws_clients:
        return
    drop: list[WebSocket] = []
    for client in list(_state_ws_clients):
        try:
            await client.send_json(payload)
        except Exception:
            drop.append(client)
    for client in drop:
        _state_ws_clients.discard(client)


@router.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    if not await ensure_admin_websocket(websocket):
        return
    await websocket.accept()
    _state_ws_clients.add(websocket)
    service = get_osint_service()
    try:
        while True:
            incidents = service.pop_incidents()
            for incident in incidents:
                await websocket.send_json(incident)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        _state_ws_clients.discard(websocket)


@router.get("/api/watchlist")
def list_watchlist():
    service = _service_or_http()
    identities = service.db.list_global_identities(watchlist_only=True)
    entries = []
    for item in identities:
        meta = item.get("watchlist_meta") or {}
        display_name = meta.get("display_name") or item["global_id"]
        entries.append(
            {
                "identity": display_name,
                "display_name": display_name,
                "global_id": item["global_id"],
                "filename": meta.get("snapshot_filename", ""),
                "last_seen_ts": item.get("last_seen_ts"),
                "snapshot_path": meta.get("snapshot_path", ""),
                "snapshot_url": _watchlist_snapshot_url(item["global_id"], item.get("last_seen_ts")),
                "watchlist_flag": item.get("watchlist_flag", 0),
            }
        )
    safe_identities = [{k: v for k, v in item.items() if k not in ("face_embedding", "reid_embedding")} for item in identities]
    return {"entries": entries, "global_identities": safe_identities}


@router.post("/api/watchlist")
async def enroll_watchlist(
    name: str = Form(...),
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = None,
):
    _require_admin_token(authorization, x_api_key, api_key)
    display_name = _sanitize_watchlist_name(name)
    if not display_name:
        raise HTTPException(status_code=400, detail="A valid watchlist identity is required.")

    raw = await file.read()
    image = _load_image_from_upload(raw)
    watchlist_path = _watchlist_dir() / f"{display_name}.jpg"
    if watchlist_path.exists():
        raise HTTPException(status_code=409, detail="A watchlist image already exists for that identity.")

    service = _service_or_http()
    face_embs = service.reid_worker.compute_face_embeddings([image])
    if face_embs.size == 0:
        raise HTTPException(status_code=400, detail="No face detected in uploaded image.")

    ts = now_utc_iso()
    global_id = service.db.create_global_identity(
        camera_id="watchlist_enroll",
        seen_ts=ts,
        face_embedding=face_embs[0],
        reid_embedding=None,
        confidence=0.99,
        watchlist_flag=1,
        watchlist_meta={},
    )

    watchlist_path.write_bytes(raw)
    snapshot = _snapshot_path(global_id, ts)
    snapshot.write_bytes(raw)

    service.db.update_global_identity(
        global_id=global_id,
        camera_id="watchlist_enroll",
        seen_ts=ts,
        face_embedding=face_embs[0],
        reid_embedding=None,
        confidence=0.99,
    )

    # Write meta in-place with sqlite update for portability
    watchlist_meta = {
        "display_name": display_name,
        "snapshot_filename": watchlist_path.name,
        "snapshot_path": str(snapshot),
    }
    conn = service.db._connect()
    try:
        conn.execute(
            "UPDATE global_identities SET watchlist_flag=1, watchlist_meta=? WHERE global_id=?",
            (
                json.dumps(watchlist_meta),
                global_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "success",
        "entry": {
            "identity": display_name,
            "display_name": display_name,
            "global_id": global_id,
            "filename": watchlist_path.name,
            "last_seen_ts": ts,
            "snapshot_path": str(snapshot),
            "snapshot_url": _watchlist_snapshot_url(global_id, ts),
        },
    }


@router.get("/api/watchlist/{global_id}")
def get_watchlist_identity(global_id: str):
    service = _service_or_http()
    identity = service.db.get_global_identity(global_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Global identity not found")

    history = service.db.get_tracklets_for_global(global_id, limit=100)
    incidents = service.db.get_recent_incidents_for_global(global_id, limit=50)
    safe_identity = {k: v for k, v in identity.items() if k not in ("face_embedding", "reid_embedding")}
    safe_identity["snapshot_url"] = _watchlist_snapshot_url(global_id, identity.get("last_seen_ts"))
    return {"identity": safe_identity, "match_history": history, "incidents": incidents}


@router.delete("/api/watchlist/{global_id}")
def delete_watchlist_identity(
    global_id: str,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = None,
):
    _require_admin_token(authorization, x_api_key, api_key)
    service = _service_or_http()
    identity = service.db.get_global_identity(global_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="Global identity not found")

    meta = identity.get("watchlist_meta") or {}
    filename = str(meta.get("snapshot_filename") or "").strip()
    if filename:
        (_watchlist_dir() / filename).unlink(missing_ok=True)
    (_watchlist_dir() / f"{global_id}.jpg").unlink(missing_ok=True)
    snapshot_path = meta.get("snapshot_path")
    if snapshot_path:
        Path(str(snapshot_path)).unlink(missing_ok=True)

    deleted = service.db.delete_global_identity(global_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Global identity not found")
    return {"status": "success", "global_id": global_id}


@router.get("/api/records/tracklets")
def get_tracklets(limit: int = 50):
    service = _service_or_http()
    return {"records": service.db.list_tracklets(limit=limit)}


@router.get("/api/osint/graph")
def osint_graph():
    """Return a graph of all watchlisted identities and their camera movements.
    Each person is a node; cameras they were seen in are nodes connected by edges
    ordered chronologically. Also includes OSINT profile data from watchlist_meta."""
    service = _service_or_http()
    conn = service.db._connect()
    try:
        identities = conn.execute(
            "SELECT * FROM global_identities WHERE watchlist_flag=1 ORDER BY last_seen_ts DESC"
        ).fetchall()
    finally:
        conn.close()

    nodes: list[dict] = []
    edges: list[dict] = []
    camera_node_ids: set[str] = set()

    for identity in identities:
        import json as _json
        gid = identity["global_id"]
        meta = _json.loads(identity["watchlist_meta"] or "{}")
        display = meta.get("full_name") or meta.get("display_name") or gid

        # Person node
        nodes.append({
            "id": gid,
            "type": "person",
            "label": display,
            "threat_level": meta.get("threat_level", "UNKNOWN"),
            "snapshot_url": _watchlist_snapshot_url(gid, identity["last_seen_ts"]),
            "meta": {k: v for k, v in meta.items() if k not in ("snapshot_path", "snapshot_filename")},
        })

        # Tracklets for this identity (ordered by start_ts)
        tracklets = service.db.get_tracklets_for_global(gid, limit=200)
        tracklets_sorted = sorted(tracklets, key=lambda t: t.get("start_ts") or "")

        for trk in tracklets_sorted:
            cam_id = trk["camera_id"]
            node_id = f"cam::{cam_id}"

            # Camera node (deduplicated)
            if node_id not in camera_node_ids:
                camera_node_ids.add(node_id)
                nodes.append({"id": node_id, "type": "camera", "label": cam_id})

            # Edge: camera → person (first sighting in this camera)
            edges.append({
                "id": f"{node_id}>{gid}::{trk['tracklet_id']}",
                "from": node_id,
                "to": gid,
                "tracklet_id": trk["tracklet_id"],
                "timestamp": trk.get("start_ts"),
                "end_ts": trk.get("end_ts"),
                "frame_count": trk.get("frame_count"),
            })

    return {"nodes": nodes, "edges": edges}


@router.post("/api/tracklet/{tracklet_id}/enrich")
def enrich_tracklet(
    tracklet_id: str,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = None,
):
    _require_admin_token(authorization, x_api_key, api_key)
    service = _service_or_http()
    if service.db.get_tracklet(tracklet_id) is None:
        raise HTTPException(status_code=404, detail=f"Tracklet not found: {tracklet_id}")
    result = service.submit_manual_enrichment(tracklet_id)
    return {"status": "submitted", "result": result}


@router.get("/api/incident/{incident_id}")
def get_incident(incident_id: str):
    service = _service_or_http()
    incident = service.db.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.get("/api/metrics/worker_queue")
def worker_queue_metrics():
    service = _service_or_http()
    return service.queue_metrics()


@router.get("/api/stream/snapshot/{global_id}/{ts}.jpg")
def stream_snapshot(global_id: str, ts: str, request: Request):
    _require_admin_token(
        request.headers.get("Authorization"),
        request.headers.get("X-API-Key"),
        request.query_params.get("api_key"),
    )
    path = _snapshot_path(global_id, ts)
    if not path.exists():
        # fallback to watchlist image
        service = _service_or_http()
        identity = service.db.get_global_identity(global_id)
        meta = identity.get("watchlist_meta") if identity else {}
        fallback_name = str((meta or {}).get("snapshot_filename") or f"{global_id}.jpg")
        fallback = _watchlist_dir() / fallback_name
        if fallback.exists():
            return FileResponse(fallback)
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(path)
