from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "analytics.db"
DB_RETRY_ATTEMPTS = 3
DB_RETRY_BACKOFF_SECONDS = 0.2


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _get_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _run_write(action, label: str) -> bool:
    for attempt in range(DB_RETRY_ATTEMPTS):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            action(conn)
            conn.commit()
            return True
        except sqlite3.OperationalError as exc:
            locked = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if conn is not None:
                conn.close()
                conn = None
            if locked and attempt + 1 < DB_RETRY_ATTEMPTS:
                time.sleep(DB_RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue
            print(f"DB Error ({label}): {exc}")
            return False
        except Exception as exc:
            print(f"DB Error ({label}): {exc}")
            return False
        finally:
            if conn is not None:
                conn.close()
    return False


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL DEFAULT 'camera_1',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                detail TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL DEFAULT 'camera_1',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                vehicle_count INTEGER,
                people_count INTEGER,
                zone_count INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vehicle_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                tracker_id INTEGER NOT NULL,
                vehicle_type TEXT NOT NULL,
                plate_text TEXT,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, tracker_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plate_reads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                tracker_id INTEGER,
                plate_text TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                confidence REAL,
                ocr_source TEXT NOT NULL DEFAULT 'unknown',
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, plate_text)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS face_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                tracker_id INTEGER NOT NULL,
                identity TEXT,
                gender TEXT,
                age INTEGER,
                watchlist_hit INTEGER NOT NULL DEFAULT 0,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, tracker_id)
            )
            """
        )

        event_columns = _get_columns(conn, "events")
        if "camera_id" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN camera_id TEXT NOT NULL DEFAULT 'camera_1'")
        if "detail" not in event_columns:
            conn.execute("ALTER TABLE events ADD COLUMN detail TEXT")
            if "details" in event_columns:
                conn.execute("UPDATE events SET detail = details WHERE detail IS NULL OR detail = ''")

        metric_columns = _get_columns(conn, "metrics")
        if "camera_id" not in metric_columns:
            conn.execute("ALTER TABLE metrics ADD COLUMN camera_id TEXT NOT NULL DEFAULT 'camera_1'")

        plate_columns = _get_columns(conn, "plate_reads")
        if "ocr_source" not in plate_columns:
            conn.execute("ALTER TABLE plate_reads ADD COLUMN ocr_source TEXT NOT NULL DEFAULT 'unknown'")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_camera_timestamp ON events(camera_id, timestamp DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plate_reads_plate ON plate_reads(plate_text)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_face_records_identity ON face_records(identity)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vehicle_records_camera_tracker ON vehicle_records(camera_id, tracker_id)"
        )
        conn.commit()
    finally:
        conn.close()


def log_event(camera_id: str, event_type: str, detail: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def action(conn: sqlite3.Connection) -> None:
        event_columns = _get_columns(conn, "events")
        if "details" in event_columns:
            conn.execute(
                """
                INSERT INTO events (camera_id, timestamp, event_type, detail, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (camera_id, timestamp, event_type, detail, detail),
            )
        else:
            conn.execute(
                "INSERT INTO events (camera_id, timestamp, event_type, detail) VALUES (?, ?, ?, ?)",
                (camera_id, timestamp, event_type, detail),
            )

    _run_write(action, "log_event")


def store_metric(camera_id: str, vehicle_count: int, people_count: int, zone_count: int) -> None:
    def action(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO metrics (camera_id, vehicle_count, people_count, zone_count)
            VALUES (?, ?, ?, ?)
            """,
            (camera_id, vehicle_count, people_count, zone_count),
        )

    _run_write(action, "store_metric")


def upsert_vehicle_record(
    camera_id: str,
    tracker_id: int,
    vehicle_type: str,
    plate_text: Optional[str] = None,
) -> None:
    def action(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO vehicle_records (camera_id, tracker_id, vehicle_type, plate_text)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(camera_id, tracker_id) DO UPDATE SET
                vehicle_type = excluded.vehicle_type,
                plate_text = COALESCE(excluded.plate_text, vehicle_records.plate_text),
                last_seen = CURRENT_TIMESTAMP
            """,
            (camera_id, tracker_id, vehicle_type, plate_text),
        )

    _run_write(action, "upsert_vehicle_record")


def upsert_plate_read(
    camera_id: str,
    tracker_id: Optional[int],
    plate_text: str,
    vehicle_type: str,
    confidence: Optional[float],
    ocr_source: str = "unknown",
) -> None:
    def action(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO plate_reads (camera_id, tracker_id, plate_text, vehicle_type, confidence, ocr_source)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(camera_id, plate_text) DO UPDATE SET
                tracker_id = COALESCE(excluded.tracker_id, plate_reads.tracker_id),
                vehicle_type = excluded.vehicle_type,
                confidence = COALESCE(excluded.confidence, plate_reads.confidence),
                ocr_source = COALESCE(excluded.ocr_source, plate_reads.ocr_source),
                last_seen = CURRENT_TIMESTAMP
            """,
            (camera_id, tracker_id, plate_text, vehicle_type, confidence, ocr_source),
        )

    _run_write(action, "upsert_plate_read")


def upsert_face_record(
    camera_id: str,
    tracker_id: int,
    identity: Optional[str],
    gender: Optional[str],
    age: Optional[int],
    watchlist_hit: bool,
) -> None:
    def action(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO face_records (camera_id, tracker_id, identity, gender, age, watchlist_hit)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(camera_id, tracker_id) DO UPDATE SET
                identity = COALESCE(excluded.identity, face_records.identity),
                gender = COALESCE(excluded.gender, face_records.gender),
                age = COALESCE(excluded.age, face_records.age),
                watchlist_hit = excluded.watchlist_hit,
                last_seen = CURRENT_TIMESTAMP
            """,
            (camera_id, tracker_id, identity, gender, age, int(watchlist_hit)),
        )

    _run_write(action, "upsert_face_record")


def _build_filter_clause(camera_id: Optional[str], query: Optional[str]) -> tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if camera_id:
        clauses.append("camera_id = ?")
        params.append(camera_id)

    if query:
        clauses.append("(detail LIKE ? OR event_type LIKE ?)")
        like_query = f"%{query}%"
        params.extend([like_query, like_query])

    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def get_recent_events(
    limit: int = 50,
    query: Optional[str] = None,
    camera_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        where_clause, params = _build_filter_clause(camera_id, query)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT camera_id, timestamp, event_type AS type, detail
            FROM events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"DB Error: {exc}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_plate_reads(
    limit: int = 50,
    query: Optional[str] = None,
    camera_id: Optional[str] = None,
    min_confidence: Optional[float] = None,
    ocr_source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        clauses: List[str] = []
        params: List[Any] = []

        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)

        if query:
            clauses.append("(plate_text LIKE ? OR vehicle_type LIKE ?)")
            like_query = f"%{query}%"
            params.extend([like_query, like_query])

        if min_confidence is not None:
            clauses.append("confidence >= ?")
            params.append(float(min_confidence))

        if ocr_source:
            clauses.append("LOWER(COALESCE(ocr_source, 'unknown')) = ?")
            params.append(ocr_source.strip().lower())

        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT camera_id, tracker_id, plate_text, vehicle_type, confidence, ocr_source, first_seen, last_seen
            FROM plate_reads
            {where_clause}
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"DB Error: {exc}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_vehicle_records(
    limit: int = 50,
    query: Optional[str] = None,
    camera_id: Optional[str] = None,
    require_plate: bool = False,
) -> List[Dict[str, Any]]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        clauses: List[str] = []
        params: List[Any] = []

        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)

        if query:
            clauses.append("(vehicle_type LIKE ? OR COALESCE(plate_text, '') LIKE ? OR CAST(tracker_id AS TEXT) LIKE ?)")
            like_query = f"%{query}%"
            params.extend([like_query, like_query, like_query])

        if require_plate:
            clauses.append("COALESCE(plate_text, '') != ''")

        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT camera_id, tracker_id, vehicle_type, plate_text, first_seen, last_seen
            FROM vehicle_records
            {where_clause}
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"DB Error: {exc}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_face_records(
    limit: int = 50,
    query: Optional[str] = None,
    camera_id: Optional[str] = None,
    watchlist_only: bool = False,
) -> List[Dict[str, Any]]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        clauses: List[str] = []
        params: List[Any] = []

        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)

        if query:
            clauses.append("(COALESCE(identity, '') LIKE ? OR COALESCE(gender, '') LIKE ?)")
            like_query = f"%{query}%"
            params.extend([like_query, like_query])

        if watchlist_only:
            clauses.append("watchlist_hit = 1")

        where_clause = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT camera_id, tracker_id, identity, gender, age, watchlist_hit, first_seen, last_seen
            FROM face_records
            {where_clause}
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"DB Error: {exc}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_metric_history(
    limit: int = 120,
    camera_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        params: List[Any] = []
        where_clause = ""
        if camera_id:
            where_clause = " WHERE camera_id = ?"
            params.append(camera_id)
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT camera_id, timestamp, vehicle_count, people_count, zone_count
            FROM metrics
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        history = [dict(row) for row in rows]
        history.reverse()
        return history
    except Exception as exc:
        print(f"DB Error: {exc}")
        return []
    finally:
        if conn is not None:
            conn.close()


def get_traffic_analytics(camera_id: Optional[str] = None) -> Dict[str, Any]:
    history = get_metric_history(limit=720, camera_id=camera_id)
    if not history:
        return {
            "peak_vehicle_count": 0,
            "average_vehicle_count": 0.0,
            "average_people_count": 0.0,
            "peak_zone_count": 0,
            "peak_timestamp": None,
            "hourly_vehicle_flow": [],
        }

    peak_row = max(history, key=lambda row: int(row.get("vehicle_count") or 0))
    average_vehicle = sum(int(row.get("vehicle_count") or 0) for row in history) / len(history)
    average_people = sum(int(row.get("people_count") or 0) for row in history) / len(history)
    peak_zone = max(int(row.get("zone_count") or 0) for row in history)

    hourly_buckets: Dict[str, int] = {}
    for row in history:
        timestamp = str(row.get("timestamp") or "")
        hour_key = timestamp[:13] + ":00:00" if len(timestamp) >= 13 else timestamp
        hourly_buckets[hour_key] = max(hourly_buckets.get(hour_key, 0), int(row.get("vehicle_count") or 0))

    return {
        "peak_vehicle_count": int(peak_row.get("vehicle_count") or 0),
        "average_vehicle_count": round(average_vehicle, 2),
        "average_people_count": round(average_people, 2),
        "peak_zone_count": peak_zone,
        "peak_timestamp": peak_row.get("timestamp"),
        "hourly_vehicle_flow": [
            {"timestamp": timestamp, "vehicle_count": count}
            for timestamp, count in sorted(hourly_buckets.items())
        ],
    }


def get_ocr_analytics(camera_id: Optional[str] = None) -> Dict[str, Any]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        where_clause = ""
        params: List[Any] = []
        if camera_id:
            where_clause = " WHERE camera_id = ?"
            params.append(camera_id)

        totals_row = conn.execute(
            f"""
            SELECT COUNT(*) AS total_reads, AVG(confidence) AS average_confidence
            FROM plate_reads
            {where_clause}
            """,
            params,
        ).fetchone()

        source_rows = conn.execute(
            f"""
            SELECT
                COALESCE(ocr_source, 'unknown') AS ocr_source,
                COUNT(*) AS reads,
                AVG(confidence) AS average_confidence
            FROM plate_reads
            {where_clause}
            GROUP BY COALESCE(ocr_source, 'unknown')
            ORDER BY reads DESC, ocr_source ASC
            """,
            params,
        ).fetchall()

        total_reads = int((totals_row["total_reads"] if totals_row else 0) or 0)
        sources: List[Dict[str, Any]] = []
        for row in source_rows:
            reads = int(row["reads"] or 0)
            sources.append(
                {
                    "ocr_source": row["ocr_source"],
                    "reads": reads,
                    "share_percent": round((reads / max(total_reads, 1)) * 100.0, 2),
                    "average_confidence": round(float(row["average_confidence"] or 0.0), 3),
                }
            )

        return {
            "total_reads": total_reads,
            "average_confidence": round(float((totals_row["average_confidence"] if totals_row else 0.0) or 0.0), 3),
            "sources": sources,
        }
    except Exception as exc:
        print(f"DB Error: {exc}")
        return {"total_reads": 0, "average_confidence": 0.0, "sources": []}
    finally:
        if conn is not None:
            conn.close()


init_db()
