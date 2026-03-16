"""
Vehicle Intelligence Module – Main Pipeline Orchestrator
=========================================================
VehicleIntelligencePipeline ties all stages together into a single
process_frame() call.

Full pipeline per frame
------------------------
1. Vehicle detection       – VehicleDetector  → List[VehicleDetection]
2. Plate recognition       – PlateReader      → PlateResult | None
3. Database lookup         – VehicleStore     → vehicle record (new or known)
4. History logging         – HistoryLogger    → "entry" | "detection"
5. Watchlist check         – PlateWatchlist   → WatchlistHit | None
6. Return VIFrameResult    – consumed by the caller (API / runtime)

Standalone vs integrated use
-----------------------------
The pipeline runs standalone.  It can also receive pre-computed
plate text (from the existing main pipeline) via process_plates()
to skip stages 1–2 and jump straight to DB lookup.

Thread safety
-------------
Each camera should have its own VehicleIntelligencePipeline instance.
All shared state (DB, watchlist cache) is protected inside each component.

Usage::

    from vehicle_intelligence import VehicleIntelligencePipeline

    vi = VehicleIntelligencePipeline(camera_id="cam_01",
                                     camera_location="Main Gate")
    result = vi.process_frame(frame)

    # Inject pre-read plates (e.g. from existing pipeline)
    result = vi.process_plates(
        plates=[{"plate_text": "MH12AB1234", "confidence": 0.9,
                 "ocr_source": "paddle", "vehicle_type": "car"}]
    )
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .analytics import VehicleAnalytics
from .anpr import PlateReader, PlateResult
from .config import VI_ANALYTICS_LOOKBACK_HOURS
from .detector import VehicleDetection, VehicleDetector
from .history import HistoryLogger
from .vehicle_store import SQLiteVehicleStore, VehicleLookupInterface
from .watchlist import PlateWatchlist, WatchlistHit


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------

@dataclass
class VIDetection:
    """
    Processed result for one vehicle detected in a frame.

    Combines detector output, OCR result, DB record and watchlist status.
    """
    # --- Detector stage ---
    tracker_id:   int
    vehicle_type: str
    bbox:         tuple                   # (x1, y1, x2, y2)
    det_confidence: float

    # --- ANPR stage (None if plate was not read this frame) ---
    plate_text:   Optional[str]   = None
    ocr_confidence: Optional[float] = None
    ocr_source:   Optional[str]   = None

    # --- DB stage ---
    is_new_vehicle: bool = False
    total_detections: int = 0

    # --- History stage ---
    event_type: str = "detection"         # "entry" | "detection"

    # --- Watchlist stage ---
    watchlist_hit: Optional[WatchlistHit] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tracker_id":       self.tracker_id,
            "vehicle_type":     self.vehicle_type,
            "bbox":             list(self.bbox),
            "det_confidence":   round(self.det_confidence, 4),
            "plate_text":       self.plate_text,
            "ocr_confidence":   (
                round(self.ocr_confidence, 4) if self.ocr_confidence is not None else None
            ),
            "ocr_source":       self.ocr_source,
            "is_new_vehicle":   self.is_new_vehicle,
            "total_detections": self.total_detections,
            "event_type":       self.event_type,
            "watchlist_hit":    (
                self.watchlist_hit.to_dict() if self.watchlist_hit else None
            ),
        }


@dataclass
class VIFrameResult:
    """Aggregated result for one processed frame."""
    camera_id:         str
    camera_location:   Optional[str]
    timestamp:         float                          # monotonic seconds
    vehicle_count:     int
    detections:        List[VIDetection] = field(default_factory=list)
    watchlist_alerts:  List[WatchlistHit] = field(default_factory=list)
    new_vehicles:      List[str] = field(default_factory=list)  # plate_text list
    processing_ms:     float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id":        self.camera_id,
            "camera_location":  self.camera_location,
            "vehicle_count":    self.vehicle_count,
            "detections":       [d.to_dict() for d in self.detections],
            "watchlist_alerts": [h.to_dict() for h in self.watchlist_alerts],
            "new_vehicles":     self.new_vehicles,
            "processing_ms":    round(self.processing_ms, 2),
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class VehicleIntelligencePipeline:
    """
    Orchestrates the complete Vehicle Intelligence pipeline.

    Parameters
    ----------
    camera_id : str
        Identifier for the camera feeding this pipeline instance.
    camera_location : str, optional
        Human-readable location (used in history and alert records).
    vehicle_store : VehicleLookupInterface, optional
        Custom DB backend.  Defaults to SQLiteVehicleStore.
    enable_detection : bool
        Set False to skip YOLO detection (use process_plates() instead).
    """

    def __init__(
        self,
        camera_id: str = "camera_1",
        camera_location: Optional[str] = None,
        vehicle_store: Optional[VehicleLookupInterface] = None,
        enable_detection: bool = True,
    ) -> None:
        self.camera_id       = camera_id
        self.camera_location = camera_location

        # Stage components
        self._detector   = VehicleDetector() if enable_detection else None
        self._anpr       = PlateReader()
        self._store      = vehicle_store or SQLiteVehicleStore()
        self._history    = HistoryLogger()
        self._watchlist  = PlateWatchlist()
        self._analytics  = VehicleAnalytics()

        # Track IDs that have been assigned a confirmed plate
        # {tracker_id: plate_text}
        self._confirmed_plates: Dict[int, str] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Stage 1 + 2: detect vehicles, read plates (from raw frame)
    # ------------------------------------------------------------------

    def process_frame(
        self,
        frame: np.ndarray,
        det_conf: Optional[float] = None,
    ) -> VIFrameResult:
        """
        Run the full pipeline on a raw camera frame.

        Parameters
        ----------
        frame : np.ndarray
            BGR image (e.g. from cv2.VideoCapture).
        det_conf : float, optional
            Override detection confidence threshold.

        Returns
        -------
        VIFrameResult
        """
        t0 = time.monotonic()

        if self._detector is None:
            return VIFrameResult(
                camera_id=self.camera_id,
                camera_location=self.camera_location,
                timestamp=t0,
                vehicle_count=0,
                processing_ms=0.0,
            )

        # Stage 1: Vehicle detection
        raw_detections = self._detector.detect(frame, conf=det_conf)

        # Stage 2: Plate recognition per vehicle
        plate_inputs: List[Dict[str, Any]] = []
        for rd in raw_detections:
            plate_result = self._anpr.read_plate(
                vehicle_crop=rd.frame_crop,
                tracker_id=rd.tracker_id,
            )
            plate_inputs.append(
                {
                    "tracker_id":    rd.tracker_id,
                    "vehicle_type":  rd.vehicle_type,
                    "bbox":          rd.bbox,
                    "det_confidence": rd.det_confidence,
                    "plate_result":  plate_result,   # may be None
                }
            )

        result = self._run_downstream_stages(plate_inputs)
        result.processing_ms = (time.monotonic() - t0) * 1000
        return result

    # ------------------------------------------------------------------
    # Shortcut: inject pre-read plates (skip detection + OCR)
    # ------------------------------------------------------------------

    def process_plates(
        self,
        plates: List[Dict[str, Any]],
    ) -> VIFrameResult:
        """
        Run stages 3–7 using externally provided plate data.

        Useful when the existing pipeline has already run detection + OCR
        and you only need the DB / history / watchlist / analytics layers.

        Parameters
        ----------
        plates : list of dict
            Each dict should have::

                {
                    "plate_text":    str,           # required
                    "confidence":    float | None,  # optional
                    "ocr_source":    str,            # optional
                    "vehicle_type":  str | None,     # optional
                    "tracker_id":    int | None,     # optional
                    "bbox":          tuple | None,   # optional
                }

        Returns
        -------
        VIFrameResult
        """
        t0 = time.monotonic()

        plate_inputs: List[Dict[str, Any]] = []
        for idx, p in enumerate(plates):
            text = p.get("plate_text", "")
            if not text:
                continue
            pr = PlateResult(
                plate_text=text,
                confidence=float(p.get("confidence") or 0.0),
                ocr_source=str(p.get("ocr_source") or "external"),
            )
            plate_inputs.append(
                {
                    "tracker_id":    p.get("tracker_id", -(idx + 1)),
                    "vehicle_type":  p.get("vehicle_type"),
                    "bbox":          p.get("bbox", (0, 0, 0, 0)),
                    "det_confidence": 1.0,
                    "plate_result":  pr,
                }
            )

        result = self._run_downstream_stages(plate_inputs)
        result.processing_ms = (time.monotonic() - t0) * 1000
        return result

    # ------------------------------------------------------------------
    # Stages 3–7: shared downstream processing
    # ------------------------------------------------------------------

    def _run_downstream_stages(
        self,
        plate_inputs: List[Dict[str, Any]],
    ) -> VIFrameResult:
        """
        Run database lookup, history logging, watchlist check for each
        vehicle/plate pair.
        """
        vi_detections: List[VIDetection] = []
        alerts:        List[WatchlistHit] = []
        new_plates:    List[str] = []

        for item in plate_inputs:
            tracker_id    = item["tracker_id"]
            vehicle_type  = item.get("vehicle_type")
            bbox          = item.get("bbox", (0, 0, 0, 0))
            det_conf      = item.get("det_confidence", 1.0)
            plate_result: Optional[PlateResult] = item.get("plate_result")

            # Resolve plate text: from this frame OR from tracker cache
            plate_text: Optional[str] = None
            ocr_confidence: Optional[float] = None
            ocr_source: Optional[str] = None

            if plate_result is not None:
                plate_text     = plate_result.plate_text
                ocr_confidence = plate_result.confidence
                ocr_source     = plate_result.ocr_source
                with self._lock:
                    self._confirmed_plates[tracker_id] = plate_text
            else:
                with self._lock:
                    plate_text = self._confirmed_plates.get(tracker_id)

            # Stage 3: Database lookup / upsert
            is_new    = False
            total_det = 0
            if plate_text:
                record   = self._store.upsert(plate_text, vehicle_type, self.camera_id)
                is_new   = bool(record.get("is_new", False))
                total_det = int(record.get("total_detections", 1))
                if is_new:
                    new_plates.append(plate_text)

            # Stage 4: History logging
            event_type = "detection"
            if plate_text:
                event_type = self._history.log_detection(
                    plate_text=plate_text,
                    camera_id=self.camera_id,
                    camera_location=self.camera_location,
                    vehicle_type=vehicle_type,
                    confidence=ocr_confidence,
                    ocr_source=ocr_source or "unknown",
                )

            # Stage 5: Watchlist check
            hit: Optional[WatchlistHit] = None
            if plate_text:
                hit = self._watchlist.check(
                    plate_text=plate_text,
                    camera_id=self.camera_id,
                    camera_location=self.camera_location,
                )
                if hit:
                    alerts.append(hit)

            vi_detections.append(
                VIDetection(
                    tracker_id=tracker_id,
                    vehicle_type=vehicle_type or "vehicle",
                    bbox=bbox,
                    det_confidence=det_conf,
                    plate_text=plate_text,
                    ocr_confidence=ocr_confidence,
                    ocr_source=ocr_source,
                    is_new_vehicle=is_new,
                    total_detections=total_det,
                    event_type=event_type,
                    watchlist_hit=hit,
                )
            )

        return VIFrameResult(
            camera_id=self.camera_id,
            camera_location=self.camera_location,
            timestamp=time.monotonic(),
            vehicle_count=len(vi_detections),
            detections=vi_detections,
            watchlist_alerts=alerts,
            new_vehicles=new_plates,
        )

    # ------------------------------------------------------------------
    # Tracker lifecycle (call from CameraRuntime on track loss)
    # ------------------------------------------------------------------

    def on_track_lost(self, tracker_id: int) -> None:
        """
        Notify the pipeline that a tracker has been lost.

        Clears OCR vote state and emits an 'exit' history event if the
        tracker had a confirmed plate.
        """
        self._anpr.reset_votes(tracker_id)
        with self._lock:
            plate_text = self._confirmed_plates.pop(tracker_id, None)
        if plate_text:
            self._history.log_exit(
                plate_text=plate_text,
                camera_id=self.camera_id,
                camera_location=self.camera_location,
            )

    # ------------------------------------------------------------------
    # Analytics passthrough (Stage 8)
    # ------------------------------------------------------------------

    @property
    def analytics(self) -> VehicleAnalytics:
        """Direct access to the analytics aggregator."""
        return self._analytics

    @property
    def watchlist(self) -> PlateWatchlist:
        """Direct access to the watchlist manager."""
        return self._watchlist

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all per-session state (tracking, vote caches)."""
        if self._detector is not None:
            self._detector.reset_tracker()
        with self._lock:
            self._confirmed_plates.clear()
