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

    def _get_candidate_color_hist(self, global_id: str) -> np.ndarray | None:
        """Return the colour histogram from the most-recent tracklet for this global identity."""
        latest = self.db.get_latest_tracklet_for_global(global_id)
        if latest is None:
            return None
        raw = latest.get("color_histogram")
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            return np.frombuffer(raw, dtype=np.float32)
        return np.asarray(raw, dtype=np.float32)

    def _fused_score(
        self,
        face_score: float,
        reid_score: float,
        color_score: float,
        plausible_score: float,
        has_face: bool = False,
        has_reid: bool = False,
    ) -> float:
        if has_face and has_reid:
            # Full multimodal: face dominant
            return 0.55 * face_score + 0.30 * reid_score + 0.10 * color_score + 0.05 * plausible_score
        elif has_face:
            return 0.65 * face_score + 0.15 * color_score + 0.20 * plausible_score
        elif has_reid:
            # ReID only (most common when insightface absent): body appearance dominant
            return 0.70 * reid_score + 0.20 * color_score + 0.10 * plausible_score
        else:
            # Colour + temporal plausibility only fallback
            return 0.75 * color_score + 0.25 * plausible_score

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
        has_face = aggregated_face is not None and aggregated_face.size > 0
        has_reid = aggregated_reid is not None and aggregated_reid.size > 0

        # Choose link threshold based on available signals
        if has_face:
            link_th = FUSED_LINK_TH          # 0.70 — high confidence with face
        elif has_reid:
            link_th = 0.60                    # body ReID is reliable enough at 0.60
        else:
            link_th = 0.68                    # colour-only needs high bar to avoid FP

        candidates = self._iter_candidates()
        best: dict[str, Any] | None = None
        best_score = 0.0
        best_face = 0.0

        candidate_start = _parse_iso_utc(start_ts)

        for candidate in candidates:
            g_face = self.db.blob_to_vec(candidate.get("face_embedding"))
            g_reid = self.db.blob_to_vec(candidate.get("reid_embedding"))
            c_has_face = g_face is not None and g_face.size > 0
            c_has_reid = g_reid is not None and g_reid.size > 0

            face_score = _to_score(_cosine(aggregated_face, g_face)) if (has_face and c_has_face) else 0.5
            reid_score = _to_score(_cosine(aggregated_reid, g_reid)) if (has_reid and c_has_reid) else 0.5

            # Colour: compare actual histograms from the most recent tracklet
            if color_hist is not None and color_hist.size > 0:
                g_color = self._get_candidate_color_hist(candidate.get("global_id"))
                if g_color is not None and g_color.size > 0:
                    color_score = _to_score(_cosine(color_hist, g_color))
                else:
                    color_score = 0.5  # neutral when candidate has no hist yet
            else:
                color_score = 0.5

            delta_seconds = (candidate_start - _parse_iso_utc(candidate["last_seen_ts"])).total_seconds()
            plausible_score = self.camera_graph.camera_plausibility(
                candidate.get("last_seen_camera") or "",
                camera_id,
                delta_seconds,
            )
            fused = self._fused_score(
                face_score, reid_score, color_score, plausible_score,
                has_face=has_face, has_reid=has_reid,
            )
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

        # Link condition: score above threshold.  When face IS available, also
        # require face threshold; otherwise body ReID or colour alone can link.
        face_ok = (not has_face) or (best_face >= FACE_LINK_TH)
        if face_ok and best_score >= link_th:
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

        if AMBIGUITY_LOWER <= best_score < link_th:
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
