from __future__ import annotations

import json
import pickle
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from migrations.run import run_migration
from osint_reid.config import OSINT_DB_PATH


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OSINTDB:
    def __init__(self, db_path: Path = OSINT_DB_PATH):
        self.db_path = db_path
        run_migration(db_path=db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @staticmethod
    def vec_to_blob(vec: np.ndarray | None) -> bytes | None:
        if vec is None:
            return None
        return np.asarray(vec, dtype=np.float32).tobytes()

    @staticmethod
    def blob_to_vec(blob: bytes | None) -> np.ndarray | None:
        if blob is None:
            return None
        return np.frombuffer(blob, dtype=np.float32)

    @staticmethod
    def obj_to_blob(obj: Any) -> bytes:
        return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def blob_to_obj(blob: bytes | None, default: Any = None) -> Any:
        if blob is None:
            return default
        return pickle.loads(blob)

    def insert_tracklet(
        self,
        tracklet_id: str,
        camera_id: str,
        start_ts: str,
        end_ts: str,
        frame_count: int,
        aggregated_reid: np.ndarray | None,
        aggregated_face: np.ndarray | None,
        color_histogram: np.ndarray | None,
        bbox_history: list[list[Any]],
        plate_assoc: str | None = None,
    ) -> None:
        ts = now_utc_iso()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO tracklets (
                  tracklet_id, camera_id, start_ts, end_ts, frame_count,
                  aggregated_reid, aggregated_face, color_histogram, bbox_history,
                  plate_assoc, resolved_global_id, enrichment_started_at,
                  enrichment_completed_at, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          COALESCE((SELECT resolved_global_id FROM tracklets WHERE tracklet_id=?), NULL),
                          COALESCE((SELECT enrichment_started_at FROM tracklets WHERE tracklet_id=?), NULL),
                          COALESCE((SELECT enrichment_completed_at FROM tracklets WHERE tracklet_id=?), NULL),
                          ?)
                """,
                (
                    tracklet_id,
                    camera_id,
                    start_ts,
                    end_ts,
                    int(frame_count),
                    self.vec_to_blob(aggregated_reid),
                    self.vec_to_blob(aggregated_face),
                    self.vec_to_blob(color_histogram),
                    json.dumps(bbox_history),
                    plate_assoc,
                    tracklet_id,
                    tracklet_id,
                    tracklet_id,
                    ts,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_enrichment_started(self, tracklet_id: str) -> None:
        ts = now_utc_iso()
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracklets SET enrichment_started_at=?, last_updated=? WHERE tracklet_id=?",
                (ts, ts, tracklet_id),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_enrichment_completed(self, tracklet_id: str) -> None:
        ts = now_utc_iso()
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracklets SET enrichment_completed_at=?, last_updated=? WHERE tracklet_id=?",
                (ts, ts, tracklet_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_tracklets(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM tracklets ORDER BY last_updated DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["bbox_history"] = json.loads(item.get("bbox_history") or "[]")
                _reid_vec = self.blob_to_vec(item.get("aggregated_reid")) if item.get("aggregated_reid") else None
                item["aggregated_reid"] = _reid_vec.tolist() if _reid_vec is not None else None
                _face_vec = self.blob_to_vec(item.get("aggregated_face")) if item.get("aggregated_face") else None
                item["aggregated_face"] = _face_vec.tolist() if _face_vec is not None else None
                _hist_vec = self.blob_to_vec(item.get("color_histogram")) if item.get("color_histogram") else None
                item["color_histogram"] = _hist_vec.tolist() if _hist_vec is not None else None
                result.append(item)
            return result
        finally:
            conn.close()

    def get_tracklet(self, tracklet_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM tracklets WHERE tracklet_id=?", (tracklet_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["bbox_history"] = json.loads(item.get("bbox_history") or "[]")
            item["aggregated_reid"] = self.blob_to_vec(item.get("aggregated_reid"))
            item["aggregated_face"] = self.blob_to_vec(item.get("aggregated_face"))
            item["color_histogram"] = self.blob_to_vec(item.get("color_histogram"))
            return item
        finally:
            conn.close()

    def create_global_identity(
        self,
        camera_id: str,
        seen_ts: str,
        face_embedding: np.ndarray | None,
        reid_embedding: np.ndarray | None,
        confidence: float,
        watchlist_flag: int = 0,
        watchlist_meta: dict[str, Any] | None = None,
    ) -> str:
        global_id = f"gid_{uuid.uuid4().hex[:12]}"
        created_at = now_utc_iso()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO global_identities (
                  global_id, created_at, last_seen_ts, last_seen_camera,
                  face_embedding, reid_embedding, watchlist_flag, watchlist_meta, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    global_id,
                    created_at,
                    seen_ts,
                    camera_id,
                    self.vec_to_blob(face_embedding),
                    self.vec_to_blob(reid_embedding),
                    int(watchlist_flag),
                    json.dumps(watchlist_meta or {}),
                    float(confidence),
                ),
            )
            conn.commit()
            return global_id
        finally:
            conn.close()

    def update_global_identity(
        self,
        global_id: str,
        camera_id: str,
        seen_ts: str,
        face_embedding: np.ndarray | None,
        reid_embedding: np.ndarray | None,
        confidence: float,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE global_identities
                SET
                  last_seen_ts=?,
                  last_seen_camera=?,
                  face_embedding=COALESCE(?, face_embedding),
                  reid_embedding=COALESCE(?, reid_embedding),
                  confidence=?
                WHERE global_id=?
                """,
                (
                    seen_ts,
                    camera_id,
                    self.vec_to_blob(face_embedding),
                    self.vec_to_blob(reid_embedding),
                    float(confidence),
                    global_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def set_tracklet_global(self, tracklet_id: str, global_id: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracklets SET resolved_global_id=?, last_updated=? WHERE tracklet_id=?",
                (global_id, now_utc_iso(), tracklet_id),
            )
            conn.commit()
        finally:
            conn.close()

    def list_global_identities(self, watchlist_only: bool = False) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            query = "SELECT * FROM global_identities"
            params: Iterable[Any] = ()
            if watchlist_only:
                query += " WHERE watchlist_flag=1"
            query += " ORDER BY last_seen_ts DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["watchlist_meta"] = json.loads(item.get("watchlist_meta") or "{}")
                out.append(item)
            return out
        finally:
            conn.close()

    def get_global_identity(self, global_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM global_identities WHERE global_id=?", (global_id,)).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["watchlist_meta"] = json.loads(item.get("watchlist_meta") or "{}")
            return item
        finally:
            conn.close()

    def delete_global_identity(self, global_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE tracklets SET resolved_global_id=NULL, last_updated=? WHERE resolved_global_id=?",
                (now_utc_iso(), global_id),
            )
            cursor = conn.execute("DELETE FROM global_identities WHERE global_id=?", (global_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def create_incident(
        self,
        tracklet_id: str,
        candidate_global_id: str | None,
        reason: str,
        score: float,
    ) -> str:
        incident_id = f"iid_{uuid.uuid4().hex[:12]}"
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO identity_incidents (
                  incident_id, tracklet_id, candidate_global_id,
                  reason, score, created_at, resolved, operator_action
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (incident_id, tracklet_id, candidate_global_id, reason, float(score), now_utc_iso(), "pending_review"),
            )
            conn.commit()
            return incident_id
        finally:
            conn.close()

    def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM identity_incidents WHERE incident_id=?", (incident_id,)
            ).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def get_recent_incidents_for_global(self, global_id: str, limit: int = 25) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT * FROM identity_incidents
                WHERE candidate_global_id=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (global_id, int(limit)),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_tracklets_for_global(self, global_id: str, limit: int = 50) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT tracklet_id, camera_id, start_ts, end_ts, frame_count, bbox_history, resolved_global_id
                FROM tracklets
                WHERE resolved_global_id=?
                ORDER BY end_ts DESC
                LIMIT ?
                """,
                (global_id, int(limit)),
            ).fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["bbox_history"] = json.loads(item.get("bbox_history") or "[]")
                out.append(item)
            return out
        finally:
            conn.close()

    def upsert_vehicle(
        self,
        tracklet_id: str,
        camera_id: str,
        make_model: str,
        make_model_confidence: float,
        color: str,
        color_confidence: float,
    ) -> str:
        vehicle_id = f"vid_{uuid.uuid4().hex[:12]}"
        now = now_utc_iso()
        conn = self._connect()
        try:
            existing = conn.execute("SELECT vehicle_id, first_seen_ts FROM vehicles WHERE tracklet_id=?", (tracklet_id,)).fetchone()
            if existing is not None:
                vehicle_id = existing["vehicle_id"]
                first_seen = existing["first_seen_ts"]
                conn.execute(
                    """
                    UPDATE vehicles
                    SET last_seen_ts=?, camera_id=?, make_model=?, make_model_confidence=?, color=?, color_confidence=?
                    WHERE vehicle_id=?
                    """,
                    (now, camera_id, make_model, float(make_model_confidence), color, float(color_confidence), vehicle_id),
                )
            else:
                first_seen = now
                conn.execute(
                    """
                    INSERT INTO vehicles (
                      vehicle_id, tracklet_id, first_seen_ts, last_seen_ts, camera_id,
                      make_model, make_model_confidence, color, color_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vehicle_id,
                        tracklet_id,
                        first_seen,
                        now,
                        camera_id,
                        make_model,
                        float(make_model_confidence),
                        color,
                        float(color_confidence),
                    ),
                )
            conn.commit()
            return vehicle_id
        finally:
            conn.close()
