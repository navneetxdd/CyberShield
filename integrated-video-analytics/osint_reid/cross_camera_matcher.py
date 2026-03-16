from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from osint_reid.camera_graph import CameraGraph
from osint_reid.config import AMBIGUITY_LOWER, FACE_LINK_TH, FUSED_LINK_TH
from osint_reid.db import OSINTDB

logger = logging.getLogger("osint_reid.matcher")


def _parse_iso_utc(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _cosine(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.0
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom <= 0:
        return 0.0
    return max(-1.0, min(1.0, float(np.dot(va, vb) / denom)))


def _to_score(cosine_sim: float) -> float:
    return (cosine_sim + 1.0) / 2.0


class CrossCameraMatcher:
    def __init__(self, db: OSINTDB, camera_graph: CameraGraph, incident_sink: Callable[[dict[str, Any]], None] | None = None):
        self.db = db
        self.camera_graph = camera_graph
        self.incident_sink = incident_sink

    def _fused_score(
        self,
        face_score: float,
        reid_score: float,
        color_score: float,
        plausible_score: float,
    ) -> float:
        return 0.60 * face_score + 0.30 * reid_score + 0.05 * color_score + 0.05 * plausible_score

    def _iter_candidates(self) -> list[dict[str, Any]]:
        return self.db.list_global_identities(watchlist_only=False)

    def match_tracklet(
        self,
        tracklet_id: str,
        camera_id: str,
        start_ts: str,
        end_ts: str,
        aggregated_face: np.ndarray | None,
        aggregated_reid: np.ndarray | None,
        color_hist: np.ndarray | None,
    ) -> dict[str, Any]:
        candidates = self._iter_candidates()
        best: dict[str, Any] | None = None
        best_score = 0.0
        best_face = 0.0

        candidate_start = _parse_iso_utc(start_ts)

        for candidate in candidates:
            g_face = self.db.blob_to_vec(candidate.get("face_embedding"))
            g_reid = self.db.blob_to_vec(candidate.get("reid_embedding"))
            face_score = _to_score(_cosine(aggregated_face, g_face))
            reid_score = _to_score(_cosine(aggregated_reid, g_reid))
            if color_hist is not None:
                # color signal is currently weakly represented; use bounded neutral score
                color_score = 0.6
            else:
                color_score = 0.0

            delta_seconds = (candidate_start - _parse_iso_utc(candidate["last_seen_ts"])).total_seconds()
            plausible_score = self.camera_graph.camera_plausibility(
                candidate.get("last_seen_camera") or "",
                camera_id,
                delta_seconds,
            )
            fused = self._fused_score(face_score, reid_score, color_score, plausible_score)
            if fused > best_score:
                best_score = fused
                best_face = face_score
                best = candidate

        if best is None:
            gid = self.db.create_global_identity(
                camera_id=camera_id,
                seen_ts=end_ts,
                face_embedding=aggregated_face,
                reid_embedding=aggregated_reid,
                confidence=0.55,
            )
            self.db.set_tracklet_global(tracklet_id, gid)
            return {"status": "new_identity", "global_id": gid, "score": 0.55}

        if best_face >= FACE_LINK_TH and best_score >= FUSED_LINK_TH:
            gid = best["global_id"]
            self.db.update_global_identity(
                global_id=gid,
                camera_id=camera_id,
                seen_ts=end_ts,
                face_embedding=aggregated_face,
                reid_embedding=aggregated_reid,
                confidence=best_score,
            )
            self.db.set_tracklet_global(tracklet_id, gid)
            return {"status": "linked", "global_id": gid, "score": round(best_score, 4)}

        if AMBIGUITY_LOWER <= best_score < FUSED_LINK_TH:
            incident_id = self.db.create_incident(
                tracklet_id=tracklet_id,
                candidate_global_id=best["global_id"],
                reason="ambiguous_multimodal_match",
                score=best_score,
            )
            payload = {
                "type": "identity_incident",
                "incident_id": incident_id,
                "tracklet_id": tracklet_id,
                "candidate_global_id": best["global_id"],
                "score": round(best_score, 4),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            if self.incident_sink is not None:
                self.incident_sink(payload)
            logger.info("Created ambiguity incident", extra={"incident_id": incident_id, "tracklet_id": tracklet_id})
            return {"status": "ambiguous", "incident_id": incident_id, "score": round(best_score, 4)}

        gid = self.db.create_global_identity(
            camera_id=camera_id,
            seen_ts=end_ts,
            face_embedding=aggregated_face,
            reid_embedding=aggregated_reid,
            confidence=max(best_score, 0.5),
        )
        self.db.set_tracklet_global(tracklet_id, gid)
        return {"status": "new_identity", "global_id": gid, "score": round(max(best_score, 0.5), 4)}
