"""
Vehicle Intelligence Module – Stage 8: Dashboard Analytics
===========================================================
VehicleAnalytics aggregates data from the VI tables and produces
dashboard-ready summaries.

Metrics produced
----------------
summary()           Top-level KPIs: total vehicles, total detections,
                    active alerts, watchlist size.
traffic_stats()     Vehicle counts per hour over the look-back window.
type_breakdown()    Count by vehicle_type (car, bus, motorcycle, truck).
frequent_vehicles() Plates with the highest detection counts.
camera_activity()   Detection counts grouped by camera.
recent_activity()   Latest history rows (entry/exit feed).
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import (
    VI_ANALYTICS_LOOKBACK_HOURS,
    VI_DB_PATH,
    VI_FREQUENT_THRESHOLD,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(VI_DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _query(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[VI Analytics] Query error: {exc}")
        return []
    finally:
        if conn is not None:
            conn.close()


def _scalar(sql: str, params: tuple = (), default: Any = 0) -> Any:
    conn: Optional[sqlite3.Connection] = None
    try:
        conn = _connect()
        row = conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception as exc:
        print(f"[VI Analytics] Scalar error: {exc}")
        return default
    finally:
        if conn is not None:
            conn.close()


class VehicleAnalytics:
    """
    Stage 8 of the VI pipeline – aggregated vehicle analytics.

    All methods accept an optional *lookback_hours* override; when omitted
    the module-level VI_ANALYTICS_LOOKBACK_HOURS default is used.

    Usage::

        analytics = VehicleAnalytics()
        print(analytics.summary())
        print(analytics.traffic_stats())
    """

    # ------------------------------------------------------------------
    # Top-level summary
    # ------------------------------------------------------------------

    def summary(self, lookback_hours: Optional[int] = None) -> Dict[str, Any]:
        """
        Return a single-object KPI summary suitable for a status card.

        Keys
        ----
        total_vehicles          : int   distinct plates ever registered
        detections_in_window    : int   detections within look-back window
        entries_in_window       : int   'entry' events in look-back window
        exits_in_window         : int   'exit' events in look-back window
        watchlist_size          : int   active watchlist entries
        unacknowledged_alerts   : int   outstanding security alerts
        total_alerts_all_time   : int
        """
        hours   = lookback_hours or VI_ANALYTICS_LOOKBACK_HOURS
        cutoff  = _lookback_ts(hours)

        total_vehicles = _scalar("SELECT COUNT(*) FROM vi_vehicles")
        watchlist_size = _scalar(
            "SELECT COUNT(*) FROM vi_watchlist WHERE is_active = 1"
        )
        unack_alerts = _scalar(
            "SELECT COUNT(*) FROM vi_alerts WHERE acknowledged = 0"
        )
        total_alerts = _scalar("SELECT COUNT(*) FROM vi_alerts")

        detections = _scalar(
            "SELECT COUNT(*) FROM vi_vehicle_history WHERE timestamp >= ?",
            (cutoff,),
        )
        entries = _scalar(
            "SELECT COUNT(*) FROM vi_vehicle_history WHERE event_type = 'entry' AND timestamp >= ?",
            (cutoff,),
        )
        exits = _scalar(
            "SELECT COUNT(*) FROM vi_vehicle_history WHERE event_type = 'exit' AND timestamp >= ?",
            (cutoff,),
        )

        return {
            "total_vehicles":        total_vehicles,
            "detections_in_window":  detections,
            "entries_in_window":     entries,
            "exits_in_window":       exits,
            "watchlist_size":        watchlist_size,
            "unacknowledged_alerts": unack_alerts,
            "total_alerts_all_time": total_alerts,
            "lookback_hours":        hours,
            "generated_at":          datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    # ------------------------------------------------------------------
    # Traffic statistics
    # ------------------------------------------------------------------

    def traffic_stats(
        self,
        lookback_hours: Optional[int] = None,
        granularity: str = "hour",
    ) -> List[Dict[str, Any]]:
        """
        Return vehicle detection counts bucketed by *granularity*.

        Parameters
        ----------
        lookback_hours : int, optional
        granularity : str
            "hour" (default) – one bucket per hour
            "day"            – one bucket per day

        Returns
        -------
        list of {"bucket": str, "count": int}
        """
        hours  = lookback_hours or VI_ANALYTICS_LOOKBACK_HOURS
        cutoff = _lookback_ts(hours)

        if granularity == "day":
            fmt = "%Y-%m-%d"
        else:
            fmt = "%Y-%m-%dT%H"

        rows = _query(
            """
            SELECT strftime(?, timestamp) AS bucket, COUNT(*) AS count
            FROM vi_vehicle_history
            WHERE timestamp >= ?
            GROUP BY bucket
            ORDER BY bucket ASC
            """,
            (fmt, cutoff),
        )
        return [{"bucket": r["bucket"], "count": r["count"]} for r in rows]

    # ------------------------------------------------------------------
    # Vehicle type breakdown
    # ------------------------------------------------------------------

    def type_breakdown(
        self, lookback_hours: Optional[int] = None
    ) -> Dict[str, int]:
        """
        Return detection counts grouped by vehicle_type.

        Returns
        -------
        {"car": int, "truck": int, "motorcycle": int, "bus": int}
        """
        hours  = lookback_hours or VI_ANALYTICS_LOOKBACK_HOURS
        cutoff = _lookback_ts(hours)

        rows = _query(
            """
            SELECT COALESCE(vehicle_type, 'unknown') AS vtype, COUNT(*) AS cnt
            FROM vi_vehicle_history
            WHERE timestamp >= ?
            GROUP BY vtype
            """,
            (cutoff,),
        )
        return {r["vtype"]: r["cnt"] for r in rows}

    # ------------------------------------------------------------------
    # Frequent vehicles
    # ------------------------------------------------------------------

    def frequent_vehicles(
        self,
        limit: int = 20,
        min_detections: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return vehicles with the highest total detection counts.

        Parameters
        ----------
        limit : int
        min_detections : int, optional
            Override VI_FREQUENT_THRESHOLD.
        """
        threshold = min_detections if min_detections is not None else VI_FREQUENT_THRESHOLD
        return _query(
            """
            SELECT plate_text, vehicle_type, total_detections,
                   first_seen, last_seen, registered_owner, notes
            FROM vi_vehicles
            WHERE total_detections >= ?
            ORDER BY total_detections DESC
            LIMIT ?
            """,
            (threshold, limit),
        )

    # ------------------------------------------------------------------
    # Camera activity
    # ------------------------------------------------------------------

    def camera_activity(
        self, lookback_hours: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Return detection counts grouped by camera_id within the window.

        Returns
        -------
        list of {"camera_id": str, "camera_location": str|None, "count": int}
        """
        hours  = lookback_hours or VI_ANALYTICS_LOOKBACK_HOURS
        cutoff = _lookback_ts(hours)

        return _query(
            """
            SELECT camera_id,
                   camera_location,
                   COUNT(*) AS count
            FROM vi_vehicle_history
            WHERE timestamp >= ?
            GROUP BY camera_id, camera_location
            ORDER BY count DESC
            """,
            (cutoff,),
        )

    # ------------------------------------------------------------------
    # Recent activity feed
    # ------------------------------------------------------------------

    def recent_activity(
        self,
        limit: int = 50,
        camera_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return the latest history records (for the live event feed).

        Parameters
        ----------
        limit : int
        camera_id : str, optional
        event_type : str, optional
            Filter to 'entry' | 'exit' | 'detection'.
        """
        clauses: List[str] = []
        params:  List[Any] = []
        if camera_id:
            clauses.append("camera_id = ?")
            params.append(camera_id)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where  = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)

        return _query(
            f"SELECT * FROM vi_vehicle_history{where} ORDER BY timestamp DESC LIMIT ?",
            tuple(params),
        )

    # ------------------------------------------------------------------
    # Watchlist alert summary
    # ------------------------------------------------------------------

    def alert_summary(
        self, lookback_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Return a summary of watchlist alerts.

        Keys
        ----
        total_in_window         : int
        unacknowledged          : int
        by_priority             : {"1": int, "2": int, "3": int}
        top_plates              : list of {"plate_text": str, "count": int}
        """
        hours  = lookback_hours or VI_ANALYTICS_LOOKBACK_HOURS
        cutoff = _lookback_ts(hours)

        total = _scalar(
            "SELECT COUNT(*) FROM vi_alerts WHERE timestamp >= ?", (cutoff,)
        )
        unack = _scalar(
            "SELECT COUNT(*) FROM vi_alerts WHERE acknowledged = 0 AND timestamp >= ?",
            (cutoff,),
        )

        by_pri_rows = _query(
            """
            SELECT priority, COUNT(*) AS cnt
            FROM vi_alerts
            WHERE timestamp >= ?
            GROUP BY priority
            """,
            (cutoff,),
        )
        by_priority = {str(r["priority"]): r["cnt"] for r in by_pri_rows}

        top_plates = _query(
            """
            SELECT plate_text, COUNT(*) AS count
            FROM vi_alerts
            WHERE timestamp >= ?
            GROUP BY plate_text
            ORDER BY count DESC
            LIMIT 10
            """,
            (cutoff,),
        )

        return {
            "total_in_window":  total,
            "unacknowledged":   unack,
            "by_priority":      by_priority,
            "top_plates":       top_plates,
            "lookback_hours":   hours,
        }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _lookback_ts(hours: int) -> str:
    """Return an ISO-8601 UTC string *hours* ago."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return cutoff.isoformat(timespec="seconds")
