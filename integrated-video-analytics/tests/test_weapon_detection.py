"""
Tests for weapon detection — model loading, pipeline inference, API endpoints,
and database interactions.
"""
from __future__ import annotations

import os
import types
from unittest.mock import MagicMock, patch

import database
import pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _use_tmp_db(tmp_path, monkeypatch):
    """Point database module at a fresh temp DB and initialise schema."""
    db_path = tmp_path / "weapon_test.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_db()
    return db_path


# ---------------------------------------------------------------------------
# STEP 1: Model loading
# ---------------------------------------------------------------------------

def test_weapon_model_loads(monkeypatch):
    """SharedResources.get_weapon_detector() returns None when disabled, no error."""
    monkeypatch.setattr(pipeline, "ENABLE_WEAPON_DETECT", False)
    result = pipeline.SharedResources.get_weapon_detector()
    assert result is None


def test_weapon_model_loads_when_enabled(monkeypatch, tmp_path):
    """When ENABLE_WEAPON_DETECT=True and a valid model path is set, detector loads."""
    # Use a real yolo model that's already on disk to avoid network download
    yolo_path = tmp_path.parent.parent / "integrated-video-analytics" / "yolo11s.pt"
    if not yolo_path.exists():
        # Fall back to looking relative to this file
        import pathlib
        yolo_path = pathlib.Path(__file__).resolve().parent.parent / "yolo11s.pt"

    if not yolo_path.exists():
        # Skip if no model available (CI without weights)
        import pytest
        pytest.skip("yolo11s.pt not present — skipping model-load test")

    monkeypatch.setattr(pipeline, "ENABLE_WEAPON_DETECT", True)
    monkeypatch.setattr(pipeline, "WEAPON_MODEL_NAME", str(yolo_path))
    # Reset cached detector so it re-loads
    pipeline.SharedResources._weapon_detector = None
    try:
        detector = pipeline.SharedResources.get_weapon_detector()
        assert detector is not None
    finally:
        pipeline.SharedResources._weapon_detector = None
        monkeypatch.setattr(pipeline, "ENABLE_WEAPON_DETECT", False)


# ---------------------------------------------------------------------------
# STEP 2: Below-threshold detections ignored
# ---------------------------------------------------------------------------

def test_weapon_below_threshold_ignored(monkeypatch, tmp_path):
    """Detections with confidence below WEAPON_DETECT_CONFIDENCE are not persisted."""
    _use_tmp_db(tmp_path, monkeypatch)

    # Build a minimal fake YOLO result with one box below threshold
    conf_threshold = 0.50
    monkeypatch.setattr(pipeline, "WEAPON_DETECT_CONFIDENCE", conf_threshold)
    monkeypatch.setattr(pipeline, "WEAPON_SCAN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(pipeline, "ENABLE_WEAPON_DETECT", True)

    # Create a fake result object that mimics ultralytics output
    import numpy as np
    fake_box = MagicMock()
    fake_box.__len__ = MagicMock(return_value=1)
    fake_box.conf = [conf_threshold - 0.10]   # below threshold
    fake_box.cls = [0]
    fake_box.xyxy = [np.array([10, 10, 100, 100])]

    fake_result = MagicMock()
    fake_result.boxes = fake_box
    fake_result.names = {0: "pistol"}

    mock_detector = MagicMock(return_value=[fake_result])

    import threading, concurrent.futures
    vp = pipeline.VideoPipeline.__new__(pipeline.VideoPipeline)
    vp.camera_id = "cam_test"
    vp.weapon_detector = mock_detector
    vp.last_weapon_scan = 0.0
    vp.weapon_flash_until = 0.0
    vp._last_weapon_boxes = []
    vp.state_lock = threading.RLock()
    vp.db_executor = concurrent.futures.ThreadPoolExecutor(1)
    vp.pending_db_futures = set()

    import numpy as np
    frame = np.zeros((480, 640, 3), dtype="uint8")
    state: dict = {"weapon_alert_count": 0}

    vp._run_weapon_inference(frame, state)

    # DB should have no weapon events
    events = database.get_weapon_events()
    assert events == [], f"Expected no events, got: {events}"
    assert state["weapon_alert_count"] == 0

    vp.db_executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# STEP 3: Weapon event DB insertion
# ---------------------------------------------------------------------------

def test_weapon_event_inserted(monkeypatch, tmp_path):
    """A detection above threshold triggers a DB insert."""
    _use_tmp_db(tmp_path, monkeypatch)

    conf_threshold = 0.50
    monkeypatch.setattr(pipeline, "WEAPON_DETECT_CONFIDENCE", conf_threshold)
    monkeypatch.setattr(pipeline, "WEAPON_SCAN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(pipeline, "ENABLE_WEAPON_DETECT", True)

    import numpy as np
    fake_box = MagicMock()
    fake_box.__len__ = MagicMock(return_value=1)
    fake_box.conf = [0.87]   # above threshold
    fake_box.cls = [0]
    fake_box.xyxy = [np.array([50, 50, 200, 200])]

    fake_result = MagicMock()
    fake_result.boxes = fake_box
    fake_result.names = {0: "pistol"}

    mock_detector = MagicMock(return_value=[fake_result])

    import threading, concurrent.futures
    vp = pipeline.VideoPipeline.__new__(pipeline.VideoPipeline)
    vp.camera_id = "cam_test"
    vp.weapon_detector = mock_detector
    vp.last_weapon_scan = 0.0
    vp.weapon_flash_until = 0.0
    vp._last_weapon_boxes = []
    vp.state_lock = threading.RLock()
    vp.db_executor = concurrent.futures.ThreadPoolExecutor(1)
    vp.pending_db_futures = set()

    frame = np.zeros((480, 640, 3), dtype="uint8")
    state: dict = {"weapon_alert_count": 0}

    vp._run_weapon_inference(frame, state)
    # Wait for DB writes to flush
    vp.db_executor.shutdown(wait=True)

    events = database.get_weapon_events()
    assert len(events) >= 1
    assert events[0]["weapon_type"] == "PISTOL"
    assert events[0]["confidence"] >= 0.85
    assert state["weapon_alert_count"] == 1


# ---------------------------------------------------------------------------
# STEP 4: Acknowledge endpoint flips acknowledged flag
# ---------------------------------------------------------------------------

def test_weapon_acknowledge(monkeypatch, tmp_path):
    """acknowledge_weapon_event sets acknowledged=1 in DB."""
    _use_tmp_db(tmp_path, monkeypatch)

    database.insert_weapon_event("cam_x", "PISTOL", 0.91, "10,10,100,100", None)
    events = database.get_weapon_events()
    assert len(events) == 1
    event_id = events[0]["id"]
    assert events[0]["acknowledged"] == 0

    result = database.acknowledge_weapon_event(event_id)
    assert result is True

    updated = database.get_weapon_events()
    assert updated[0]["acknowledged"] == 1
    assert updated[0]["acknowledged_at"] is not None


# ---------------------------------------------------------------------------
# STEP 5: Summary endpoint returns correct counts
# ---------------------------------------------------------------------------

def test_weapon_summary(monkeypatch, tmp_path):
    """get_weapon_summary returns correct totals and breakdown."""
    _use_tmp_db(tmp_path, monkeypatch)

    database.insert_weapon_event("cam_a", "PISTOL", 0.88, None, None)
    database.insert_weapon_event("cam_a", "PISTOL", 0.92, None, None)
    database.insert_weapon_event("cam_a", "RIFLE", 0.75, None, None)

    # Acknowledge one
    events = database.get_weapon_events()
    database.acknowledge_weapon_event(events[0]["id"])

    summary = database.get_weapon_summary(camera_id="cam_a")

    assert summary["total_weapon_events"] == 3
    assert summary["unacknowledged_count"] == 2
    assert summary["weapon_breakdown"]["PISTOL"] == 2
    assert summary["weapon_breakdown"]["RIFLE"] == 1


def test_weapon_summary_all_cameras(monkeypatch, tmp_path):
    """get_weapon_summary without camera_id aggregates across all cameras."""
    _use_tmp_db(tmp_path, monkeypatch)

    database.insert_weapon_event("cam_a", "PISTOL", 0.90, None, None)
    database.insert_weapon_event("cam_b", "KNIFE", 0.65, None, None)

    summary = database.get_weapon_summary()
    assert summary["total_weapon_events"] == 2
