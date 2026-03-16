"""
Vehicle Intelligence Module
===========================
A modular vehicle monitoring pipeline for the CyberShield video analytics
platform.

Pipeline stages
---------------
1. Camera input        – handled by the caller (CameraRuntime / test harness)
2. Vehicle detection   – detector.VehicleDetector
3. Plate recognition   – anpr.PlateReader
4. Database lookup     – vehicle_store.SQLiteVehicleStore (swappable via interface)
5. History logging     – history.HistoryLogger
6. Watchlist check     – watchlist.PlateWatchlist
7. Dashboard analytics – analytics.VehicleAnalytics

Quick start::

    from vehicle_intelligence import VehicleIntelligencePipeline, vi_init_db

    vi_init_db()  # create tables (idempotent)
    pipeline = VehicleIntelligencePipeline(
        camera_id="cam_01",
        camera_location="Main Gate",
    )

    # Full-frame path (requires YOLO + OCR models)
    result = pipeline.process_frame(bgr_frame)

    # Inject plates already read by the existing pipeline
    result = pipeline.process_plates([
        {"plate_text": "MH12AB1234", "vehicle_type": "car",
         "confidence": 0.91, "ocr_source": "paddle"}
    ])
"""
from .analytics import VehicleAnalytics
from .anpr import PlateReader, PlateResult
from .db_schema import vi_init_db
from .detector import VehicleDetection, VehicleDetector
from .history import HistoryLogger
from .pipeline import VehicleIntelligencePipeline, VIDetection, VIFrameResult
from .vehicle_store import SQLiteVehicleStore, VehicleLookupInterface
from .watchlist import PlateWatchlist, WatchlistHit

__all__ = [
    # Pipeline entry point
    "VehicleIntelligencePipeline",
    # Result types
    "VIFrameResult",
    "VIDetection",
    # Individual stage classes
    "VehicleDetector",
    "VehicleDetection",
    "PlateReader",
    "PlateResult",
    "SQLiteVehicleStore",
    "VehicleLookupInterface",
    "HistoryLogger",
    "PlateWatchlist",
    "WatchlistHit",
    "VehicleAnalytics",
    # DB initialisation
    "vi_init_db",
]
