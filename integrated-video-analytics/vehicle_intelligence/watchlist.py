"""
Vehicle Intelligence Module – Stage 7: Watchlist Check
=======================================================
PlateWatchlist manages the set of licence plates that require special
monitoring.  Every confirmed plate read is checked against the watchlist;
a match generates a vi_alerts record and returns a WatchlistHit.

Storage
-------
Watchlist entries live in the vi_watchlist SQLite table (not image files,
unlike the facial recognition watchlist).  The list is cached in memory
and refreshed periodically to reduce DB round-trips.

Priority levels
---------------
1  low      – informational flag
2  medium   – review required
3  high     – immediate response needed
"""
from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import VI_DB_PATH, VI_DEFAULT_ALERT_PRIORITY

_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF  = 0.2
_CACHE_TTL_SECONDS = 30.0         # refresh in-memory cache every 30 s


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
            print(f"[VI Watchlist] DB error ({label}): {exc}")
            return False
        except Exception as exc:
            print(f"[VI Watchlist] DB error ({label}): {exc}")
            return False
        finally:
            if conn is not None:
                conn.close()
    return False


# ---------------------------------------------------------------------------
# Data structure returned on a hit
# ---------------------------------------------------------------------------

class WatchlistHit:
    """Describes a watchlist match for a detected plate."""

    def __init__(
        self,
        plate_text: str,
        reason: Optional[str],
        priority: int,
        alert_id: Optional[int] = None,
    ) -> None:
        self.plate_text  = plate_text
        self.reason      = reason
        self.priority    = priority
        self.alert_id    = alert_id
        self.timestamp   = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plate_text": self.plate_text,
            "reason":     self.reason,
            "priority":   self.priority,
            "alert_id":   self.alert_id,
            "timestamp":  self.timestamp,
        }

    def __repr__(self) -> str:
        return (
            f"WatchlistHit(plate={self.plate_text!r}, "
            f"priority={self.priority}, reason={self.reason!r})"
        )


# ---------------------------------------------------------------------------
# PlateWatchlist
# ---------------------------------------------------------------------------

class PlateWatchlist:
    """
    Stage 7 of the VI pipeline.

    Thread-safe watchlist backed by the vi_watchlist SQLite table.
    An in-memory cache is maintained and refreshed every *cache_ttl* seconds.

    Usage::

        wl = PlateWatchlist()
        wl.add("MH12AB1234", reason="Reported stolen", priority=3)

        hit = wl.check("MH12AB1234", camera_id="cam_01")
        if hit:
            print(f"ALERT: {hit}")
    """

    def __init__(self, cache_ttl: float = _CACHE_TTL_SECONDS) -> None:
        self._cache_ttl = cache_ttl
        self._lock      = threading.RLock()
        # {plate_text: {reason, priority}}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_refresh: float = 0.0
        self._refresh_cache()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _refresh_cache(self) -> None:
        """Reload the active watchlist from the database into memory."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            rows = conn.execute(
                "SELECT plate_text, reason, priority FROM vi_watchlist WHERE is_active = 1"
            ).fetchall()
            with self._lock:
                self._cache = {
                    row["plate_text"]: {
                        "reason":   row["reason"],
                        "priority": row["priority"],
                    }
                    for row in rows
                }
            self._last_refresh = time.monotonic()
        except Exception as exc:
            print(f"[VI Watchlist] Cache refresh error: {exc}")
        finally:
            if conn is not None:
                conn.close()

    def _maybe_refresh(self) -> None:
        if time.monotonic() - self._last_refresh > self._cache_ttl:
            self._refresh_cache()

    # ------------------------------------------------------------------
    # Alert persistence
    # ------------------------------------------------------------------

    def _write_alert(
        self,
        plate_text: str,
        camera_id: str,
        camera_location: Optional[str],
        priority: int,
        message: str,
    ) -> Optional[int]:
        """Insert a vi_alerts row and return the new row id."""
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result_id: list[Optional[int]] = [None]

        def action(conn: sqlite3.Connection) -> None:
            cur = conn.execute(
                """
                INSERT INTO vi_alerts
                    (plate_text, camera_id, camera_location, timestamp,
                     alert_type, priority, message)
                VALUES (?, ?, ?, ?, 'watchlist_match', ?, ?)
                """,
                (plate_text, camera_id, camera_location, timestamp, priority, message),
            )
            result_id[0] = cur.lastrowid

        _run_write(action, "write_alert")
        return result_id[0]

    # ------------------------------------------------------------------
    # Public API – watchlist management
    # ------------------------------------------------------------------

    def add(
        self,
        plate_text: str,
        reason: Optional[str] = None,
        priority: int = VI_DEFAULT_ALERT_PRIORITY,
        added_by: str = "operator",
    ) -> bool:
        """
        Add a plate to the watchlist (or reactivate if it already exists).

        Parameters
        ----------
        plate_text : str
            Normalised plate number (e.g. "MH12AB1234").
        reason : str, optional
            Why this plate is flagged.
        priority : int
            1=low, 2=medium, 3=high.
        added_by : str
            Operator or system identifier.

        Returns
        -------
        bool
            True if the write succeeded.
        """
        def action(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                INSERT INTO vi_watchlist (plate_text, reason, priority, added_by, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(plate_text) DO UPDATE SET
                    reason    = excluded.reason,
                    priority  = excluded.priority,
                    added_by  = excluded.added_by,
                    is_active = 1
                """,
                (plate_text, reason, priority, added_by),
            )

        ok = _run_write(action, "watchlist_add")
        if ok:
            with self._lock:
                self._cache[plate_text] = {"reason": reason, "priority": priority}
        return bool(ok)

    def remove(self, plate_text: str) -> bool:
        """
        Deactivate a watchlist entry (soft delete – keeps alert history).

        Returns True if the write succeeded.
        """
        def action(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE vi_watchlist SET is_active = 0 WHERE plate_text = ?",
                (plate_text,),
            )

        ok = _run_write(action, "watchlist_remove")
        if ok:
            with self._lock:
                self._cache.pop(plate_text, None)
        return bool(ok)

    def list_entries(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Return all watchlist entries (active only by default)."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            if include_inactive:
                rows = conn.execute(
                    "SELECT * FROM vi_watchlist ORDER BY priority DESC, added_at DESC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM vi_watchlist WHERE is_active = 1 "
                    "ORDER BY priority DESC, added_at DESC"
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[VI Watchlist] list_entries error: {exc}")
            return []
        finally:
            if conn is not None:
                conn.close()

    def is_listed(self, plate_text: str) -> bool:
        """Quick in-memory check (no DB hit)."""
        self._maybe_refresh()
        with self._lock:
            return plate_text in self._cache

    # ------------------------------------------------------------------
    # Public API – detection-time check
    # ------------------------------------------------------------------

    def check(
        self,
        plate_text: str,
        camera_id: str,
        camera_location: Optional[str] = None,
    ) -> Optional[WatchlistHit]:
        """
        Check *plate_text* against the active watchlist.

        If a match is found:
          • A vi_alerts row is persisted.
          • A WatchlistHit is returned.

        If no match, returns None.

        Parameters
        ----------
        plate_text : str
            The validated plate number to look up.
        camera_id : str
            Camera that detected the plate.
        camera_location : str, optional
            Human-readable location string for the alert message.
        """
        self._maybe_refresh()

        with self._lock:
            entry = self._cache.get(plate_text)

        if entry is None:
            return None

        reason   = entry.get("reason")
        priority = int(entry.get("priority", VI_DEFAULT_ALERT_PRIORITY))
        location = camera_location or camera_id
        message  = (
            f"Watchlist vehicle detected at {location}. "
            + (f"Reason: {reason}." if reason else "")
        ).strip()

        alert_id = self._write_alert(
            plate_text=plate_text,
            camera_id=camera_id,
            camera_location=camera_location,
            priority=priority,
            message=message,
        )

        return WatchlistHit(
            plate_text=plate_text,
            reason=reason,
            priority=priority,
            alert_id=alert_id,
        )

    # ------------------------------------------------------------------
    # Alert queries
    # ------------------------------------------------------------------

    def get_alerts(
        self,
        limit: int = 50,
        unacknowledged_only: bool = False,
        camera_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent watchlist alerts."""
        clauses: List[str] = []
        params:  List[Any] = []
        if unacknowledged_only:
            clauses.append("acknowledged = 0")
        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        where  = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)

        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            rows = conn.execute(
                f"SELECT * FROM vi_alerts{where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception as exc:
            print(f"[VI Watchlist] get_alerts error: {exc}")
            return []
        finally:
            if conn is not None:
                conn.close()

    def acknowledge_alert(self, alert_id: int) -> bool:
        """Mark an alert as acknowledged."""
        def action(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE vi_alerts SET acknowledged = 1 WHERE id = ?",
                (alert_id,),
            )

        return bool(_run_write(action, "ack_alert"))

    def count_unacknowledged(self) -> int:
        """Return the number of outstanding (unacknowledged) alerts."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = _connect()
            return conn.execute(
                "SELECT COUNT(*) FROM vi_alerts WHERE acknowledged = 0"
            ).fetchone()[0]
        except Exception as exc:
            print(f"[VI Watchlist] count_unacknowledged error: {exc}")
            return 0
        finally:
            if conn is not None:
                conn.close()
