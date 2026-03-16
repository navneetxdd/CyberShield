"""
Vehicle Intelligence Module – Test Suite
=========================================
Tests are grouped by pipeline stage.  All tests use a temporary SQLite
database so they never touch the production analytics.db.

Test categories
---------------
Stage 0  – Config / helpers
Stage 1  – ANPR plate normalisation
Stage 2  – Database schema initialisation
Stage 3  – VehicleStore CRUD
Stage 4  – HistoryLogger events
Stage 5  – PlateWatchlist management
Stage 6  – VehicleAnalytics aggregation
Stage 7  – VehicleIntelligencePipeline (process_plates, integration)
Stage 8  – vi_api router (HTTP layer)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Make the app directory importable without installing
# ---------------------------------------------------------------------------
import sys

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))


# ---------------------------------------------------------------------------
# Shared fixture: in-memory SQLite DB path
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    """
    Redirect all VI DB operations to a fresh temporary database.
    Patches VI_DB_PATH in every submodule that uses it.
    """
    db_file = tmp_path / "test_vi.db"

    import vehicle_intelligence.config       as cfg
    import vehicle_intelligence.db_schema    as ds
    import vehicle_intelligence.vehicle_store as vs
    import vehicle_intelligence.history      as hs
    import vehicle_intelligence.watchlist    as wl
    import vehicle_intelligence.analytics    as an

    for module in (cfg, ds, vs, hs, wl, an):
        monkeypatch.setattr(module, "VI_DB_PATH", db_file)

    # Initialise schema in the temp DB
    ds.vi_init_db()
    return db_file


# ===========================================================================
# Stage 0 – Config helpers
# ===========================================================================

class TestConfig:
    def test_plate_pattern_accepts_valid_plate(self):
        from vehicle_intelligence.config import PLATE_TEXT_PATTERN
        assert PLATE_TEXT_PATTERN.match("MH12AB1234")

    def test_plate_pattern_accepts_short_number(self):
        from vehicle_intelligence.config import PLATE_TEXT_PATTERN
        assert PLATE_TEXT_PATTERN.match("KA1AB1234")

    def test_plate_pattern_rejects_too_short(self):
        from vehicle_intelligence.config import PLATE_TEXT_PATTERN
        assert PLATE_TEXT_PATTERN.match("AB12") is None

    def test_plate_pattern_rejects_letters_only(self):
        from vehicle_intelligence.config import PLATE_TEXT_PATTERN
        assert PLATE_TEXT_PATTERN.match("ABCDEFGH") is None

    def test_read_env_float_returns_default(self, monkeypatch):
        monkeypatch.delenv("VI_DETECT_CONFIDENCE", raising=False)
        from vehicle_intelligence.config import _read_env_float
        assert _read_env_float("VI_DETECT_CONFIDENCE", 0.30) == 0.30

    def test_read_env_float_respects_min(self, monkeypatch):
        monkeypatch.setenv("VI_DETECT_CONFIDENCE", "0.01")
        from vehicle_intelligence.config import _read_env_float
        assert _read_env_float("VI_DETECT_CONFIDENCE", 0.30, minimum=0.05) == 0.05

    def test_read_env_int_ignores_invalid(self, monkeypatch):
        monkeypatch.setenv("VI_FREQUENT_THRESHOLD", "not_a_number")
        from vehicle_intelligence.config import _read_env_int
        assert _read_env_int("VI_FREQUENT_THRESHOLD", 3) == 3


# ===========================================================================
# Stage 1 – ANPR normalisation
# ===========================================================================

class TestPlateNormalisation:
    def test_strips_spaces(self):
        from vehicle_intelligence.anpr import normalize_plate_text
        assert normalize_plate_text("MH 12 AB 1234") == "MH12AB1234"

    def test_strips_dashes(self):
        from vehicle_intelligence.anpr import normalize_plate_text
        assert normalize_plate_text("DL-4C-AF-3456") == "DL4CAF3456"

    def test_upper_cases(self):
        from vehicle_intelligence.anpr import normalize_plate_text
        assert normalize_plate_text("ka01ab1234") == "KA01AB1234"

    def test_rejects_invalid(self):
        from vehicle_intelligence.anpr import normalize_plate_text
        assert normalize_plate_text("ABCDEFGH") is None
        assert normalize_plate_text("12345678") is None
        assert normalize_plate_text("AB-1") is None
        assert normalize_plate_text("") is None

    def test_accepts_numeric_only_suffix(self):
        from vehicle_intelligence.anpr import normalize_plate_text
        # "MH12" + 3 digits – no alpha group
        result = normalize_plate_text("MH12123")
        # Pattern: ^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4}$
        # MH12 matches [A-Z]{2}[0-9]{1,2}, no [A-Z], 123 is 3 digits → valid
        assert result == "MH12123"


# ===========================================================================
# Stage 2 – Database schema
# ===========================================================================

class TestDBSchema:
    def test_tables_created(self, tmp_db: Path):
        conn = sqlite3.connect(str(tmp_db))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "vi_vehicles"        in tables
        assert "vi_vehicle_history" in tables
        assert "vi_watchlist"       in tables
        assert "vi_alerts"          in tables

    def test_init_is_idempotent(self, tmp_db: Path):
        """Calling vi_init_db() twice must not raise."""
        from vehicle_intelligence.db_schema import vi_init_db
        vi_init_db()   # second call
        vi_init_db()   # third call – should still be fine

    def test_indexes_created(self, tmp_db: Path):
        conn = sqlite3.connect(str(tmp_db))
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        conn.close()
        assert "idx_vi_history_plate" in indexes
        assert "idx_vi_alerts_ts"     in indexes
        assert "idx_vi_watchlist_active" in indexes


# ===========================================================================
# Stage 3 – VehicleStore CRUD
# ===========================================================================

class TestVehicleStore:
    def test_lookup_returns_none_for_unknown(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        assert store.lookup("MH12AB1234") is None

    def test_upsert_creates_record(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store  = SQLiteVehicleStore()
        record = store.upsert("MH12AB1234", "car", "cam_01")
        assert record["plate_text"] == "MH12AB1234"
        assert record["vehicle_type"] == "car"
        assert record["is_new"] is True

    def test_upsert_increments_detections(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        store.upsert("KA01AB1234", "truck", "cam_01")
        store.upsert("KA01AB1234", "truck", "cam_01")
        record = store.lookup("KA01AB1234")
        assert record is not None
        assert record["total_detections"] == 2

    def test_upsert_second_call_is_not_new(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        store.upsert("DL4CAF3456", "car", "cam_01")
        record = store.upsert("DL4CAF3456", "car", "cam_01")
        assert record["is_new"] is False

    def test_list_vehicles_returns_all(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        store.upsert("MH12AB1234", "car",   "cam_01")
        store.upsert("KA01AB1234", "truck", "cam_01")
        rows = store.list_vehicles(limit=10)
        assert len(rows) == 2

    def test_list_vehicles_search(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        store.upsert("MH12AB1234", "car",   "cam_01")
        store.upsert("KA01AB1234", "truck", "cam_01")
        rows = store.list_vehicles(search="KA01")
        assert len(rows) == 1
        assert rows[0]["plate_text"] == "KA01AB1234"

    def test_count_reflects_inserts(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        assert store.count() == 0
        store.upsert("MH12AB1234", "car", "cam_01")
        assert store.count() == 1

    def test_frequent_vehicles_threshold(self, tmp_db: Path):
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        for _ in range(5):
            store.upsert("MH12AB1234", "car", "cam_01")
        store.upsert("KA01AB9999", "bus", "cam_01")
        frequent = store.get_frequent_vehicles(min_detections=3)
        assert len(frequent) == 1
        assert frequent[0]["plate_text"] == "MH12AB1234"


# ===========================================================================
# Stage 4 – HistoryLogger
# ===========================================================================

class TestHistoryLogger:
    def test_first_event_is_entry(self, tmp_db: Path):
        from vehicle_intelligence.history import HistoryLogger
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        SQLiteVehicleStore().upsert("MH12AB1234", "car", "cam_01")
        logger     = HistoryLogger(entry_cooldown=0)   # 0s cooldown → always entry
        event_type = logger.log_detection("MH12AB1234", "cam_01")
        assert event_type == "entry"

    def test_second_event_within_cooldown_is_detection(self, tmp_db: Path):
        from vehicle_intelligence.history import HistoryLogger
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        SQLiteVehicleStore().upsert("MH12AB1234", "car", "cam_01")
        logger = HistoryLogger(entry_cooldown=300)
        logger.log_detection("MH12AB1234", "cam_01")
        event_type = logger.log_detection("MH12AB1234", "cam_01")
        assert event_type == "detection"

    def test_exit_clears_cache_for_next_entry(self, tmp_db: Path):
        from vehicle_intelligence.history import HistoryLogger
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        SQLiteVehicleStore().upsert("MH12AB1234", "car", "cam_01")
        logger = HistoryLogger(entry_cooldown=300)
        logger.log_detection("MH12AB1234", "cam_01")
        logger.log_exit("MH12AB1234", "cam_01")
        event_type = logger.log_detection("MH12AB1234", "cam_01")
        assert event_type == "entry"

    def test_get_recent_returns_rows(self, tmp_db: Path):
        from vehicle_intelligence.history import HistoryLogger
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        SQLiteVehicleStore().upsert("MH12AB1234", "car", "cam_01")
        logger = HistoryLogger(entry_cooldown=0)
        logger.log_detection("MH12AB1234", "cam_01")
        rows = logger.get_recent(limit=10)
        assert len(rows) >= 1
        assert rows[0]["plate_text"] == "MH12AB1234"

    def test_get_vehicle_history_filters_by_plate(self, tmp_db: Path):
        from vehicle_intelligence.history import HistoryLogger
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        SQLiteVehicleStore().upsert("MH12AB1234", "car", "cam_01")
        SQLiteVehicleStore().upsert("DL4CAF3456", "bus", "cam_01")
        logger = HistoryLogger(entry_cooldown=0)
        logger.log_detection("MH12AB1234", "cam_01")
        logger.log_detection("DL4CAF3456", "cam_01")
        rows = logger.get_vehicle_history("MH12AB1234")
        assert all(r["plate_text"] == "MH12AB1234" for r in rows)


# ===========================================================================
# Stage 5 – PlateWatchlist
# ===========================================================================

class TestPlateWatchlist:
    def test_add_and_check_hit(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl  = PlateWatchlist(cache_ttl=0)   # force refresh every check
        wl.add("MH12AB1234", reason="Stolen", priority=3)
        hit = wl.check("MH12AB1234", camera_id="cam_01")
        assert hit is not None
        assert hit.plate_text == "MH12AB1234"
        assert hit.priority   == 3

    def test_unknown_plate_returns_none(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl  = PlateWatchlist(cache_ttl=0)
        hit = wl.check("DL4CAF0000", camera_id="cam_01")
        assert hit is None

    def test_remove_deactivates_entry(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", reason="Test")
        wl.remove("MH12AB1234")
        hit = wl.check("MH12AB1234", camera_id="cam_01")
        assert hit is None

    def test_list_entries_returns_active_only_by_default(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", reason="Active")
        wl.add("DL4CAF3456", reason="Removed")
        wl.remove("DL4CAF3456")
        entries = wl.list_entries()
        assert len(entries) == 1
        assert entries[0]["plate_text"] == "MH12AB1234"

    def test_check_writes_alert(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", reason="Test alert")
        wl.check("MH12AB1234", camera_id="cam_01")
        alerts = wl.get_alerts(limit=10)
        assert any(a["plate_text"] == "MH12AB1234" for a in alerts)

    def test_acknowledge_alert(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", reason="Test")
        hit = wl.check("MH12AB1234", camera_id="cam_01")
        assert hit is not None and hit.alert_id is not None
        ok = wl.acknowledge_alert(hit.alert_id)
        assert ok is True
        unack = wl.count_unacknowledged()
        assert unack == 0

    def test_is_listed_in_memory(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234")
        assert wl.is_listed("MH12AB1234") is True
        assert wl.is_listed("ZZ99ZZ9999") is False

    def test_add_updates_existing_entry(self, tmp_db: Path):
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", reason="Old reason", priority=1)
        wl.add("MH12AB1234", reason="New reason", priority=3)
        entries = wl.list_entries()
        assert len(entries) == 1
        assert entries[0]["reason"]   == "New reason"
        assert entries[0]["priority"] == 3


# ===========================================================================
# Stage 6 – VehicleAnalytics
# ===========================================================================

class TestVehicleAnalytics:
    def _populate(self, tmp_db: Path) -> None:
        """Insert sample data for analytics queries."""
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        from vehicle_intelligence.history import HistoryLogger
        from vehicle_intelligence.watchlist import PlateWatchlist

        store  = SQLiteVehicleStore()
        logger = HistoryLogger(entry_cooldown=0)
        wl     = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", priority=3)

        for plate in ("MH12AB1234", "KA01AB1234", "DL4CAF3456"):
            store.upsert(plate, "car", "cam_01")
            logger.log_detection(plate, "cam_01", vehicle_type="car")

        wl.check("MH12AB1234", camera_id="cam_01")

    def test_summary_total_vehicles(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        summary = VehicleAnalytics().summary()
        assert summary["total_vehicles"] >= 3

    def test_summary_watchlist_size(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        summary = VehicleAnalytics().summary()
        assert summary["watchlist_size"] == 1

    def test_summary_unacknowledged_alerts(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        summary = VehicleAnalytics().summary()
        assert summary["unacknowledged_alerts"] >= 1

    def test_type_breakdown_returns_car(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        breakdown = VehicleAnalytics().type_breakdown(lookback_hours=720)
        assert "car" in breakdown
        assert breakdown["car"] >= 3

    def test_frequent_vehicles_threshold(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        from vehicle_intelligence.vehicle_store import SQLiteVehicleStore
        store = SQLiteVehicleStore()
        for _ in range(5):
            store.upsert("MH12AB1234", "car", "cam_01")
        result = VehicleAnalytics().frequent_vehicles(min_detections=4)
        assert any(r["plate_text"] == "MH12AB1234" for r in result)

    def test_recent_activity_order(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        rows = VehicleAnalytics().recent_activity(limit=10)
        # Most recent first
        if len(rows) >= 2:
            assert rows[0]["timestamp"] >= rows[-1]["timestamp"]

    def test_camera_activity_groups(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        rows = VehicleAnalytics().camera_activity(lookback_hours=720)
        assert any(r["camera_id"] == "cam_01" for r in rows)

    def test_alert_summary_counts(self, tmp_db: Path):
        from vehicle_intelligence.analytics import VehicleAnalytics
        self._populate(tmp_db)
        summary = VehicleAnalytics().alert_summary(lookback_hours=720)
        assert summary["total_in_window"] >= 1
        assert "by_priority" in summary


# ===========================================================================
# Stage 7 – VehicleIntelligencePipeline (integration)
# ===========================================================================

class TestVehicleIntelligencePipeline:
    """
    Tests the pipeline in *process_plates* mode (no YOLO / GPU required).
    """

    def test_process_plates_new_vehicle(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi     = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        result = vi.process_plates([
            {"plate_text": "MH12AB1234", "vehicle_type": "car",
             "confidence": 0.9, "ocr_source": "paddle"}
        ])
        assert result.vehicle_count == 1
        assert result.detections[0].plate_text == "MH12AB1234"
        assert result.detections[0].is_new_vehicle is True
        assert "MH12AB1234" in result.new_vehicles

    def test_process_plates_second_detection_not_new(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        vi.process_plates([{"plate_text": "MH12AB1234", "vehicle_type": "car"}])
        result = vi.process_plates([{"plate_text": "MH12AB1234", "vehicle_type": "car"}])
        assert result.detections[0].is_new_vehicle is False

    def test_process_plates_watchlist_alert(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        from vehicle_intelligence.watchlist import PlateWatchlist
        wl = PlateWatchlist(cache_ttl=0)
        wl.add("MH12AB1234", reason="Stolen", priority=3)

        vi     = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        result = vi.process_plates([{"plate_text": "MH12AB1234", "vehicle_type": "car"}])
        assert len(result.watchlist_alerts) == 1
        assert result.watchlist_alerts[0].plate_text == "MH12AB1234"

    def test_process_plates_no_watchlist_hit(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi     = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        result = vi.process_plates([{"plate_text": "KA01AB9999", "vehicle_type": "bus"}])
        assert len(result.watchlist_alerts) == 0

    def test_process_plates_logs_entry_first_time(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi     = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        result = vi.process_plates([{"plate_text": "MH12AB1234", "vehicle_type": "car"}])
        assert result.detections[0].event_type == "entry"

    def test_on_track_lost_emits_exit(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        from vehicle_intelligence.history import HistoryLogger
        vi = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        vi.process_plates([
            {"plate_text": "MH12AB1234", "vehicle_type": "car",
             "tracker_id": 42}
        ])
        vi.on_track_lost(42)
        # Verify exit event in DB
        logger = HistoryLogger()
        history = logger.get_recent(event_type="exit", limit=5)
        assert any(r["plate_text"] == "MH12AB1234" for r in history)

    def test_process_plates_multiple_vehicles(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi     = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        result = vi.process_plates([
            {"plate_text": "MH12AB1234", "vehicle_type": "car"},
            {"plate_text": "DL4CAF3456", "vehicle_type": "truck"},
        ])
        assert result.vehicle_count == 2
        plates = {d.plate_text for d in result.detections}
        assert "MH12AB1234" in plates
        assert "DL4CAF3456" in plates

    def test_to_dict_serialisable(self, tmp_db: Path):
        """VIFrameResult.to_dict() must return a JSON-serialisable object."""
        import json
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi     = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        result = vi.process_plates([
            {"plate_text": "MH12AB1234", "vehicle_type": "car"}
        ])
        json.dumps(result.to_dict())   # must not raise

    def test_analytics_property_accessible(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        assert vi.analytics is not None

    def test_reset_clears_confirmed_plates(self, tmp_db: Path):
        from vehicle_intelligence.pipeline import VehicleIntelligencePipeline
        vi = VehicleIntelligencePipeline(camera_id="cam_01", enable_detection=False)
        vi.process_plates([{"plate_text": "MH12AB1234", "tracker_id": 1}])
        vi.reset()
        assert len(vi._confirmed_plates) == 0


# ===========================================================================
# Stage 8 – vi_api HTTP layer (using TestClient – no DB patch required here
#           because vi_startup() initialises _store etc.)
# ===========================================================================

class TestViAPI:
    @pytest.fixture()
    def client(self, tmp_db: Path, monkeypatch):
        """
        Create a FastAPI TestClient with VI startup pointing at the temp DB.
        """
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import vehicle_intelligence.db_schema as ds

        monkeypatch.setattr(ds, "VI_DB_PATH", tmp_db)
        import vi_api as api_module
        monkeypatch.setattr(api_module, "_ready", False)

        # Patch vi_startup to run against the temp DB
        def patched_startup():
            import vehicle_intelligence.config as cfg
            import vehicle_intelligence.vehicle_store as vs
            import vehicle_intelligence.history as hs
            import vehicle_intelligence.watchlist as wl
            import vehicle_intelligence.analytics as an
            for mod in (cfg, vs, hs, wl, an):
                monkeypatch.setattr(mod, "VI_DB_PATH", tmp_db)
            ds.vi_init_db()
            api_module._store     = vs.SQLiteVehicleStore()
            api_module._history   = hs.HistoryLogger()
            api_module._watchlist = wl.PlateWatchlist(cache_ttl=0)
            api_module._analytics = an.VehicleAnalytics()
            api_module._ready     = True

        test_app = FastAPI()
        test_app.include_router(api_module.vi_router)
        patched_startup()
        return TestClient(test_app)

    def test_health_returns_ready(self, client):
        r = client.get("/vi/health")
        assert r.status_code == 200
        assert r.json()["ready"] is True

    def test_analytics_summary(self, client):
        r = client.get("/vi/analytics/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_vehicles" in data

    def test_vehicles_empty_list(self, client):
        r = client.get("/vi/vehicles")
        assert r.status_code == 200
        assert r.json() == []

    def test_add_and_list_watchlist(self, client):
        r = client.post("/vi/watchlist", json={
            "plate_text": "MH12AB1234",
            "reason":     "Test",
            "priority":   2,
            "added_by":   "tester",
        })
        assert r.status_code == 201
        r2 = client.get("/vi/watchlist")
        assert any(e["plate_text"] == "MH12AB1234" for e in r2.json())

    def test_remove_from_watchlist(self, client):
        client.post("/vi/watchlist", json={
            "plate_text": "DL4CAF3456", "reason": "Test", "priority": 1
        })
        r = client.delete("/vi/watchlist/DL4CAF3456")
        assert r.status_code == 200
        r2 = client.get("/vi/watchlist")
        assert not any(e["plate_text"] == "DL4CAF3456" for e in r2.json())

    def test_vehicle_not_found_returns_404(self, client):
        r = client.get("/vi/vehicles/ZZZZ9999")
        assert r.status_code == 404

    def test_history_empty(self, client):
        r = client.get("/vi/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alerts_empty(self, client):
        r = client.get("/vi/alerts")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alert_count(self, client):
        r = client.get("/vi/alerts/count")
        assert r.status_code == 200
        assert "unacknowledged" in r.json()

    def test_traffic_stats(self, client):
        r = client.get("/vi/analytics/traffic")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_type_breakdown(self, client):
        r = client.get("/vi/analytics/types")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)
