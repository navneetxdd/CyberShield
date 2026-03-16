"""
Vehicle Intelligence Module – Configuration
============================================
All tuneable parameters read from environment variables with safe defaults.
Values are intentionally kept separate from the parent pipeline config so
the VI module can be deployed or tested independently.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Root of the integrated-video-analytics application
APP_DIR: Path = Path(__file__).resolve().parent.parent
# Shared SQLite database (same file as the main app for simplicity)
VI_DB_PATH: Path = APP_DIR / "analytics.db"
# Directory for vehicle plate watchlist text files (one plate per line or file)
VI_WATCHLIST_DIR: Path = APP_DIR / "vehicle_watchlist"
VI_WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Plate normalisation helpers (mirrors pipeline.py so we stay consistent)
# ---------------------------------------------------------------------------
# Accepts plates such as MH12AB1234, KA01C9999, DL4CAF3456 etc.
PLATE_TEXT_PATTERN: re.Pattern = re.compile(
    r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4}$"
)
PLATE_ALLOWLIST: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


# ---------------------------------------------------------------------------
# Internal helpers (no external dependencies)
# ---------------------------------------------------------------------------
def _read_env_float(
    name: str,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except (AttributeError, ValueError):
        return default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _read_env_int(
    name: str,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError):
        return default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _read_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
VI_DETECT_CONFIDENCE: float = _read_env_float(
    "VI_DETECT_CONFIDENCE", 0.30, minimum=0.05, maximum=0.95
)
VI_PLATE_CONFIDENCE: float = _read_env_float(
    "VI_PLATE_CONFIDENCE", 0.25, minimum=0.05, maximum=0.95
)
VI_PLATE_OCR_TARGET_WIDTH: int = _read_env_int(
    "VI_PLATE_TARGET_WIDTH", 480, minimum=240, maximum=1280
)

# ---------------------------------------------------------------------------
# OCR quality gates
# ---------------------------------------------------------------------------
VI_PADDLE_MIN_CONFIDENCE: float = _read_env_float(
    "VI_PADDLE_MIN_CONFIDENCE", 0.75, minimum=0.1, maximum=0.99
)
VI_LOCAL_OCR_MIN_CONFIDENCE: float = _read_env_float(
    "VI_LOCAL_OCR_MIN_CONFIDENCE", 0.50, minimum=0.05, maximum=0.95
)
VI_PLATE_SCAN_INTERVAL: float = _read_env_float(
    "VI_PLATE_SCAN_INTERVAL", 5.0, minimum=0.5, maximum=60.0
)
# Number of OCR hits required before a plate is accepted (reduces noise)
VI_PLATE_CONFIRMATION_HITS: int = _read_env_int(
    "VI_PLATE_CONFIRMATION_HITS", 2, minimum=1, maximum=8
)
# Confidence threshold above which a single OCR read is accepted immediately
VI_PLATE_DIRECT_ACCEPT_CONFIDENCE: float = _read_env_float(
    "VI_PLATE_DIRECT_ACCEPT_CONFIDENCE", 0.82, minimum=0.1, maximum=0.99
)

# ---------------------------------------------------------------------------
# History & analytics
# ---------------------------------------------------------------------------
VI_HISTORY_RETENTION_DAYS: int = _read_env_int(
    "VI_HISTORY_RETENTION_DAYS", 30, minimum=1, maximum=365
)
# Minimum total detections for a vehicle to be classified as "frequent"
VI_FREQUENT_THRESHOLD: int = _read_env_int(
    "VI_FREQUENT_THRESHOLD", 3, minimum=1, maximum=10_000
)
# Look-back window for dashboard analytics (hours)
VI_ANALYTICS_LOOKBACK_HOURS: int = _read_env_int(
    "VI_ANALYTICS_LOOKBACK_HOURS", 24, minimum=1, maximum=720
)

# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------
# Default alert priority for watchlist matches (1=low, 2=medium, 3=high)
VI_DEFAULT_ALERT_PRIORITY: int = _read_env_int(
    "VI_DEFAULT_ALERT_PRIORITY", 2, minimum=1, maximum=3
)
# Maximum unacknowledged alerts returned by the API
VI_MAX_ALERTS: int = _read_env_int("VI_MAX_ALERTS", 200, minimum=1, maximum=5000)

# ---------------------------------------------------------------------------
# Vehicle classes recognised by the detector
# ---------------------------------------------------------------------------
VI_VEHICLE_CLASSES: set[str] = {"car", "motorcycle", "bus", "truck"}
# COCO class IDs that map to vehicle types
VI_TARGET_CLASSES: dict[int, str] = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
