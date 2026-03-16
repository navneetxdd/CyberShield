from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from osint_reid.config import ADMIN_API_TOKEN, SNAPSHOT_DIR
from osint_reid.db import now_utc_iso
from osint_reid.service import get_osint_service

logger = logging.getLogger("osint_reid.api")

router = APIRouter()
_state_ws_clients: set[WebSocket] = set()


def _require_admin_token(auth_header: str | None) -> None:
    configured_token = os.getenv("ADMIN_API_TOKEN", ADMIN_API_TOKEN).strip()
    if not configured_token:
        raise HTTPException(status_code=503, detail="ADMIN_API_TOKEN is not configured. Set it to enable protected write endpoints.")
    supplied = (auth_header or "").strip()
    if supplied.startswith("Bearer "):
        supplied = supplied[len("Bearer ") :].strip()
    if supplied != configured_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")


def _watchlist_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "watchlist"
    path.mkdir(exist_ok=True)
    return path


def _service_or_http():
    try:
        return get_osint_service()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"OSINT service unavailable: {exc}") from exc


def _snapshot_path(global_id: str, ts: str) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = ts.replace(":", "-")
    return SNAPSHOT_DIR / f"{global_id}_{safe_ts}.jpg"


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
        entries.append(
            {
                "identity": meta.get("display_name") or item["global_id"],
                "global_id": item["global_id"],
                "filename": meta.get("snapshot_filename", ""),
                "last_seen_ts": item.get("last_seen_ts"),
                "snapshot_path": meta.get("snapshot_path", ""),
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
):
    _require_admin_token(authorization)

    raw = await file.read()
    image = _load_image_from_upload(raw)

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

    watchlist_path = _watchlist_dir() / f"{global_id}.jpg"
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
        "display_name": name,
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
            "identity": name,
            "global_id": global_id,
            "filename": watchlist_path.name,
            "last_seen_ts": ts,
            "snapshot_path": str(snapshot),
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
    return {"identity": safe_identity, "match_history": history, "incidents": incidents}


@router.get("/api/records/tracklets")
def get_tracklets(limit: int = 50):
    service = _service_or_http()
    return {"records": service.db.list_tracklets(limit=limit)}


@router.post("/api/tracklet/{tracklet_id}/enrich")
def enrich_tracklet(tracklet_id: str, authorization: str | None = Header(default=None)):
    _require_admin_token(authorization)
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
def stream_snapshot(global_id: str, ts: str):
    path = _snapshot_path(global_id, ts)
    if not path.exists():
        # fallback to watchlist image
        fallback = _watchlist_dir() / f"{global_id}.jpg"
        if fallback.exists():
            return FileResponse(fallback)
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(path)
