from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

from osint_reid.aggregation import aggregate_tracklet_payload
from osint_reid.camera_graph import CameraGraph
from osint_reid.config import MAX_CROPS_PER_TRACKLET, MIN_TRACKLET_FRAMES, TRACKLET_IDLE_SECONDS, WORKER_POOL_SIZE
from osint_reid.cross_camera_matcher import CrossCameraMatcher
from osint_reid.db import OSINTDB
from osint_reid.reid_worker import ReIDWorker
from osint_reid.vehicle_classifier import VehicleClassifier

logger = logging.getLogger("osint_reid.service")


@dataclass
class TrackletBuffer:
    tracklet_id: str
    camera_id: str
    class_name: str
    start_ts: str
    end_ts: str
    frame_count: int = 0
    crops: list[np.ndarray] = field(default_factory=list)
    face_crops: list[np.ndarray] = field(default_factory=list)
    face_confidences: list[float] = field(default_factory=list)
    bbox_history: list[list[Any]] = field(default_factory=list)
    last_seen_epoch: float = 0.0


class OSINTService:
    def __init__(self):
        self.db = OSINTDB()
        self.camera_graph = CameraGraph()
        self.reid_worker = ReIDWorker()
        self.vehicle_classifier = VehicleClassifier()
        self.executor = ThreadPoolExecutor(max_workers=WORKER_POOL_SIZE)
        self.matcher = CrossCameraMatcher(self.db, self.camera_graph, incident_sink=self.push_incident)

        self._lock = threading.RLock()
        self._buffers: dict[str, TrackletBuffer] = {}
        self._pending: dict[str, Future[Any]] = {}
        self._incidents: list[dict[str, Any]] = []
        self._movement_events: list[dict[str, Any]] = []

    def queue_metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "pending_enrichments": len(self._pending),
                "active_tracklet_buffers": len(self._buffers),
                "incident_buffer": len(self._incidents),
            }

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def push_incident(self, incident: dict[str, Any]) -> None:
        with self._lock:
            self._incidents.insert(0, incident)
            del self._incidents[100:]

    def pop_incidents(self) -> list[dict[str, Any]]:
        with self._lock:
            out = list(self._incidents)
            self._incidents.clear()
            return out

    def push_movement_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._movement_events.insert(0, event)
            del self._movement_events[200:]

    def get_movement_events(self, since_iso: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if since_iso is None:
                return list(self._movement_events)
            return [e for e in self._movement_events if e.get("timestamp", "") >= since_iso]

    def collect_detection(
        self,
        camera_id: str,
        tracker_id: int,
        class_name: str,
        frame: np.ndarray,
        bbox_xyxy: tuple[int, int, int, int],
        ts_iso: str,
        confidence: float,
    ) -> None:
        tracklet_id = f"{camera_id}:{tracker_id}:{class_name}"
        x1, y1, x2, y2 = bbox_xyxy
        x1 = max(x1, 0)
        y1 = max(y1, 0)
        x2 = min(x2, frame.shape[1])
        y2 = min(y2, frame.shape[0])
        if x2 <= x1 or y2 <= y1:
            return
        crop = frame[y1:y2, x1:x2].copy()
        if crop.size == 0:
            return

        with self._lock:
            buffer = self._buffers.get(tracklet_id)
            if buffer is None:
                buffer = TrackletBuffer(
                    tracklet_id=tracklet_id,
                    camera_id=camera_id,
                    class_name=class_name,
                    start_ts=ts_iso,
                    end_ts=ts_iso,
                    last_seen_epoch=time.time(),
                )
                self._buffers[tracklet_id] = buffer

            buffer.end_ts = ts_iso
            buffer.last_seen_epoch = time.time()
            buffer.frame_count += 1
            if len(buffer.crops) < MAX_CROPS_PER_TRACKLET:
                buffer.crops.append(crop)
            if class_name == "person":
                face_h = max(int(crop.shape[0] * 0.55), 1)
                face_crop = crop[:face_h, :].copy()
                if face_crop.size > 0 and len(buffer.face_crops) < MAX_CROPS_PER_TRACKLET:
                    buffer.face_crops.append(face_crop)
                    buffer.face_confidences.append(float(confidence))

            w = int(x2 - x1)
            h = int(y2 - y1)
            buffer.bbox_history.append([ts_iso, int(x1), int(y1), w, h])
            if len(buffer.bbox_history) > 128:
                buffer.bbox_history = buffer.bbox_history[-128:]

    def flush_stale(self) -> None:
        now = time.time()
        stale_ids: list[str] = []
        with self._lock:
            for tracklet_id, buf in self._buffers.items():
                if (now - buf.last_seen_epoch) >= TRACKLET_IDLE_SECONDS:
                    stale_ids.append(tracklet_id)

            for tracklet_id in stale_ids:
                buf = self._buffers.pop(tracklet_id)
                if buf.frame_count < MIN_TRACKLET_FRAMES:
                    continue
                if tracklet_id in self._pending and not self._pending[tracklet_id].done():
                    continue
                fut = self.executor.submit(self._enrich_tracklet_buffer, buf)
                self._pending[tracklet_id] = fut

    def _enrich_tracklet_buffer(self, buf: TrackletBuffer) -> None:
        self.db.mark_enrichment_started(buf.tracklet_id)
        try:
            reid_mat = self.reid_worker.compute_reid_embeddings(buf.crops)
            face_mat = self.reid_worker.compute_face_embeddings(buf.face_crops)
            reid_embeddings = [row for row in reid_mat] if reid_mat.size > 0 else []
            face_embeddings = [row for row in face_mat] if face_mat.size > 0 else []

            color_name = "unknown"
            color_conf = 0.0
            color_hist = np.zeros((8 * 8 * 8,), dtype=np.float32)
            make_model = "Unknown"
            make_model_conf = 0.0

            # Compute colour histogram for ALL tracklets (vehicles and persons).
            # For persons this provides the only appearance signal when face/ReID
            # embeddings are unavailable, enabling colour-based cross-camera linking.
            if buf.crops:
                _, _, color_hist = self.vehicle_classifier.classify_color(buf.crops)

            if buf.class_name != "person":
                make_model, make_model_conf = self.vehicle_classifier.classify_vehicle_crops(buf.crops)
                color_name, color_conf, _ = self.vehicle_classifier.classify_color(buf.crops)
                self.db.upsert_vehicle(
                    tracklet_id=buf.tracklet_id,
                    camera_id=buf.camera_id,
                    make_model=make_model,
                    make_model_confidence=make_model_conf,
                    color=color_name,
                    color_confidence=color_conf,
                )

            payload = aggregate_tracklet_payload(
                {
                    "tracklet_id": buf.tracklet_id,
                    "camera_id": buf.camera_id,
                    "start_ts": buf.start_ts,
                    "end_ts": buf.end_ts,
                    "frame_count": buf.frame_count,
                    "reid_embeddings": reid_embeddings,
                    "face_embeddings": face_embeddings,
                    "face_confidences": buf.face_confidences,
                    "bbox_history": buf.bbox_history,
                    "color_hist": color_hist,
                    "plate_assoc": None,
                }
            )
            self.db.insert_tracklet(**payload)

            match_out = self.matcher.match_tracklet(
                tracklet_id=buf.tracklet_id,
                camera_id=buf.camera_id,
                start_ts=buf.start_ts,
                end_ts=buf.end_ts,
                aggregated_face=payload["aggregated_face"],
                aggregated_reid=payload["aggregated_reid"],
                color_hist=payload["color_histogram"],
            )
            global_id = match_out.get("global_id")
            if global_id and buf.class_name == "person":
                identity = self.db.get_global_identity(global_id)
                prev_camera = identity.get("last_seen_camera") if identity else None
                if prev_camera and prev_camera != buf.camera_id:
                    self.push_movement_event({
                        "global_id": global_id,
                        "from_camera": prev_camera,
                        "to_camera": buf.camera_id,
                        "timestamp": buf.end_ts,
                        "display_name": (identity.get("display_name") or global_id) if identity else global_id,
                    })
            logger.info(
                "Tracklet enrichment complete",
                extra={
                    "stage": "enrich",
                    "tracklet_id": buf.tracklet_id,
                    "status": match_out.get("status"),
                    "global_id": match_out.get("global_id"),
                },
            )
        finally:
            self.db.mark_enrichment_completed(buf.tracklet_id)
            with self._lock:
                self._pending.pop(buf.tracklet_id, None)

    def enrich_tracklet_now(self, tracklet_id: str) -> dict[str, Any]:
        record = self.db.get_tracklet(tracklet_id)
        if record is None:
            raise ValueError(f"Tracklet not found: {tracklet_id}")
        out = self.matcher.match_tracklet(
            tracklet_id=tracklet_id,
            camera_id=str(record["camera_id"]),
            start_ts=str(record["start_ts"]),
            end_ts=str(record["end_ts"]),
            aggregated_face=record.get("aggregated_face"),
            aggregated_reid=record.get("aggregated_reid"),
            color_hist=record.get("color_histogram"),
        )
        return out

    def submit_manual_enrichment(self, tracklet_id: str) -> dict[str, Any]:
        with self._lock:
            existing = self._pending.get(tracklet_id)
            if existing is not None and not existing.done():
                return {"status": "queued", "tracklet_id": tracklet_id}
            fut = self.executor.submit(self._enrich_existing_tracklet, tracklet_id)
            self._pending[tracklet_id] = fut
        return {"status": "queued", "tracklet_id": tracklet_id}

    def _enrich_existing_tracklet(self, tracklet_id: str) -> None:
        try:
            self.db.mark_enrichment_started(tracklet_id)
            self.enrich_tracklet_now(tracklet_id)
        finally:
            self.db.mark_enrichment_completed(tracklet_id)
            with self._lock:
                self._pending.pop(tracklet_id, None)


_service_singleton: OSINTService | None = None


def get_osint_service() -> OSINTService:
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = OSINTService()
    return _service_singleton
