"""
Vehicle Intelligence Module – Stage 3 & 4: Plate Recognition + Text Extraction
================================================================================
PlateReader implements a two-stage process:
  1. Plate region detection – YOLOv8 plate detector locates the licence plate
     within a vehicle crop.
  2. OCR pipeline        – PaddleOCR (primary) → EasyOCR (fallback) converts
     the plate image into text.

Plates are validated and normalised (e.g. "MH 12 AB 1234" → "MH12AB1234").
A per-tracker rate limiter avoids re-scanning the same vehicle every frame.

A confidence-voting system (matching the parent pipeline) requires either:
  • A single high-confidence read (>= VI_PLATE_DIRECT_ACCEPT_CONFIDENCE), or
  • Multiple reads accumulating sufficient score (>= VI_PLATE_CONFIRMATION_HITS).

This module integrates with SharedResources when available so models are
not loaded twice when running alongside the main pipeline.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np

_APP_DIR = Path(__file__).resolve().parent.parent
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from .config import (
    PLATE_ALLOWLIST,
    PLATE_TEXT_PATTERN,
    VI_LOCAL_OCR_MIN_CONFIDENCE,
    VI_PADDLE_MIN_CONFIDENCE,
    VI_PLATE_CONFIDENCE,
    VI_PLATE_DIRECT_ACCEPT_CONFIDENCE,
    VI_PLATE_CONFIRMATION_HITS,
    VI_PLATE_OCR_TARGET_WIDTH,
    VI_PLATE_SCAN_INTERVAL,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PlateResult:
    """A successfully read and validated plate number."""
    plate_text: str
    confidence: float
    ocr_source: str                  # "paddle" | "easyocr" | "none"


@dataclass
class _VoteState:
    """Accumulated OCR votes for one tracker ID."""
    hits: int = 0
    best_confidence: float = 0.0
    score: float = 0.0
    best_text: str = ""
    best_source: str = "none"


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------

def normalize_plate_text(text: str) -> Optional[str]:
    """Strip spaces/punctuation, upper-case, validate against pattern."""
    cleaned = "".join(ch for ch in text.upper() if ch in PLATE_ALLOWLIST)
    return cleaned if PLATE_TEXT_PATTERN.match(cleaned) else None


# ---------------------------------------------------------------------------
# PlateReader
# ---------------------------------------------------------------------------

class PlateReader:
    """
    Stage 3 + 4 of the VI pipeline.

    Accepts a vehicle crop (numpy BGR array), detects the plate sub-region,
    runs the OCR cascade, and returns a PlateResult (or None if no confident
    read was obtained).

    Usage::

        reader = PlateReader()
        result = reader.read_plate(vehicle_crop, tracker_id=42)
        if result:
            print(result.plate_text, result.confidence)
    """

    def __init__(self) -> None:
        self._plate_detector = None
        self._paddle_ocr     = None
        self._easy_ocr       = None

        # Per-tracker scan timestamp cache {tracker_id: last_scan_monotonic}
        self._last_scan: Dict[int, float]  = {}
        # Per-tracker vote accumulator {tracker_id: _VoteState}
        self._votes: Dict[int, _VoteState] = {}

    # ------------------------------------------------------------------
    # Lazy model access
    # ------------------------------------------------------------------

    def _get_plate_detector(self):
        if self._plate_detector is None:
            try:
                from pipeline import SharedResources  # type: ignore
                self._plate_detector = SharedResources.get_plate_detector()
            except Exception as exc:
                print(f"[VI ANPR] Plate detector unavailable: {exc}")
        return self._plate_detector

    def _get_paddle_ocr(self):
        if self._paddle_ocr is None:
            try:
                from pipeline import SharedResources  # type: ignore
                self._paddle_ocr = SharedResources.get_paddle_ocr_reader()
            except Exception as exc:
                print(f"[VI ANPR] PaddleOCR unavailable: {exc}")
        return self._paddle_ocr

    def _get_easy_ocr(self):
        if self._easy_ocr is None:
            try:
                from pipeline import SharedResources  # type: ignore
                self._easy_ocr = SharedResources.get_ocr_reader()
            except Exception as exc:
                print(f"[VI ANPR] EasyOCR unavailable: {exc}")
        return self._easy_ocr

    # ------------------------------------------------------------------
    # Image preprocessing
    # ------------------------------------------------------------------

    @staticmethod
    def _preprocess(crop: np.ndarray) -> np.ndarray:
        """Resize, convert to grayscale with CLAHE, then back to BGR."""
        h, w = crop.shape[:2]
        if w < VI_PLATE_OCR_TARGET_WIDTH:
            scale  = VI_PLATE_OCR_TARGET_WIDTH / w
            crop   = cv2.resize(
                crop,
                (VI_PLATE_OCR_TARGET_WIDTH, int(h * scale)),
                interpolation=cv2.INTER_CUBIC,
            )
        gray    = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        clahe   = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray    = clahe.apply(gray)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    # ------------------------------------------------------------------
    # Plate region detection
    # ------------------------------------------------------------------

    def _detect_plate_region(self, vehicle_crop: np.ndarray) -> Optional[np.ndarray]:
        """Return the highest-confidence plate sub-image from a vehicle crop."""
        detector = self._get_plate_detector()
        if detector is None or vehicle_crop is None or vehicle_crop.size == 0:
            return None
        try:
            results = detector(vehicle_crop, conf=VI_PLATE_CONFIDENCE, verbose=False)[0]
            boxes   = results.boxes
            if boxes is None or len(boxes) == 0:
                return None
            idx         = int(boxes.conf.argmax())
            x1, y1, x2, y2 = (int(v) for v in boxes.xyxy[idx].cpu().numpy())
            h, w        = vehicle_crop.shape[:2]
            x1, y1     = max(0, x1), max(0, y1)
            x2, y2     = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            return vehicle_crop[y1:y2, x1:x2]
        except Exception as exc:
            print(f"[VI ANPR] Plate region error: {exc}")
            return None

    # ------------------------------------------------------------------
    # OCR engines
    # ------------------------------------------------------------------

    def _run_paddle(self, img: np.ndarray) -> Optional[tuple[str, float]]:
        paddle = self._get_paddle_ocr()
        if paddle is None:
            return None
        try:
            result = paddle.ocr(img, cls=True)
            if not result or not result[0]:
                return None
            candidates: List[tuple[str, float]] = []
            for line in result[0]:
                if (
                    line
                    and len(line) >= 2
                    and isinstance(line[1], (tuple, list))
                    and len(line[1]) >= 2
                ):
                    candidates.append((str(line[1][0]), float(line[1][1])))
            if not candidates:
                return None
            text, conf = max(candidates, key=lambda x: x[1])
            if conf < VI_PADDLE_MIN_CONFIDENCE:
                return None
            return text, conf
        except Exception as exc:
            print(f"[VI ANPR] PaddleOCR error: {exc}")
            return None

    def _run_easy(self, img: np.ndarray) -> Optional[tuple[str, float]]:
        easy = self._get_easy_ocr()
        if easy is None:
            return None
        try:
            results = easy.readtext(img, allowlist=PLATE_ALLOWLIST, detail=1)
            if not results:
                return None
            _, text, conf = max(results, key=lambda x: x[2])
            if conf < VI_LOCAL_OCR_MIN_CONFIDENCE:
                return None
            return str(text), float(conf)
        except Exception as exc:
            print(f"[VI ANPR] EasyOCR error: {exc}")
            return None

    # ------------------------------------------------------------------
    # Vote accumulation (noise reduction)
    # ------------------------------------------------------------------

    def _accumulate_vote(
        self,
        tracker_id: int,
        text: str,
        confidence: float,
        source: str,
    ) -> Optional[PlateResult]:
        """
        Record an OCR reading and return a confirmed PlateResult when the
        voting thresholds are met (or immediately on a high-confidence read).
        """
        # Immediate accept on high confidence
        if confidence >= VI_PLATE_DIRECT_ACCEPT_CONFIDENCE:
            normalized = normalize_plate_text(text)
            if normalized:
                self._votes.pop(tracker_id, None)
                return PlateResult(
                    plate_text=normalized,
                    confidence=confidence,
                    ocr_source=source,
                )

        # Accumulate vote
        normalized = normalize_plate_text(text)
        if not normalized:
            return None

        state = self._votes.setdefault(tracker_id, _VoteState())
        state.hits += 1
        state.score += confidence
        if confidence > state.best_confidence:
            state.best_confidence = confidence
            state.best_text       = normalized
            state.best_source     = source

        # Check confirmation threshold
        if (
            state.hits >= VI_PLATE_CONFIRMATION_HITS
            and state.score >= (VI_PLATE_CONFIRMATION_HITS * VI_LOCAL_OCR_MIN_CONFIDENCE)
        ):
            result = PlateResult(
                plate_text=state.best_text,
                confidence=state.best_confidence,
                ocr_source=state.best_source,
            )
            self._votes.pop(tracker_id, None)
            return result

        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read_plate(
        self,
        vehicle_crop: np.ndarray,
        tracker_id: Optional[int] = None,
        force: bool = False,
    ) -> Optional[PlateResult]:
        """
        Attempt to read the licence plate from a vehicle crop.

        Parameters
        ----------
        vehicle_crop : np.ndarray
            BGR image of the detected vehicle region.
        tracker_id : int, optional
            Tracker ID used for rate limiting and vote accumulation.
        force : bool
            Skip the rate-limit check (useful for testing or manual triggers).

        Returns
        -------
        PlateResult or None
            Returns a result only when the confidence threshold is met.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None

        # Rate limiting
        if tracker_id is not None and not force:
            now  = time.monotonic()
            last = self._last_scan.get(tracker_id, 0.0)
            if (now - last) < VI_PLATE_SCAN_INTERVAL:
                return None
            self._last_scan[tracker_id] = now
            # Trim cache to avoid unbounded growth
            if len(self._last_scan) > 4096:
                oldest = sorted(self._last_scan.items(), key=lambda x: x[1])[:512]
                for k, _ in oldest:
                    self._last_scan.pop(k, None)

        # Detect plate sub-region
        plate_region = self._detect_plate_region(vehicle_crop)
        if plate_region is None:
            plate_region = vehicle_crop   # fall back to full vehicle crop

        # Preprocess
        preprocessed = self._preprocess(plate_region)

        # OCR cascade: PaddleOCR → EasyOCR
        ocr_result = self._run_paddle(preprocessed)
        source      = "paddle"
        if ocr_result is None:
            ocr_result = self._run_easy(preprocessed)
            source     = "easyocr"

        if ocr_result is None:
            return None

        text, conf = ocr_result

        if tracker_id is not None:
            return self._accumulate_vote(tracker_id, text, conf, source)

        # No tracker ID – accept directly if the text validates
        normalized = normalize_plate_text(text)
        if normalized:
            return PlateResult(plate_text=normalized, confidence=conf, ocr_source=source)
        return None

    def reset_votes(self, tracker_id: int) -> None:
        """Clear accumulated votes for a tracker (call on track lost)."""
        self._votes.pop(tracker_id, None)
        self._last_scan.pop(tracker_id, None)
