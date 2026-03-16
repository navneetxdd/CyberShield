"""
Vehicle Intelligence Module – Stage 1 & 2: Camera Input + Vehicle Detection
============================================================================
VehicleDetector wraps the shared YOLOv8 model (SharedResources) with
ByteTrack multi-object tracking so each vehicle carries a stable tracker ID
across frames.

If the parent pipeline cannot be imported (standalone use), the detector
loads its own YOLO model instance.

Returned VehicleDetection objects carry:
  - tracker_id   : stable integer ID from ByteTrack
  - vehicle_type : "car" | "motorcycle" | "bus" | "truck"
  - bbox         : (x1, y1, x2, y2) in pixel space
  - confidence   : detector confidence score
  - frame_crop   : numpy array of the vehicle region (BGR)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Ensure the app root is importable (needed when running standalone tests)
_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from .config import (
    VI_DETECT_CONFIDENCE,
    VI_TARGET_CLASSES,
    VI_VEHICLE_CLASSES,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class VehicleDetection:
    """One detected vehicle in a single frame."""
    tracker_id: int
    vehicle_type: str
    bbox: Tuple[int, int, int, int]           # x1, y1, x2, y2
    confidence: float
    frame_crop: Optional[np.ndarray] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class VehicleDetector:
    """
    Stage 1 + 2 of the VI pipeline.

    Detects vehicles using YOLOv8 (reusing SharedResources when available)
    and assigns stable tracker IDs via ByteTrack.

    Usage::

        detector = VehicleDetector()
        detections = detector.detect(frame)
        for d in detections:
            print(d.tracker_id, d.vehicle_type, d.bbox)
    """

    def __init__(self) -> None:
        self._detector = None
        self._tracker = None
        self._fallback_tid: int = 0          # counter used when tracker is absent
        self._init_tracker()

    # ------------------------------------------------------------------
    # Lazy model access – prefers SharedResources to avoid duplicate loads
    # ------------------------------------------------------------------

    def _get_detector(self):
        if self._detector is None:
            try:
                from pipeline import SharedResources  # type: ignore
                self._detector = SharedResources.get_detector()
                print("[VI Detector] Reusing SharedResources detector.")
            except Exception:
                import torch
                from ultralytics import YOLO
                model_name = "yolov8m.pt" if torch.cuda.is_available() else "yolov8s.pt"
                print(f"[VI Detector] Loading standalone detector: {model_name}")
                self._detector = YOLO(model_name)
        return self._detector

    def _init_tracker(self) -> None:
        """Initialise ByteTrack; silently disabled if supervision is missing."""
        try:
            import supervision as sv
            # Pull thresholds from parent config if available; else use sensible defaults
            try:
                from pipeline import (  # type: ignore
                    TRACK_ACTIVATION_THRESHOLD,
                    TRACK_LOST_BUFFER,
                    TRACK_MATCHING_THRESHOLD,
                    TRACK_FRAME_RATE,
                )
                act_thresh = TRACK_ACTIVATION_THRESHOLD
                lost_buf   = TRACK_LOST_BUFFER
                match_thr  = TRACK_MATCHING_THRESHOLD
                frame_rate = TRACK_FRAME_RATE
            except Exception:
                act_thresh = 0.18
                lost_buf   = 45
                match_thr  = 0.72
                frame_rate = 10

            self._tracker = sv.ByteTrack(
                track_activation_threshold=act_thresh,
                lost_track_buffer=lost_buf,
                minimum_matching_threshold=match_thr,
                frame_rate=frame_rate,
            )
        except Exception as exc:
            print(f"[VI Detector] ByteTrack unavailable ({exc}); tracking disabled.")
            self._tracker = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        frame: np.ndarray,
        conf: Optional[float] = None,
    ) -> List[VehicleDetection]:
        """
        Run YOLOv8 + ByteTrack on *frame* and return vehicle detections.

        Parameters
        ----------
        frame : np.ndarray
            BGR image from OpenCV.
        conf : float, optional
            Confidence threshold (defaults to VI_DETECT_CONFIDENCE).

        Returns
        -------
        list of VehicleDetection
        """
        if frame is None or frame.size == 0:
            return []

        threshold = conf if conf is not None else VI_DETECT_CONFIDENCE
        detector  = self._get_detector()

        try:
            results = detector(frame, conf=threshold, verbose=False)[0]
        except Exception as exc:
            print(f"[VI Detector] Inference error: {exc}")
            return []

        boxes = results.boxes
        if boxes is None or len(boxes) == 0:
            return []

        xyxy    = boxes.xyxy.cpu().numpy()
        confs   = boxes.conf.cpu().numpy()
        cls_ids = boxes.cls.cpu().numpy().astype(int)

        # Filter to vehicle classes only
        vehicle_mask = np.array(
            [VI_TARGET_CLASSES.get(c) in VI_VEHICLE_CLASSES for c in cls_ids]
        )
        if not np.any(vehicle_mask):
            return []

        xyxy_v    = xyxy[vehicle_mask]
        confs_v   = confs[vehicle_mask]
        cls_ids_v = cls_ids[vehicle_mask]

        # -----------------------------------------------------------
        # ByteTrack tracking
        # -----------------------------------------------------------
        tracker_ids: Optional[np.ndarray] = None
        if self._tracker is not None:
            try:
                import supervision as sv
                dets = sv.Detections(
                    xyxy=xyxy_v,
                    confidence=confs_v,
                    class_id=cls_ids_v,
                )
                tracked = self._tracker.update_with_detections(dets)
                if tracked.tracker_id is not None and len(tracked.tracker_id) > 0:
                    xyxy_v    = tracked.xyxy
                    confs_v   = (
                        tracked.confidence
                        if tracked.confidence is not None
                        else confs_v
                    )
                    cls_ids_v = (
                        tracked.class_id
                        if tracked.class_id is not None
                        else cls_ids_v
                    )
                    tracker_ids = tracked.tracker_id
            except Exception as exc:
                print(f"[VI Detector] Tracking update error: {exc}")

        # -----------------------------------------------------------
        # Build result list
        # -----------------------------------------------------------
        detections: List[VehicleDetection] = []
        h, w = frame.shape[:2]

        for i in range(len(xyxy_v)):
            x1, y1, x2, y2 = (int(v) for v in xyxy_v[i])
            vtype = VI_TARGET_CLASSES.get(int(cls_ids_v[i]), "vehicle")

            if tracker_ids is not None and i < len(tracker_ids):
                tid = int(tracker_ids[i])
            else:
                self._fallback_tid += 1
                tid = self._fallback_tid

            # Clamp and crop
            cx1, cy1 = max(0, x1), max(0, y1)
            cx2, cy2 = min(w, x2), min(h, y2)
            crop = frame[cy1:cy2, cx1:cx2] if cy2 > cy1 and cx2 > cx1 else None

            detections.append(
                VehicleDetection(
                    tracker_id=tid,
                    vehicle_type=vtype,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(confs_v[i]),
                    frame_crop=crop,
                )
            )

        return detections

    def reset_tracker(self) -> None:
        """Re-initialise the ByteTrack state (e.g. on camera switch)."""
        self._init_tracker()
