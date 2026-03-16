from __future__ import annotations

from typing import Any

import numpy as np

from osint_reid.config import FACE_CONF_THRESHOLD


def aggregate_embeddings(embs: list[np.ndarray], method: str = "median") -> np.ndarray | None:
    if not embs:
        return None
    arr = np.asarray([np.asarray(e, dtype=np.float32) for e in embs], dtype=np.float32)
    if method == "mean":
        vec = arr.mean(axis=0)
    else:
        vec = np.median(arr, axis=0)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.astype(np.float32)


def aggregate_face_embeddings(
    face_embs: list[np.ndarray],
    face_confidences: list[float],
    method: str = "median",
) -> np.ndarray | None:
    filtered = [emb for emb, conf in zip(face_embs, face_confidences) if float(conf) >= FACE_CONF_THRESHOLD]
    return aggregate_embeddings(filtered, method=method)


def aggregate_tracklet_payload(tracklet: dict[str, Any]) -> dict[str, Any]:
    reid_vec = aggregate_embeddings(tracklet.get("reid_embeddings", []), method="median")
    face_vec = aggregate_face_embeddings(
        tracklet.get("face_embeddings", []),
        tracklet.get("face_confidences", []),
        method="median",
    )
    color_hist = tracklet.get("color_hist")
    if color_hist is not None:
        color_hist = np.asarray(color_hist, dtype=np.float32)
    return {
        "tracklet_id": tracklet["tracklet_id"],
        "camera_id": tracklet["camera_id"],
        "start_ts": tracklet["start_ts"],
        "end_ts": tracklet["end_ts"],
        "frame_count": int(tracklet.get("frame_count") or 0),
        "aggregated_reid": reid_vec,
        "aggregated_face": face_vec,
        "color_histogram": color_hist,
        "bbox_history": tracklet.get("bbox_history", []),
        "plate_assoc": tracklet.get("plate_assoc"),
    }
