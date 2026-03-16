from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    return float(raw)


MIN_TRACKLET_FRAMES = _env_int("MIN_TRACKLET_FRAMES", 5)
FACE_CONF_THRESHOLD = _env_float("FACE_CONF_THRESHOLD", 0.6)
FACE_LINK_TH = _env_float("FACE_LINK_TH", 0.45)
REID_LINK_TH = _env_float("REID_LINK_TH", 0.65)
FUSED_LINK_TH = _env_float("FUSED_LINK_TH", 0.70)
AMBIGUITY_LOWER = _env_float("AMBIGUITY_LOWER", 0.50)
REID_MODEL = os.getenv("REID_MODEL", "osnet_x0_25")
VEHICLE_CLASSIFIER = os.getenv("VEHICLE_CLASSIFIER", "efficientnet_b0_stanfordcars")
COLOR_BINS = os.getenv("COLOR_BINS", "HSV_8x8x8")
CAMERA_GRAPH_PATH = BASE_DIR / os.getenv("CAMERA_GRAPH_PATH", "config/camera_graph.json")
WORKER_POOL_SIZE = _env_int("WORKER_POOL_SIZE", 4)
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
ENABLE_SAHI = _env_bool("ENABLE_SAHI", True)
ENABLE_RTDETR_VALIDATOR = _env_bool("ENABLE_RTDETR_VALIDATOR", True)
TRACKLET_IDLE_SECONDS = _env_float("TRACKLET_IDLE_SECONDS", 2.5)
MAX_CROPS_PER_TRACKLET = _env_int("MAX_CROPS_PER_TRACKLET", 16)
OSINT_DB_PATH = BASE_DIR / "analytics.db"
SNAPSHOT_DIR = BASE_DIR / "uploads" / "snapshots"
