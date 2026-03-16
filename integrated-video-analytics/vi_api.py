"""
Vehicle Intelligence Module – FastAPI Router
============================================
Provides REST endpoints for the Vehicle Intelligence Module.
Mounted at /vi in the main application.

Endpoints
---------
GET  /vi/health                 Module readiness check
GET  /vi/analytics/summary      KPI summary card
GET  /vi/analytics/traffic      Hourly / daily traffic buckets
GET  /vi/analytics/types        Vehicle type breakdown
GET  /vi/analytics/cameras      Per-camera detection counts
GET  /vi/vehicles               Paginated vehicle registry
GET  /vi/vehicles/{plate}       Single vehicle detail + history
GET  /vi/history                Recent detection history
GET  /vi/watchlist              Active watchlist entries
POST /vi/watchlist              Add a plate to the watchlist
DELETE /vi/watchlist/{plate}    Remove a plate from the watchlist
GET  /vi/alerts                 Watchlist alerts
POST /vi/alerts/{id}/ack        Acknowledge an alert

The router uses module-level singletons (initialised once on first import)
so it is cheap to include in the existing main.py.

Integration into main.py (add these two lines)::

    from vi_api import vi_router, vi_startup
    app.include_router(vi_router)
    # call vi_startup() inside the lifespan or startup event
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Ensure vehicle_intelligence package is importable
_APP_DIR = Path(__file__).resolve().parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from vehicle_intelligence import (
    SQLiteVehicleStore,
    VehicleAnalytics,
    VehicleIntelligencePipeline,
    HistoryLogger,
    PlateWatchlist,
    vi_init_db,
)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_store:     Optional[SQLiteVehicleStore] = None
_history:   Optional[HistoryLogger]     = None
_watchlist: Optional[PlateWatchlist]    = None
_analytics: Optional[VehicleAnalytics]  = None
_ready:     bool = False


def vi_startup() -> None:
    """
    Initialise the VI module.  Call from the FastAPI lifespan / startup
    event so tables are created before the first request arrives.
    """
    global _store, _history, _watchlist, _analytics, _ready
    try:
        vi_init_db()
        _store     = SQLiteVehicleStore()
        _history   = HistoryLogger()
        _watchlist = PlateWatchlist()
        _analytics = VehicleAnalytics()
        _ready     = True
        print("[VI API] Vehicle Intelligence Module ready.")
    except Exception as exc:
        print(f"[VI API] Startup error: {exc}")
        _ready = False


def _require_ready():
    if not _ready:
        raise HTTPException(
            status_code=503,
            detail="Vehicle Intelligence Module is not initialised. "
                   "Call vi_startup() during application startup.",
        )


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class WatchlistAddRequest(BaseModel):
    plate_text: str = Field(..., description="Normalised plate number, e.g. MH12AB1234")
    reason:     Optional[str] = Field(None, description="Why this plate is flagged")
    priority:   int           = Field(2,    ge=1, le=3, description="1=low, 2=medium, 3=high")
    added_by:   str           = Field("operator", description="Who added this entry")


class AcknowledgeRequest(BaseModel):
    alert_id: int


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

vi_router = APIRouter(prefix="/vi", tags=["Vehicle Intelligence"])


@vi_router.get("/health")
def vi_health() -> Dict[str, Any]:
    """Return the readiness status of the Vehicle Intelligence Module."""
    return {
        "ready":   _ready,
        "module":  "vehicle_intelligence",
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------------

@vi_router.get("/analytics/summary")
def analytics_summary(
    lookback_hours: int = Query(default=24, ge=1, le=720),
) -> Dict[str, Any]:
    """Top-level KPI dashboard card."""
    _require_ready()
    return _analytics.summary(lookback_hours=lookback_hours)  # type: ignore[union-attr]


@vi_router.get("/analytics/traffic")
def analytics_traffic(
    lookback_hours: int   = Query(default=24, ge=1, le=720),
    granularity:    str   = Query(default="hour", pattern="^(hour|day)$"),
) -> List[Dict[str, Any]]:
    """
    Vehicle detection counts bucketed by time.

    granularity: "hour" or "day"
    """
    _require_ready()
    return _analytics.traffic_stats(  # type: ignore[union-attr]
        lookback_hours=lookback_hours,
        granularity=granularity,
    )


@vi_router.get("/analytics/types")
def analytics_types(
    lookback_hours: int = Query(default=24, ge=1, le=720),
) -> Dict[str, int]:
    """Detection counts grouped by vehicle type."""
    _require_ready()
    return _analytics.type_breakdown(lookback_hours=lookback_hours)  # type: ignore[union-attr]


@vi_router.get("/analytics/cameras")
def analytics_cameras(
    lookback_hours: int = Query(default=24, ge=1, le=720),
) -> List[Dict[str, Any]]:
    """Detection counts grouped by camera."""
    _require_ready()
    return _analytics.camera_activity(lookback_hours=lookback_hours)  # type: ignore[union-attr]


@vi_router.get("/analytics/frequent")
def analytics_frequent(
    limit:          int = Query(default=20,  ge=1, le=200),
    min_detections: int = Query(default=3,   ge=1),
) -> List[Dict[str, Any]]:
    """Vehicles with the most detections."""
    _require_ready()
    return _analytics.frequent_vehicles(  # type: ignore[union-attr]
        limit=limit,
        min_detections=min_detections,
    )


@vi_router.get("/analytics/alerts")
def analytics_alerts(
    lookback_hours: int = Query(default=24, ge=1, le=720),
) -> Dict[str, Any]:
    """Watchlist alert summary for the dashboard."""
    _require_ready()
    return _analytics.alert_summary(lookback_hours=lookback_hours)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Vehicle registry endpoints
# ---------------------------------------------------------------------------

@vi_router.get("/vehicles")
def list_vehicles(
    limit:  int           = Query(default=50, ge=1, le=500),
    offset: int           = Query(default=0,  ge=0),
    search: Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    """Paginated vehicle registry."""
    _require_ready()
    return _store.list_vehicles(limit=limit, offset=offset, search=search)  # type: ignore[union-attr]


@vi_router.get("/vehicles/{plate_text}")
def get_vehicle(
    plate_text: str,
    history_limit: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Return full detail for one vehicle, including its recent history.
    """
    _require_ready()
    record = _store.lookup(plate_text.upper())  # type: ignore[union-attr]
    if record is None:
        raise HTTPException(status_code=404, detail=f"Vehicle '{plate_text}' not found.")
    history = _history.get_vehicle_history(plate_text.upper(), limit=history_limit)  # type: ignore[union-attr]
    on_watchlist = _watchlist.is_listed(plate_text.upper())  # type: ignore[union-attr]
    return {
        **record,
        "history": history,
        "on_watchlist": on_watchlist,
    }


# ---------------------------------------------------------------------------
# History endpoint
# ---------------------------------------------------------------------------

@vi_router.get("/history")
def get_history(
    camera_id:    Optional[str] = Query(default=None),
    event_type:   Optional[str] = Query(default=None, pattern="^(entry|exit|detection)$"),
    plate_search: Optional[str] = Query(default=None),
    limit:        int           = Query(default=50, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Recent vehicle history events."""
    _require_ready()
    return _history.get_recent(  # type: ignore[union-attr]
        camera_id=camera_id,
        limit=limit,
        event_type=event_type,
        plate_search=plate_search,
    )


# ---------------------------------------------------------------------------
# Watchlist endpoints
# ---------------------------------------------------------------------------

@vi_router.get("/watchlist")
def list_watchlist(
    include_inactive: bool = Query(default=False),
) -> List[Dict[str, Any]]:
    """Return all (active) watchlist entries."""
    _require_ready()
    return _watchlist.list_entries(include_inactive=include_inactive)  # type: ignore[union-attr]


@vi_router.post("/watchlist", status_code=201)
def add_to_watchlist(body: WatchlistAddRequest) -> Dict[str, Any]:
    """Add or reactivate a plate in the watchlist."""
    _require_ready()
    plate = body.plate_text.upper().strip()
    if not plate:
        raise HTTPException(status_code=422, detail="plate_text must not be empty.")
    ok = _watchlist.add(  # type: ignore[union-attr]
        plate_text=plate,
        reason=body.reason,
        priority=body.priority,
        added_by=body.added_by,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to add to watchlist.")
    return {"status": "added", "plate_text": plate}


@vi_router.delete("/watchlist/{plate_text}", status_code=200)
def remove_from_watchlist(plate_text: str) -> Dict[str, Any]:
    """Deactivate a watchlist entry (soft delete)."""
    _require_ready()
    plate = plate_text.upper().strip()
    ok    = _watchlist.remove(plate)  # type: ignore[union-attr]
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to remove from watchlist.")
    return {"status": "removed", "plate_text": plate}


# ---------------------------------------------------------------------------
# Alert endpoints
# ---------------------------------------------------------------------------

@vi_router.get("/alerts")
def get_alerts(
    limit:               int           = Query(default=50, ge=1, le=500),
    unacknowledged_only: bool          = Query(default=False),
    camera_id:           Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    """Return recent security alerts."""
    _require_ready()
    return _watchlist.get_alerts(  # type: ignore[union-attr]
        limit=limit,
        unacknowledged_only=unacknowledged_only,
        camera_id=camera_id,
    )


@vi_router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(alert_id: int) -> Dict[str, Any]:
    """Mark a watchlist alert as acknowledged."""
    _require_ready()
    ok = _watchlist.acknowledge_alert(alert_id)  # type: ignore[union-attr]
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to acknowledge alert.")
    return {"status": "acknowledged", "alert_id": alert_id}


@vi_router.get("/alerts/count")
def alert_count() -> Dict[str, int]:
    """Return the number of unacknowledged alerts (badge counter)."""
    _require_ready()
    return {"unacknowledged": _watchlist.count_unacknowledged()}  # type: ignore[union-attr]
