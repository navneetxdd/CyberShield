"""
Vehicle Intelligence Module – Stage 5: Database Lookup
=======================================================
Provides a swappable interface for vehicle registry lookups.

VehicleLookupInterface (ABC)
    The contract that any backend must implement.  When the user supplies
    their own database connector, they can subclass this and pass an
    instance to VehicleIntelligencePipeline.

SQLiteVehicleStore (default implementation)
    Stores vehicle records in the vi_vehicles table within analytics.db.
    Suitable for standalone / development use.

Replacing the backend
---------------------
Implement VehicleLookupInterface, then pass your instance to the pipeline::

    class MyDBStore(VehicleLookupInterface):
        def lookup(self, plate_text):  ...
        def upsert(self, plate_text, vehicle_type, camera_id): ...
        def mark_seen(self, plate_text, camera_id): ...

    pipeline = VehicleIntelligencePipeline(vehicle_store=MyDBStore())
"""
from __future__ import annotations

import sqlite3
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import VI_DB_PATH


# ---------------------------------------------------------------------------
# Abstract interface (plug-in point for the user's own DB)
# ---------------------------------------------------------------------------

class VehicleLookupInterface(ABC):
    """
    Contract for a vehicle registry backend.

    All methods must be safe to call from multiple threads.
    """

    @abstractmethod
    def lookup(self, plate_text: str) -> Optional[Dict[str, Any]]:
        """
        Return the vehicle record for *plate_text*, or None if unknown.

        The dict must include at least::

            {
                "plate_text":       str,
                "vehicle_type":     str | None,
                "total_detections": int,
                "first_seen":       str,   # ISO-8601
                "last_seen":        str,   # ISO-8601
                "registered_owner": str | None,
                "notes":            str | None,
                "is_new":           bool,  # True on first encounter
            }
        """
        ...

    @abstractmethod
    def upsert(
        self,
        plate_text: str,
        vehicle_type: Optional[str],
        camera_id: str,
    ) -> Dict[str, Any]:
        """
        Insert a new vehicle record or update the existing one.

        Must return the resulting record dict (same shape as lookup).
        """
        ...

    @abstractmethod
    def list_vehicles(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return a paginated list of vehicle records."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return the total number of distinct vehicles."""
        ...


# ---------------------------------------------------------------------------
# Default SQLite implementation
# ---------------------------------------------------------------------------

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF  = 0.2


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(VI_DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _run_write(action, label: str) -> Optional[Any]:
    for attempt in range(_RETRY_ATTEMPTS):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            result = action(conn)
            conn.commit()
            return result
        except sqlite3.OperationalError as exc:
            locked = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if conn is not None:
                conn.close()
                conn = None
            if locked and attempt + 1 < _RETRY_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF * (attempt + 1))
                continue
            print(f"[VI VehicleStore] DB error ({label}): {exc}")
            return None
        except Exception as exc:
            print(f"[VI VehicleStore] DB error ({label}): {exc}")
            return None
        finally:
            if conn is not None:
                conn.close()
    return None


class SQLiteVehicleStore(VehicleLookupInterface):
    """
    Default vehicle registry backed by the vi_vehicles SQLite table.

    Thread-safe; uses WAL mode and retry-on-lock logic.
    """

    # ------------------------------------------------------------------
    # VehicleLookupInterface implementation
    # ------------------------------------------------------------------

    def lookup(self, plate_text: str) -> Optional[Dict[str, Any]]:
        """Return the vehicle record, or None if not yet registered."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            row  = conn.execute(
                "SELECT * FROM vi_vehicles WHERE plate_text = ?",
                (plate_text,),
            ).fetchone()
            if row is None:
                return None
            return {**dict(row), "is_new": False}
        except Exception as exc:
            print(f"[VI VehicleStore] lookup error: {exc}")
            return None
        finally:
            if conn is not None:
                conn.close()

    def upsert(
        self,
        plate_text: str,
        vehicle_type: Optional[str],
        camera_id: str,
    ) -> Dict[str, Any]:
        """
        Insert a new vehicle or update last_seen + detection count.

        Returns the resulting record dict; sets is_new=True on first insert.
        """
        now    = datetime.now(timezone.utc).isoformat(timespec="seconds")
        is_new = self.lookup(plate_text) is None

        def action(conn: sqlite3.Connection):
            conn.execute(
                """
                INSERT INTO vi_vehicles (plate_text, vehicle_type, total_detections,
                                         first_seen, last_seen)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(plate_text) DO UPDATE SET
                    vehicle_type     = COALESCE(excluded.vehicle_type, vi_vehicles.vehicle_type),
                    total_detections = vi_vehicles.total_detections + 1,
                    last_seen        = excluded.last_seen
                """,
                (plate_text, vehicle_type, now, now),
            )

        _run_write(action, "upsert_vehicle")

        record = self.lookup(plate_text) or {
            "plate_text":       plate_text,
            "vehicle_type":     vehicle_type,
            "total_detections": 1,
            "first_seen":       now,
            "last_seen":        now,
            "registered_owner": None,
            "notes":            None,
        }
        record["is_new"] = is_new
        return record

    def list_vehicles(
        self,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            if search:
                like = f"%{search}%"
                rows = conn.execute(
                    """
                    SELECT * FROM vi_vehicles
                    WHERE plate_text LIKE ?
                       OR vehicle_type LIKE ?
                       OR registered_owner LIKE ?
                    ORDER BY last_seen DESC LIMIT ? OFFSET ?
                    """,
                    (like, like, like, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM vi_vehicles ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[VI VehicleStore] list_vehicles error: {exc}")
            return []
        finally:
            if conn is not None:
                conn.close()

    def count(self) -> int:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            return conn.execute(
                "SELECT COUNT(*) FROM vi_vehicles"
            ).fetchone()[0]
        except Exception as exc:
            print(f"[VI VehicleStore] count error: {exc}")
            return 0
        finally:
            if conn is not None:
                conn.close()

    # ------------------------------------------------------------------
    # Extra queries (not part of the abstract interface)
    # ------------------------------------------------------------------

    def get_frequent_vehicles(
        self,
        min_detections: int,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return vehicles seen at least *min_detections* times."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            rows = conn.execute(
                """
                SELECT * FROM vi_vehicles
                WHERE total_detections >= ?
                ORDER BY total_detections DESC
                LIMIT ?
                """,
                (min_detections, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[VI VehicleStore] get_frequent_vehicles error: {exc}")
            return []
        finally:
            if conn is not None:
                conn.close()
