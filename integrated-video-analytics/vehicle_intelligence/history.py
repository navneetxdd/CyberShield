"""
Vehicle Intelligence Module – Stage 6: Vehicle History Logging
==============================================================
HistoryLogger writes one row to vi_vehicle_history for every confirmed
plate detection.  It also decides whether a detection is an 'entry',
'exit', or plain 'detection' event:

  entry     – first time the plate is seen at a camera in this session
              (or after a cooldown period).
  exit      – emitted programmatically when the pipeline signals that a
              tracker ID has been lost (call log_exit).
  detection – all subsequent sightings within the same session window.

The history table is the audit trail used by the dashboard analytics.
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import VI_DB_PATH

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF  = 0.2

# A plate is considered a new "entry" if it has not been seen at the same
# camera within this many seconds.
_ENTRY_COOLDOWN_SECONDS = 300.0   # 5 minutes


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(VI_DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _run_write(action, label: str) -> bool:
    for attempt in range(_RETRY_ATTEMPTS):
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
            if locked and attempt + 1 < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue
            print(f"[VI History] DB error ({label}): {exc}")
            return False
        except Exception as exc:
            print(f"[VI History] DB error ({label}): {exc}")
            return False
        finally:
            if conn is not None:
                conn.close()
    return False


class HistoryLogger:
    """
    Stage 6 of the VI pipeline.

    Maintains an in-memory cache of the last time each (plate, camera)
    pair was logged so we can classify events as 'entry' vs 'detection'
    without hitting the database on every frame.

    Usage::

        logger = HistoryLogger()
        # Call once per confirmed plate read
        logger.log_detection(
            plate_text="MH12AB1234",
            camera_id="cam_01",
            camera_location="Gate A",
            vehicle_type="car",
            confidence=0.91,
            ocr_source="paddle",
        )
        # Call when ByteTrack loses the track
        logger.log_exit("MH12AB1234", "cam_01", "Gate A")
    """

    def __init__(self, entry_cooldown: float = _ENTRY_COOLDOWN_SECONDS) -> None:
        self._entry_cooldown = entry_cooldown
        # {(plate_text, camera_id): last_log_monotonic}
        self._seen_cache: Dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_event(self, plate_text: str, camera_id: str) -> str:
        """Decide whether this detection is an 'entry' or 'detection'."""
        key  = (plate_text, camera_id)
        now  = time.monotonic()
        last = self._seen_cache.get(key)
        if last is None or (now - last) >= self._entry_cooldown:
            event_type = "entry"
        else:
            event_type = "detection"
        self._seen_cache[key] = now
        # Bound cache size
        if len(self._seen_cache) > 8192:
            oldest = sorted(self._seen_cache.items(), key=lambda x: x[1])[:1024]
            for k, _ in oldest:
                self._seen_cache.pop(k, None)
        return event_type

    def _write_event(
        self,
        plate_text: str,
        camera_id: str,
        camera_location: Optional[str],
        event_type: str,
        vehicle_type: Optional[str],
        confidence: Optional[float],
        ocr_source: str,
    ) -> bool:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        def action(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO vi_vehicle_history
                    (plate_text, camera_id, camera_location, timestamp,
                     event_type, vehicle_type, confidence, ocr_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plate_text,
                    camera_id,
                    camera_location,
                    timestamp,
                    event_type,
                    vehicle_type,
                    confidence,
                    ocr_source,
                ),
            )

        return _run_write(action, "write_history_event")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_detection(
        self,
        plate_text: str,
        camera_id: str,
        camera_location: Optional[str] = None,
        vehicle_type: Optional[str] = None,
        confidence: Optional[float] = None,
        ocr_source: str = "unknown",
    ) -> str:
        """
        Log a detection event and return the event_type used.

        Parameters
        ----------
        plate_text : str
            Validated, normalised plate number.
        camera_id : str
            Identifier of the camera that made the detection.
        camera_location : str, optional
            Human-readable location (e.g. "Main Gate", "Parking A").
        vehicle_type : str, optional
            "car" | "motorcycle" | "bus" | "truck"
        confidence : float, optional
            OCR confidence score (0–1).
        ocr_source : str
            "paddle" | "easyocr" | "cloud" | "manual" | "unknown"

        Returns
        -------
        str
            The event_type that was written: "entry" or "detection".
        """
        event_type = self._classify_event(plate_text, camera_id)
        self._write_event(
            plate_text=plate_text,
            camera_id=camera_id,
            camera_location=camera_location,
            event_type=event_type,
            vehicle_type=vehicle_type,
            confidence=confidence,
            ocr_source=ocr_source,
        )
        return event_type

    def log_exit(
        self,
        plate_text: str,
        camera_id: str,
        camera_location: Optional[str] = None,
        vehicle_type: Optional[str] = None,
    ) -> None:
        """
        Explicitly log an 'exit' event (call when a tracker is lost).

        Clears the in-memory cache entry so the next sighting is treated
        as an 'entry' again.
        """
        self._seen_cache.pop((plate_text, camera_id), None)
        self._write_event(
            plate_text=plate_text,
            camera_id=camera_id,
            camera_location=camera_location,
            event_type="exit",
            vehicle_type=vehicle_type,
            confidence=None,
            ocr_source="system",
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_recent(
        self,
        camera_id: Optional[str] = None,
        limit: int = 50,
        event_type: Optional[str] = None,
        plate_search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return the most recent history events.

        Parameters
        ----------
        camera_id : str, optional
            Filter to a single camera.
        limit : int
            Maximum rows to return.
        event_type : str, optional
            Filter by 'entry' | 'exit' | 'detection'.
        plate_search : str, optional
            Partial plate number to search.

        Returns
        -------
        list of dict
        """
        clauses: List[str] = []
        params:  List[Any] = []

        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if plate_search:
            clauses.append("plate_text LIKE ?")
            params.append(f"%{plate_search}%")

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)

        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            rows = conn.execute(
                f"SELECT * FROM vi_vehicle_history{where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[VI History] get_recent error: {exc}")
            return []
        finally:
            if conn is not None:
                conn.close()

    def get_vehicle_history(
        self,
        plate_text: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return history events for a specific plate."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            rows = conn.execute(
                "SELECT * FROM vi_vehicle_history "
                "WHERE plate_text = ? ORDER BY timestamp DESC LIMIT ?",
                (plate_text, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[VI History] get_vehicle_history error: {exc}")
            return []
        finally:
            if conn is not None:
                conn.close()
