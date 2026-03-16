from pathlib import Path

import database


def test_database_records_are_searchable(tmp_path):
    db_path = tmp_path / "analytics_test.db"
    original_path = database.DB_PATH

    try:
        database.DB_PATH = db_path
        database.init_db()

        database.log_event("cam_a", "ANPR Match", "Plate ABC123 detected")
        database.log_event("cam_b", "Face Analytics", "Face analytics completed")
        database.upsert_vehicle_record("cam_a", 7, "car", "ABC123")
        database.upsert_plate_read("cam_a", 7, "ABC123", "car", 0.91, "paddle")
        database.upsert_face_record("cam_a", 11, "alice", "Woman", None, True)

        events = database.get_recent_events(camera_id="cam_a")
        vehicles = database.get_vehicle_records(query="ABC", camera_id="cam_a")
        plates = database.get_plate_reads(query="ABC", camera_id="cam_a")
        faces = database.get_face_records(query="alice", camera_id="cam_a")

        assert len(events) == 1
        assert events[0]["camera_id"] == "cam_a"
        assert vehicles[0]["plate_text"] == "ABC123"
        assert plates[0]["plate_text"] == "ABC123"
        assert plates[0]["ocr_source"] == "paddle"
        assert faces[0]["identity"] == "alice"
        assert faces[0]["watchlist_hit"] == 1
    finally:
        database.DB_PATH = original_path


def test_database_upserts_update_existing_records(tmp_path):
    db_path = tmp_path / "analytics_upsert.db"
    original_path = database.DB_PATH

    try:
        database.DB_PATH = db_path
        database.init_db()

        database.upsert_plate_read("cam_a", 1, "XYZ999", "car", 0.55)
        database.upsert_plate_read("cam_a", 9, "XYZ999", "truck", 0.88, "cloud")

        records = database.get_plate_reads(camera_id="cam_a")
        assert len(records) == 1
        assert records[0]["tracker_id"] == 9
        assert records[0]["vehicle_type"] == "truck"
        assert records[0]["ocr_source"] == "cloud"
    finally:
        database.DB_PATH = original_path


def test_legacy_event_schema_is_still_writable(tmp_path):
    db_path = tmp_path / "legacy.db"
    original_path = database.DB_PATH

    try:
        database.DB_PATH = db_path
        conn = database._connect()
        conn.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT NOT NULL,
                camera_id TEXT NOT NULL DEFAULT 'camera_1'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                vehicle_count INTEGER,
                people_count INTEGER,
                zone_count INTEGER
            )
            """
        )
        conn.commit()
        conn.close()

        database.init_db()
        database.log_event("cam_legacy", "Face Analytics", "Legacy schema write works")

        events = database.get_recent_events(camera_id="cam_legacy")
        assert len(events) == 1
        assert events[0]["detail"] == "Legacy schema write works"
    finally:
        database.DB_PATH = original_path


def test_ocr_analytics_groups_by_source(tmp_path):
    db_path = tmp_path / "ocr_analytics.db"
    original_path = database.DB_PATH

    try:
        database.DB_PATH = db_path
        database.init_db()

        database.upsert_plate_read("cam_x", 1, "MH12AB1234", "car", 0.91, "paddle")
        database.upsert_plate_read("cam_x", 2, "MH14XY4321", "truck", 0.71, "easyocr")
        database.upsert_plate_read("cam_x", 3, "DL05CA7777", "car", 0.64, "cloud")

        analytics = database.get_ocr_analytics(camera_id="cam_x")

        assert analytics["total_reads"] == 3
        assert len(analytics["sources"]) == 3
        sources = {item["ocr_source"] for item in analytics["sources"]}
        assert sources == {"paddle", "easyocr", "cloud"}
    finally:
        database.DB_PATH = original_path


def test_plate_record_filters_confidence_and_source(tmp_path):
    db_path = tmp_path / "plate_filters.db"
    original_path = database.DB_PATH

    try:
        database.DB_PATH = db_path
        database.init_db()

        database.upsert_plate_read("cam_f", 1, "MH12AB1234", "car", 0.91, "paddle")
        database.upsert_plate_read("cam_f", 2, "MH14XY4321", "truck", 0.62, "easyocr")

        high_conf = database.get_plate_reads(camera_id="cam_f", min_confidence=0.8)
        paddle_only = database.get_plate_reads(camera_id="cam_f", ocr_source="paddle")

        assert len(high_conf) == 1
        assert high_conf[0]["plate_text"] == "MH12AB1234"
        assert len(paddle_only) == 1
        assert paddle_only[0]["ocr_source"] == "paddle"
    finally:
        database.DB_PATH = original_path


def test_face_and_vehicle_filters(tmp_path):
    db_path = tmp_path / "record_filters.db"
    original_path = database.DB_PATH

    try:
        database.DB_PATH = db_path
        database.init_db()

        database.upsert_face_record("cam_v", 11, "alice", "Woman", 28, True)
        database.upsert_face_record("cam_v", 12, None, "Man", 32, False)

        database.upsert_vehicle_record("cam_v", 21, "car", "MH12AB1234")
        database.upsert_vehicle_record("cam_v", 22, "truck", None)

        watchlist_only = database.get_face_records(camera_id="cam_v", watchlist_only=True)
        plated_only = database.get_vehicle_records(camera_id="cam_v", require_plate=True)

        assert len(watchlist_only) == 1
        assert watchlist_only[0]["watchlist_hit"] == 1
        assert len(plated_only) == 1
        assert plated_only[0]["plate_text"] == "MH12AB1234"
    finally:
        database.DB_PATH = original_path


# ---------------------------------------------------------------------------
# Weapon events
# ---------------------------------------------------------------------------

def test_insert_weapon_event_persists(tmp_path):
    db_path = tmp_path / "weapon_db.db"
    original_path = database.DB_PATH
    try:
        database.DB_PATH = db_path
        database.init_db()

        database.insert_weapon_event("cam_w", "PISTOL", 0.90, "10,20,100,150", None)
        events = database.get_weapon_events()

        assert len(events) == 1
        assert events[0]["camera_id"] == "cam_w"
        assert events[0]["weapon_type"] == "PISTOL"
        assert abs(events[0]["confidence"] - 0.90) < 0.001
        assert events[0]["bounding_box"] == "10,20,100,150"
        assert events[0]["acknowledged"] == 0
    finally:
        database.DB_PATH = original_path


def test_get_weapon_events_filter_unacknowledged(tmp_path):
    db_path = tmp_path / "weapon_ack.db"
    original_path = database.DB_PATH
    try:
        database.DB_PATH = db_path
        database.init_db()

        database.insert_weapon_event("cam_w", "PISTOL", 0.88, None, None)
        database.insert_weapon_event("cam_w", "RIFLE", 0.76, None, None)

        all_events = database.get_weapon_events(camera_id="cam_w")
        assert len(all_events) == 2

        # Acknowledge the first one
        database.acknowledge_weapon_event(all_events[0]["id"])

        unacked = database.get_weapon_events(camera_id="cam_w", unacknowledged_only=True)
        assert len(unacked) == 1
        assert unacked[0]["acknowledged"] == 0
    finally:
        database.DB_PATH = original_path


def test_acknowledge_weapon_event(tmp_path):
    db_path = tmp_path / "weapon_ack2.db"
    original_path = database.DB_PATH
    try:
        database.DB_PATH = db_path
        database.init_db()

        database.insert_weapon_event("cam_w", "KNIFE", 0.72, None, None)
        events = database.get_weapon_events()
        event_id = events[0]["id"]

        # Initially unacknowledged
        assert events[0]["acknowledged"] == 0
        assert events[0]["acknowledged_at"] is None

        result = database.acknowledge_weapon_event(event_id)
        assert result is True

        updated = database.get_weapon_events()
        assert updated[0]["acknowledged"] == 1
        assert updated[0]["acknowledged_at"] is not None
    finally:
        database.DB_PATH = original_path


def test_get_weapon_summary_counts(tmp_path):
    db_path = tmp_path / "weapon_summary.db"
    original_path = database.DB_PATH
    try:
        database.DB_PATH = db_path
        database.init_db()

        database.insert_weapon_event("cam_a", "PISTOL", 0.91, None, None)
        database.insert_weapon_event("cam_a", "PISTOL", 0.85, None, None)
        database.insert_weapon_event("cam_b", "RIFLE", 0.78, None, None)

        # Acknowledge one PISTOL
        events = database.get_weapon_events(camera_id="cam_a")
        database.acknowledge_weapon_event(events[0]["id"])

        summary_a = database.get_weapon_summary(camera_id="cam_a")
        assert summary_a["total_weapon_events"] == 2
        assert summary_a["unacknowledged_count"] == 1
        assert summary_a["weapon_breakdown"]["PISTOL"] == 2

        summary_all = database.get_weapon_summary()
        assert summary_all["total_weapon_events"] == 3
        assert "RIFLE" in summary_all["weapon_breakdown"]
    finally:
        database.DB_PATH = original_path
