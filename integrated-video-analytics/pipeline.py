from __future__ import annotations

import concurrent.futures
import copy
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import cv2
try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    easyocr = None
    HAS_EASYOCR = False
try:
    from paddleocr import PaddleOCR
    HAS_PADDLEOCR = True
except ImportError:
    PaddleOCR = None
    HAS_PADDLEOCR = False
import numpy as np
try:
    import onnxruntime as ort
except ImportError:
    ort = None
try:
    import insightface
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
except ImportError:
    insightface = None
    FaceAnalysis = None
    HAS_INSIGHTFACE = False
import requests
import supervision as sv
import torch
from ultralytics import YOLO
try:
    from sahi import AutoDetectionModel  # type: ignore[import-not-found]
    from sahi.predict import get_sliced_prediction  # type: ignore[import-not-found]
    HAS_SAHI = True
except ImportError:
    AutoDetectionModel = None
    get_sliced_prediction = None
    HAS_SAHI = False
try:
    import google.generativeai as genai  # type: ignore[import-not-found]
    HAS_GEMINI = True
except ImportError:
    genai = None
    HAS_GEMINI = False

from database import (
    log_event,
    store_metric,
    upsert_face_record,
    upsert_plate_read,
    upsert_vehicle_record,
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_PLATE_MODEL_URL = (
    "https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt"
)

TARGET_CLASSES = {
    0: "person",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}
VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck"}
WATCHLIST_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
PLATE_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
PLATE_TEXT_PATTERN = re.compile(r"^[A-Z0-9]{4,10}$")


def resolve_model_path(explicit: Optional[str], *local_candidates: Path, fallback: str) -> str:
    if explicit:
        return explicit
    for candidate in local_candidates:
        if candidate.exists():
            return str(candidate)
    return fallback


def normalize_plate_text(text: str) -> Optional[str]:
    cleaned = "".join(ch for ch in text.upper() if ch.isalnum())
    if not PLATE_TEXT_PATTERN.match(cleaned):
        return None
    return cleaned


def detector_fallback_name() -> str:
    return "yolo11s.pt" if torch.cuda.is_available() else "yolo11s.pt"


def read_env_float(
    name: str,
    default: float,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw.strip())
    except (AttributeError, ValueError):
        print(f"Invalid {name}={raw!r}; using default {default}.")
        return default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def read_env_int(
    name: str,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (AttributeError, ValueError):
        print(f"Invalid {name}={raw!r}; using default {default}.")
        return default
    if minimum is not None:
        value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def read_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    print(f"Invalid {name}={raw!r}; using default {default}.")
    return default


def touch_timestamp_cache(cache: Dict[Any, float], key: Any, timestamp: float) -> None:
    cache.pop(key, None)
    cache[key] = timestamp


def trim_timestamp_cache(
    cache: Dict[Any, float],
    now: float,
    ttl_seconds: float,
    max_items: int,
) -> None:
    cutoff = now - ttl_seconds
    stale_keys = [key for key, seen_at in cache.items() if seen_at < cutoff]
    for key in stale_keys:
        cache.pop(key, None)
    while len(cache) > max_items:
        oldest_key = next(iter(cache))
        cache.pop(oldest_key, None)


DETECTION_CONFIDENCE = read_env_float("CYBERSHIELD_DETECT_CONFIDENCE", 0.20, minimum=0.05, maximum=0.95)
PLATE_CONFIDENCE = read_env_float("CYBERSHIELD_PLATE_CONFIDENCE", 0.25, minimum=0.05, maximum=0.95)
DETECTION_IMAGE_SIZE = read_env_int(
    "CYBERSHIELD_DETECT_IMGSZ",
    1024,
    minimum=320,
    maximum=1600,
)
PLATE_IMAGE_SIZE = read_env_int("CYBERSHIELD_PLATE_IMGSZ", 640, minimum=256, maximum=1280)
MIN_STABLE_FRAMES = read_env_int("CYBERSHIELD_MIN_STABLE_FRAMES", 2, minimum=1, maximum=12)
PLATE_SCAN_INTERVAL_SECONDS = read_env_float("CYBERSHIELD_PLATE_SCAN_INTERVAL", 2.0, minimum=0.2)
PLATE_REFRESH_INTERVAL_SECONDS = read_env_float("CYBERSHIELD_PLATE_REFRESH_INTERVAL", 8.0, minimum=0.5)
FACE_SCAN_INTERVAL_SECONDS = read_env_float("CYBERSHIELD_FACE_SCAN_INTERVAL", 3.0, minimum=0.5)
PLATE_OCR_TARGET_WIDTH = read_env_int("CYBERSHIELD_PLATE_TARGET_WIDTH", 480, minimum=240, maximum=1280)
PLATE_HEURISTIC_MIN_VEHICLE_WIDTH = read_env_int("CYBERSHIELD_PLATE_HEURISTIC_MIN_WIDTH", 100, minimum=80, maximum=1000)
PLATE_HEURISTIC_MIN_VEHICLE_HEIGHT = read_env_int("CYBERSHIELD_PLATE_HEURISTIC_MIN_HEIGHT", 80, minimum=40, maximum=1000)
RENDER_TRACK_TTL_SECONDS = read_env_float(
    "CYBERSHIELD_RENDER_TRACK_TTL",
    1.0 if torch.cuda.is_available() else 1.75,
    minimum=0.25,
)
RENDER_TRACK_MAX_TTL_SECONDS = read_env_float("CYBERSHIELD_RENDER_TRACK_MAX_TTL", 4.0, minimum=1.0)
RENDER_TRACK_LATENCY_MULTIPLIER = read_env_float(
    "CYBERSHIELD_RENDER_TRACK_LATENCY_MULTIPLIER",
    2.5,
    minimum=1.0,
    maximum=6.0,
)
TRACK_STALE_SECONDS = read_env_float("CYBERSHIELD_TRACK_STALE_SECONDS", 15.0, minimum=1.0)
METRIC_WRITE_INTERVAL_SECONDS = read_env_float("CYBERSHIELD_METRIC_WRITE_INTERVAL", 2.0, minimum=0.5)
PLATE_CONFIRMATION_HITS = read_env_int("CYBERSHIELD_PLATE_CONFIRMATION_HITS", 1, minimum=1, maximum=8)
PLATE_DIRECT_ACCEPT_CONFIDENCE = read_env_float(
    "CYBERSHIELD_PLATE_DIRECT_CONFIDENCE",
    0.50,
    minimum=0.1,
    maximum=0.99,
)
PLATE_MIN_AGGREGATE_SCORE = read_env_float("CYBERSHIELD_PLATE_MIN_SCORE", 0.28, minimum=0.1)
PLATE_EXECUTOR_WORKERS = read_env_int(
    "CYBERSHIELD_PLATE_WORKERS",
    max(2, min(4, os.cpu_count() or 4)),
    minimum=1,
    maximum=8,
)
PLATE_QUEUE_LIMIT = read_env_int("CYBERSHIELD_PLATE_QUEUE_LIMIT", 8, minimum=1, maximum=64)
FACE_QUEUE_LIMIT = read_env_int("CYBERSHIELD_FACE_QUEUE_LIMIT", 4, minimum=1, maximum=32)
DB_QUEUE_LIMIT = read_env_int("CYBERSHIELD_DB_QUEUE_LIMIT", 256, minimum=8, maximum=4096)
UNIQUE_CACHE_TTL_SECONDS = read_env_float("CYBERSHIELD_UNIQUE_CACHE_TTL", 3600.0, minimum=60.0)
PLATE_CACHE_LIMIT = read_env_int("CYBERSHIELD_PLATE_CACHE_LIMIT", 4096, minimum=100, maximum=200000)
FACE_TRACK_CACHE_LIMIT = read_env_int("CYBERSHIELD_FACE_TRACK_CACHE_LIMIT", 4096, minimum=100, maximum=200000)
TRACK_ACTIVATION_THRESHOLD = read_env_float("CYBERSHIELD_TRACK_ACTIVATION_THRESHOLD", 0.13, minimum=0.05, maximum=0.9)
TRACK_MATCHING_THRESHOLD = read_env_float("CYBERSHIELD_TRACK_MATCHING_THRESHOLD", 0.65, minimum=0.3, maximum=0.95)
TRACK_LOST_BUFFER = read_env_int("CYBERSHIELD_TRACK_LOST_BUFFER", 60, minimum=5, maximum=180)
TRACK_FRAME_RATE = read_env_int("CYBERSHIELD_TRACK_FRAME_RATE", 12 if torch.cuda.is_available() else 8, minimum=1, maximum=60)
TRACK_MIN_CONSECUTIVE_FRAMES = read_env_int("CYBERSHIELD_TRACK_MIN_CONSECUTIVE", 1, minimum=1, maximum=8)
PLATE_API_COOLDOWN_SECONDS = read_env_float("CYBERSHIELD_PLATE_API_COOLDOWN", 300.0, minimum=10.0)
PADDLE_PRIMARY_MIN_CONFIDENCE = read_env_float("CYBERSHIELD_PADDLE_PRIMARY_MIN_CONFIDENCE", 0.60, minimum=0.1, maximum=0.99)
LOCAL_OCR_MIN_CONFIDENCE = read_env_float("CYBERSHIELD_LOCAL_OCR_MIN_CONFIDENCE", 0.20, minimum=0.05, maximum=0.95)
CLOUD_OCR_MIN_CONFIDENCE = read_env_float("CYBERSHIELD_CLOUD_OCR_MIN_CONFIDENCE", 0.78, minimum=0.05, maximum=0.99)
ENABLE_PADDLE_OCR = read_env_bool("CYBERSHIELD_ENABLE_PADDLE_OCR", True)
ENABLE_EASYOCR_FALLBACK = read_env_bool("CYBERSHIELD_ENABLE_EASYOCR_FALLBACK", True)
FACE_MATCH_THRESHOLD = read_env_float("CYBERSHIELD_FACE_MATCH_THRESHOLD", 0.95, minimum=0.5, maximum=1.3)
ENABLE_GEMINI_ENRICHMENT = read_env_bool("CYBERSHIELD_ENABLE_GEMINI_ENRICHMENT", False)
GEMINI_MODEL_NAME = (os.getenv("CYBERSHIELD_GEMINI_MODEL") or "gemini-2.0-flash").strip() or "gemini-2.0-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
ENABLE_ADVANCED_ON_GPU = read_env_bool("CYBERSHIELD_ENABLE_ADVANCED_ON_GPU", True)
DEFAULT_ADVANCED_DETECTORS = torch.cuda.is_available() and ENABLE_ADVANCED_ON_GPU
ENABLE_HEAVY_VALIDATOR = read_env_bool("CYBERSHIELD_ENABLE_HEAVY_VALIDATOR", DEFAULT_ADVANCED_DETECTORS)
HEAVY_VALIDATOR_MODEL = (os.getenv("CYBERSHIELD_HEAVY_VALIDATOR_MODEL") or "yolov8x.pt").strip() or "yolov8x.pt"
HEAVY_VALIDATOR_MIN_CONF = read_env_float("CYBERSHIELD_HEAVY_VALIDATOR_MIN_CONF", 0.15, minimum=0.05, maximum=0.9)
HEAVY_VALIDATOR_MAX_CONF = read_env_float("CYBERSHIELD_HEAVY_VALIDATOR_MAX_CONF", 0.45, minimum=0.06, maximum=0.95)
HEAVY_VALIDATOR_IOU = read_env_float("CYBERSHIELD_HEAVY_VALIDATOR_IOU", 0.45, minimum=0.1, maximum=0.95)
HEAVY_VALIDATOR_INTERVAL = read_env_int("CYBERSHIELD_HEAVY_VALIDATOR_INTERVAL", 2, minimum=1, maximum=12)
ENABLE_SAHI_INFERENCE = read_env_bool("CYBERSHIELD_ENABLE_SAHI_INFERENCE", DEFAULT_ADVANCED_DETECTORS)
SAHI_SLICE_HEIGHT = read_env_int("CYBERSHIELD_SAHI_SLICE_HEIGHT", 512, minimum=256, maximum=1024)
SAHI_SLICE_WIDTH = read_env_int("CYBERSHIELD_SAHI_SLICE_WIDTH", 512, minimum=256, maximum=1024)
SAHI_OVERLAP_HEIGHT = read_env_float("CYBERSHIELD_SAHI_OVERLAP_HEIGHT", 0.2, minimum=0.05, maximum=0.6)
SAHI_OVERLAP_WIDTH = read_env_float("CYBERSHIELD_SAHI_OVERLAP_WIDTH", 0.2, minimum=0.05, maximum=0.6)
SAHI_TRIGGER_MIN_WIDTH = read_env_int("CYBERSHIELD_SAHI_TRIGGER_MIN_WIDTH", 1600, minimum=640, maximum=4096)
SAHI_INTERVAL = read_env_int("CYBERSHIELD_SAHI_INTERVAL", 4, minimum=1, maximum=20)
ENABLE_RTDETR_CONFIRMATION = read_env_bool("CYBERSHIELD_ENABLE_RTDETR_CONFIRMATION", DEFAULT_ADVANCED_DETECTORS)
RTDETR_MODEL_NAME = (os.getenv("CYBERSHIELD_RTDETR_MODEL") or "rtdetr-l.pt").strip() or "rtdetr-l.pt"
RTDETR_MIN_CONF = read_env_float("CYBERSHIELD_RTDETR_MIN_CONF", 0.15, minimum=0.05, maximum=0.9)
RTDETR_IOU = read_env_float("CYBERSHIELD_RTDETR_IOU", 0.45, minimum=0.1, maximum=0.95)
RTDETR_INTERVAL = read_env_int("CYBERSHIELD_RTDETR_INTERVAL", 3, minimum=1, maximum=20)
ENABLE_OSINT_REID = read_env_bool("CYBERSHIELD_ENABLE_OSINT_REID", True)
ENABLE_ADAPTIVE_GOVERNOR = read_env_bool("CYBERSHIELD_ENABLE_ADAPTIVE_GOVERNOR", True)
ADAPTIVE_TARGET_FPS = read_env_float("CYBERSHIELD_ADAPTIVE_TARGET_FPS", 18.0, minimum=8.0, maximum=60.0)
ADAPTIVE_MAX_INFER_MS = read_env_float(
    "CYBERSHIELD_ADAPTIVE_MAX_INFER_MS",
    85.0 if torch.cuda.is_available() else 145.0,
    minimum=15.0,
    maximum=400.0,
)
ADAPTIVE_HYSTERESIS_FRAMES = read_env_int("CYBERSHIELD_ADAPTIVE_HYSTERESIS_FRAMES", 5, minimum=1, maximum=120)

PLATE_RECOGNIZER_API_TOKEN = os.getenv("PLATE_RECOGNIZER_API_TOKEN", "").strip()

DETECTION_MODEL_NAME = resolve_model_path(
    os.getenv("CYBERSHIELD_DETECT_MODEL"),
    BASE_DIR / detector_fallback_name(),
    fallback=detector_fallback_name(),
)
PLATE_MODEL_NAME = resolve_model_path(
    os.getenv("CYBERSHIELD_PLATE_MODEL"),
    BASE_DIR / "weights" / "best.pt",
    fallback=DEFAULT_PLATE_MODEL_URL,
)


class SharedResources:
    _detector: Optional[YOLO] = None
    _plate_detector: Optional[YOLO] = None
    _face_analyzer = None
    _ocr_reader = None
    _paddle_ocr_reader = None
    _heavy_validator: Optional[YOLO] = None
    _rtdetr_validator: Optional[YOLO] = None
    _initialization_errors: Dict[str, str] = {}

    detector_lock = threading.Lock()
    plate_lock = threading.Lock()
    face_lock = threading.Lock()
    init_lock = threading.Lock()

    @classmethod
    def _set_initialization_error(cls, component: str, error: Exception | str) -> None:
        cls._initialization_errors[component] = str(error)

    @classmethod
    def _clear_initialization_error(cls, component: str) -> None:
        cls._initialization_errors.pop(component, None)

    @classmethod
    def _get_initialization_errors(cls) -> Dict[str, str]:
        return dict(cls._initialization_errors)

    @staticmethod
    def _face_cuda_available() -> bool:
        if ort is None:
            return torch.cuda.is_available()
        try:
            providers = ort.get_available_providers()
        except Exception:
            return torch.cuda.is_available()
        return torch.cuda.is_available() and "CUDAExecutionProvider" in providers

    @staticmethod
    def get_runtime_capabilities() -> Dict[str, Any]:
        cuda_available = bool(torch.cuda.is_available())
        face_cuda_available = bool(SharedResources._face_cuda_available())
        return {
            "cuda_available": cuda_available,
            "detector_gpu_ready": cuda_available,
            "face_gpu_ready": face_cuda_available,
            "gpu_ready": cuda_available or face_cuda_available,
        }

    @classmethod
    def get_detector(cls) -> YOLO:
        with cls.init_lock:
            if cls._detector is None:
                print(f"Loading primary detector: {DETECTION_MODEL_NAME}")
                cls._detector = YOLO(DETECTION_MODEL_NAME)
                cls._clear_initialization_error("detector")
            return cls._detector

    @classmethod
    def get_plate_detector(cls) -> Optional[YOLO]:
        with cls.init_lock:
            if cls._plate_detector is None:
                try:
                    print(f"Loading plate detector: {PLATE_MODEL_NAME}")
                    cls._plate_detector = YOLO(PLATE_MODEL_NAME)
                    cls._clear_initialization_error("plate_detector")
                except Exception as exc:
                    print(f"Plate detector unavailable: {exc}")
                    cls._set_initialization_error("plate_detector", exc)
                    cls._plate_detector = None
            return cls._plate_detector

    @classmethod
    def get_heavy_validator(cls) -> Optional[YOLO]:
        if not ENABLE_HEAVY_VALIDATOR:
            return None
        with cls.init_lock:
            if cls._heavy_validator is None:
                try:
                    print(f"Loading heavy validator: {HEAVY_VALIDATOR_MODEL}")
                    cls._heavy_validator = YOLO(HEAVY_VALIDATOR_MODEL)
                    cls._clear_initialization_error("heavy_validator")
                except Exception as exc:
                    print(f"Heavy validator unavailable: {exc}")
                    cls._set_initialization_error("heavy_validator", exc)
                    cls._heavy_validator = None
            return cls._heavy_validator

    @classmethod
    def get_rtdetr_validator(cls) -> Optional[YOLO]:
        if not ENABLE_RTDETR_CONFIRMATION:
            return None
        with cls.init_lock:
            if cls._rtdetr_validator is None:
                try:
                    print(f"Loading RT-DETR validator: {RTDETR_MODEL_NAME}")
                    cls._rtdetr_validator = YOLO(RTDETR_MODEL_NAME)
                    cls._clear_initialization_error("rtdetr_validator")
                except Exception as exc:
                    print(f"RT-DETR validator unavailable: {exc}")
                    cls._set_initialization_error("rtdetr_validator", exc)
                    cls._rtdetr_validator = None
            return cls._rtdetr_validator

    @classmethod
    def get_face_analyzer(cls):
        if not HAS_INSIGHTFACE:
            cls._set_initialization_error("face_analyzer", "InsightFace is not installed.")
            return None
        if FaceAnalysis is None:
            cls._set_initialization_error("face_analyzer", "InsightFace FaceAnalysis is unavailable.")
            return None
        with cls.init_lock:
            if cls._face_analyzer is None:
                try:
                    print("Loading ArcFace analyzer (buffalo_l)")
                    cls._face_analyzer = FaceAnalysis(name='buffalo_l')
                    ctx_id = 0 if cls._face_cuda_available() else -1
                    cls._face_analyzer.prepare(ctx_id=ctx_id, det_size=(640, 640))
                    cls._clear_initialization_error("face_analyzer")
                except Exception as exc:
                    print(f"ArcFace unavailable: {exc}")
                    cls._set_initialization_error("face_analyzer", exc)
                    cls._face_analyzer = None
            return cls._face_analyzer

    @classmethod
    def get_ocr_reader(cls):
        if not HAS_EASYOCR or not ENABLE_EASYOCR_FALLBACK:
            reason = "EasyOCR fallback is disabled." if HAS_EASYOCR else "EasyOCR is not installed."
            cls._set_initialization_error("easyocr", reason)
            return None
        if easyocr is None:
            cls._set_initialization_error("easyocr", "EasyOCR module import failed.")
            return None
        with cls.init_lock:
            if cls._ocr_reader is None:
                try:
                    print("Loading EasyOCR reader")
                    cls._ocr_reader = easyocr.Reader(["en"], gpu=torch.cuda.is_available(), verbose=False)
                    cls._clear_initialization_error("easyocr")
                except Exception as exc:
                    print(f"EasyOCR unavailable: {exc}")
                    cls._set_initialization_error("easyocr", exc)
                    cls._ocr_reader = None
            return cls._ocr_reader

    @classmethod
    def get_paddle_ocr_reader(cls):
        if not HAS_PADDLEOCR or not ENABLE_PADDLE_OCR:
            reason = "PaddleOCR is disabled." if HAS_PADDLEOCR else "PaddleOCR is not installed."
            cls._set_initialization_error("paddleocr", reason)
            return None
        if PaddleOCR is None:
            cls._set_initialization_error("paddleocr", "PaddleOCR module import failed.")
            return None
        with cls.init_lock:
            if cls._paddle_ocr_reader is None:
                try:
                    print("Loading PaddleOCR reader")
                    cls._paddle_ocr_reader = PaddleOCR(
                        lang="en",
                        use_textline_orientation=True,
                    )
                    cls._clear_initialization_error("paddleocr")
                except Exception as exc:
                    print(f"PaddleOCR unavailable: {exc}")
                    cls._set_initialization_error("paddleocr", exc)
                    cls._paddle_ocr_reader = None
            return cls._paddle_ocr_reader

def warm_shared_resources() -> None:
    SharedResources.get_detector()
    SharedResources.get_plate_detector()
    SharedResources.get_face_analyzer()
    SharedResources.get_paddle_ocr_reader()
    SharedResources.get_ocr_reader()


def get_system_health_snapshot() -> Dict[str, Any]:
    capabilities = SharedResources.get_runtime_capabilities()
    device = "cuda:0" if capabilities["detector_gpu_ready"] else "cpu"
    initialization_errors = SharedResources._get_initialization_errors()
    warnings: list[Dict[str, str]] = []

    if initialization_errors.get("plate_detector"):
        warnings.append(
            {
                "code": "plate_detector_unavailable",
                "severity": "warning",
                "component": "plate_detector",
                "message": initialization_errors["plate_detector"],
            }
        )
    if capabilities["cuda_available"] and not capabilities["face_gpu_ready"] and HAS_INSIGHTFACE:
        warnings.append(
            {
                "code": "face_gpu_fallback",
                "severity": "info",
                "component": "face_analyzer",
                "message": "CUDA is available but InsightFace is running on CPU fallback.",
            }
        )
    if initialization_errors.get("face_analyzer"):
        warnings.append(
            {
                "code": "face_analyzer_unavailable",
                "severity": "warning",
                "component": "face_analyzer",
                "message": initialization_errors["face_analyzer"],
            }
        )
    if initialization_errors.get("paddleocr") and initialization_errors.get("easyocr") and not PLATE_RECOGNIZER_API_TOKEN:
        warnings.append(
            {
                "code": "ocr_unavailable",
                "severity": "error",
                "component": "ocr",
                "message": "No OCR engine is ready. Local OCR and cloud OCR fallback are unavailable.",
            }
        )
    else:
        if initialization_errors.get("paddleocr"):
            warnings.append(
                {
                    "code": "paddleocr_unavailable",
                    "severity": "info",
                    "component": "paddleocr",
                    "message": initialization_errors["paddleocr"],
                }
            )
        if initialization_errors.get("easyocr"):
            warnings.append(
                {
                    "code": "easyocr_unavailable",
                    "severity": "info",
                    "component": "easyocr",
                    "message": initialization_errors["easyocr"],
                }
            )

    return {
        "device": device,
        "cuda_available": capabilities["cuda_available"],
        "gpu_ready": capabilities["gpu_ready"],
        "detector_gpu_ready": capabilities["detector_gpu_ready"],
        "face_gpu_ready": capabilities["face_gpu_ready"],
        "paddle_ocr_available": bool(HAS_PADDLEOCR and ENABLE_PADDLE_OCR),
        "easyocr_available": bool(HAS_EASYOCR and ENABLE_EASYOCR_FALLBACK),
        "face_available": bool(HAS_INSIGHTFACE),
        "detector_ready": SharedResources._detector is not None,
        "plate_detector_ready": SharedResources._plate_detector is not None,
        "face_analyzer_ready": SharedResources._face_analyzer is not None,
        "paddle_ocr_ready": SharedResources._paddle_ocr_reader is not None,
        "easyocr_ready": SharedResources._ocr_reader is not None,
        "cloud_ocr_ready": bool(PLATE_RECOGNIZER_API_TOKEN),
        "ocr_ready": bool(
            SharedResources._paddle_ocr_reader is not None
            or SharedResources._ocr_reader is not None
            or PLATE_RECOGNIZER_API_TOKEN
        ),
        "warnings": warnings,
        "models": {
            "detector_model": DETECTION_MODEL_NAME,
            "plate_model": PLATE_MODEL_NAME,
        },
    }


def has_any_ocr_path() -> bool:
    local_enabled = (HAS_PADDLEOCR and ENABLE_PADDLE_OCR) or (HAS_EASYOCR and ENABLE_EASYOCR_FALLBACK)
    return bool(local_enabled or PLATE_RECOGNIZER_API_TOKEN)


class VideoPipeline:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.device = "cuda:0" if self.gpu_available() else "cpu"
        self.detector = SharedResources.get_detector()
        self.plate_detector = SharedResources.get_plate_detector()
        self.face_analyzer = SharedResources.get_face_analyzer()

        self.tracker = sv.ByteTrack(
            track_activation_threshold=TRACK_ACTIVATION_THRESHOLD,
            lost_track_buffer=TRACK_LOST_BUFFER,
            minimum_matching_threshold=TRACK_MATCHING_THRESHOLD,
            frame_rate=TRACK_FRAME_RATE,
            minimum_consecutive_frames=TRACK_MIN_CONSECUTIVE_FRAMES,
        )
        self.state_lock = threading.RLock()
        self.plate_executor = concurrent.futures.ThreadPoolExecutor(max_workers=PLATE_EXECUTOR_WORKERS)
        self.face_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.db_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.watchlist_dir = BASE_DIR / "watchlist"
        self.ocr_reader = SharedResources.get_ocr_reader()
        self.paddle_ocr_reader = SharedResources.get_paddle_ocr_reader()

        self.track_states: Dict[int, Dict[str, Any]] = {}
        self.render_tracks: Dict[int, Dict[str, Any]] = {}
        self.face_results: Dict[int, Dict[str, Any]] = {}
        self.plate_results: Dict[int, Dict[str, Any]] = {}
        self.plate_votes: Dict[int, Dict[str, Dict[str, float]]] = {}
        self.mmc_votes: Dict[int, Dict[str, Dict[str, float]]] = {}
        self.detected_plate_texts: Dict[str, float] = {}
        self.analyzed_face_track_ids: Dict[int, float] = {}
        self.last_seen: Dict[int, float] = {}
        self.last_face_attempt: Dict[int, float] = {}
        self.last_plate_attempt: Dict[int, float] = {}
        self.pending_tasks: set[str] = set()
        self.pending_plate_futures: set[concurrent.futures.Future[Any]] = set()
        self.pending_face_futures: set[concurrent.futures.Future[Any]] = set()
        self.pending_db_futures: set[concurrent.futures.Future[Any]] = set()
        self.last_metric_write = 0.0
        self.last_low_confidence_log: Dict[int, float] = {}
        self.rider_proxy_track_ids: Dict[int, float] = {}
        self._cached_watchlist_embeddings: Dict[str, Optional[np.ndarray]] = {}
        self._cached_watchlist_signature: tuple[tuple[str, int, int], ...] = ()
        self._plate_api_disabled_until = 0.0
        self.face_match_threshold = FACE_MATCH_THRESHOLD
        self._gemini_model = None
        self._gemini_failures = 0
        self._heavy_validator_failures = 0
        self._rtdetr_failures = 0
        self._sahi_failures = 0
        self._frame_counter = 0
        self._sahi_model = None
        self.gemini_enabled = bool(ENABLE_GEMINI_ENRICHMENT and HAS_GEMINI and GEMINI_API_KEY)
        self.heavy_validator = SharedResources.get_heavy_validator() if ENABLE_HEAVY_VALIDATOR else None
        self.rtdetr_validator = SharedResources.get_rtdetr_validator() if ENABLE_RTDETR_CONFIRMATION else None
        self.sahi_enabled = bool(ENABLE_SAHI_INFERENCE and HAS_SAHI)
        self._base_heavy_enabled = self.heavy_validator is not None
        self._base_rtdetr_enabled = self.rtdetr_validator is not None
        self._base_sahi_enabled = self.sahi_enabled
        self.adaptive_governor_enabled = bool(ENABLE_ADAPTIVE_GOVERNOR)
        self._adaptive_mode = "normal"
        self._adaptive_pending_mode = "normal"
        self._adaptive_pending_frames = 0
        self._adaptive_target_fps = ADAPTIVE_TARGET_FPS if self.device != "cpu" else max(10.0, ADAPTIVE_TARGET_FPS - 4.0)
        self._adaptive_max_infer_ms = ADAPTIVE_MAX_INFER_MS
        self._adaptive_infer_ema_ms = ADAPTIVE_MAX_INFER_MS * 0.7
        self._last_detection_latency_ms = 0.0
        self._effective_sahi_enabled = self._base_sahi_enabled
        self._effective_heavy_enabled = self._base_heavy_enabled
        self._effective_rtdetr_enabled = self._base_rtdetr_enabled
        self._effective_sahi_interval = max(1, SAHI_INTERVAL)
        self._effective_heavy_interval = max(1, HEAVY_VALIDATOR_INTERVAL)
        self._effective_rtdetr_interval = max(1, RTDETR_INTERVAL)
        self._effective_plate_scan_interval = PLATE_SCAN_INTERVAL_SECONDS
        self._effective_plate_refresh_interval = PLATE_REFRESH_INTERVAL_SECONDS
        self._effective_face_scan_interval = FACE_SCAN_INTERVAL_SECONDS
        self._effective_gemini_enabled = self.gemini_enabled
        self.osint_service = None
        if ENABLE_OSINT_REID:
            try:
                from osint_reid.service import get_osint_service

                self.osint_service = get_osint_service()
            except Exception as exc:
                print(f"OSINT/ReID service unavailable: {exc}")
                self.osint_service = None

        if ENABLE_GEMINI_ENRICHMENT and not HAS_GEMINI:
            print("Gemini enrichment enabled but google-generativeai is not installed.")
        if ENABLE_GEMINI_ENRICHMENT and not GEMINI_API_KEY:
            print("Gemini enrichment enabled but GEMINI_API_KEY is missing.")
        if ENABLE_SAHI_INFERENCE and not HAS_SAHI:
            print("SAHI inference enabled but sahi is not installed.")

    @staticmethod
    def gpu_available() -> bool:
        return torch.cuda.is_available()

    def shutdown(self) -> None:
        self.plate_executor.shutdown(wait=False, cancel_futures=True)
        self.face_executor.shutdown(wait=False, cancel_futures=True)
        self.db_executor.shutdown(wait=False, cancel_futures=True)

    def snapshot_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        with self.state_lock:
            return copy.deepcopy(state)

    @staticmethod
    def _normalize_gender(value: Optional[str]) -> str:
        if not value:
            return "Unknown"
        normalized = value.strip().lower()
        if normalized in {"man", "male"}:
            return "Man"
        if normalized in {"woman", "female"}:
            return "Woman"
        return "Unknown"

    @staticmethod
    def _estimate_density(people_count: int, frame_width: int, frame_height: int) -> str:
        if frame_width <= 0 or frame_height <= 0:
            return "Low"
        area_megapixels = max((frame_width * frame_height) / 1_000_000.0, 0.5)
        density_score = people_count / area_megapixels
        if density_score < 0.75:
            return "Low"
        if density_score < 2.25:
            return "Medium"
        return "High"

    @staticmethod
    def _format_clock(timestamp: Optional[float] = None) -> str:
        return time.strftime("%H:%M:%S", time.localtime(timestamp or time.time()))

    @staticmethod
    def _render_track_ttl(state: Dict[str, Any]) -> float:
        latency_seconds = max(float(state.get("inference_latency_ms") or 0.0) / 1000.0, 0.0)
        analytics_fps = max(float(state.get("analytics_fps") or 0.0), 0.0)
        analytics_interval = (1.0 / analytics_fps) if analytics_fps > 0.0 else 0.0
        ttl = max(
            RENDER_TRACK_TTL_SECONDS,
            latency_seconds * RENDER_TRACK_LATENCY_MULTIPLIER,
            analytics_interval * 2.0,
        )
        return min(ttl, RENDER_TRACK_MAX_TTL_SECONDS)

    @staticmethod
    def _box_overlaps(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int], margin: int = 18) -> bool:
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        return not (
            (ax2 + margin) < bx1
            or (bx2 + margin) < ax1
            or (ay2 + margin) < by1
            or (by2 + margin) < ay1
        )

    @staticmethod
    def _watchlist_has_images(watchlist_dir: Path) -> bool:
        return watchlist_dir.exists() and any(
            path.suffix.lower() in WATCHLIST_SUFFIXES for path in watchlist_dir.iterdir() if path.is_file()
        )

    def _watchlist_signature(self) -> tuple[tuple[str, int, int], ...]:
        if not self.watchlist_dir.exists():
            return ()
        signature: list[tuple[str, int, int]] = []
        for path in sorted(self.watchlist_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in WATCHLIST_SUFFIXES:
                continue
            stat = path.stat()
            signature.append((path.name, stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def _refresh_watchlist_cache(self) -> None:
        signature = self._watchlist_signature()
        if signature == self._cached_watchlist_signature:
            return

        refreshed: Dict[str, Optional[np.ndarray]] = {}
        for filename, _, _ in signature:
            path = self.watchlist_dir / filename
            target_img = cv2.imread(str(path))
            if target_img is None:
                refreshed[path.stem] = None
                continue
            target_rgb = cv2.cvtColor(target_img, cv2.COLOR_BGR2RGB)
            with SharedResources.face_lock:
                if not self.face_analyzer:
                    refreshed[path.stem] = None
                    continue
                faces = self.face_analyzer.get(target_rgb)
            refreshed[path.stem] = faces[0].embedding if faces else None

        self._cached_watchlist_embeddings = refreshed
        self._cached_watchlist_signature = signature

    @staticmethod
    def _compose_vehicle_label(class_name: str, make: str, model: str, color: str) -> str:
        if make and make != "Unknown":
            parts = [part for part in [color, make, model] if part and part != "Unknown"]
            return f"{' '.join(parts)} ({class_name.capitalize()})".strip()
        return class_name.capitalize()

    def _drop_future(self, bucket: set[concurrent.futures.Future[Any]], future: concurrent.futures.Future[Any]) -> None:
        with self.state_lock:
            bucket.discard(future)

    def _submit_executor_task(
        self,
        executor: concurrent.futures.ThreadPoolExecutor,
        future_bucket: set[concurrent.futures.Future[Any]],
        queue_limit: int,
        func,
        *args,
    ) -> bool:
        with self.state_lock:
            if len(future_bucket) >= queue_limit:
                return False
            try:
                future = executor.submit(func, *args)
            except RuntimeError:
                return False
            future_bucket.add(future)
        future.add_done_callback(lambda done_future: self._drop_future(future_bucket, done_future))
        return True

    def _submit_db_task(self, func, *args) -> None:
        try:
            self._submit_executor_task(self.db_executor, self.pending_db_futures, DB_QUEUE_LIMIT, func, *args)
        except RuntimeError:
            return

    def _push_recent(self, state: Dict[str, Any], key: str, item: Dict[str, Any], unique_field: str) -> None:
        bucket = state[key]
        bucket[:] = [existing for existing in bucket if existing.get(unique_field) != item.get(unique_field)]
        bucket.insert(0, item)
        del bucket[10:]

    def _append_event(self, state: Dict[str, Any], event_type: str, detail: str) -> None:
        event = {
            "camera_id": self.camera_id,
            "time": self._format_clock(),
            "type": event_type,
            "detail": detail,
        }
        event = self.enrich_with_gemini(event, "event")
        enriched_detail = detail
        gemini_block = event.get("gemini")
        if isinstance(gemini_block, dict) and gemini_block.get("summary"):
            enriched_detail = f"{detail} | AI: {str(gemini_block.get('summary'))[:180]}"
            event["detail"] = enriched_detail
        state["event_logs"].insert(0, event)
        del state["event_logs"][50:]
        self._submit_db_task(log_event, self.camera_id, event_type, enriched_detail)

    @staticmethod
    def _empty_detections() -> sv.Detections:
        return sv.Detections(
            xyxy=np.empty((0, 4), dtype=np.float32),
            confidence=np.empty((0,), dtype=np.float32),
            class_id=np.empty((0,), dtype=np.int64),
        )

    def _predict_primary(self, frame: np.ndarray) -> sv.Detections:
        with SharedResources.detector_lock:
            with torch.inference_mode():
                results = self.detector.predict(
                    source=frame,
                    conf=DETECTION_CONFIDENCE,
                    imgsz=DETECTION_IMAGE_SIZE,
                    classes=list(TARGET_CLASSES.keys()),
                    device=self.device,
                    half=(str(self.device) != "cpu"),
                    verbose=False,
                )
        return sv.Detections.from_ultralytics(results[0])

    def _should_use_sahi(self, frame: np.ndarray) -> bool:
        if not self._effective_sahi_enabled:
            return False
        if self._frame_counter % self._effective_sahi_interval != 0:
            return False
        frame_height, frame_width = frame.shape[:2]
        return frame_width >= SAHI_TRIGGER_MIN_WIDTH and frame_height >= 360

    def _determine_adaptive_mode(self, analytics_fps: float) -> str:
        fps = max(float(analytics_fps or 0.0), 0.0)
        infer_ms = max(float(self._adaptive_infer_ema_ms or 0.0), 0.0)
        pressure_fps = self._adaptive_target_fps * 0.88
        caution_fps = self._adaptive_target_fps * 0.98

        if fps > 0.0:
            if fps < pressure_fps or infer_ms > (self._adaptive_max_infer_ms * 1.15):
                return "pressure"
            if fps < caution_fps or infer_ms > (self._adaptive_max_infer_ms * 0.92):
                return "caution"
            return "normal"

        if infer_ms > (self._adaptive_max_infer_ms * 1.15):
            return "pressure"
        if infer_ms > (self._adaptive_max_infer_ms * 0.92):
            return "caution"
        return "normal"

    def _apply_adaptive_policy(self) -> None:
        if not self.adaptive_governor_enabled:
            self._effective_sahi_enabled = self._base_sahi_enabled
            self._effective_heavy_enabled = self._base_heavy_enabled
            self._effective_rtdetr_enabled = self._base_rtdetr_enabled
            self._effective_sahi_interval = max(1, SAHI_INTERVAL)
            self._effective_heavy_interval = max(1, HEAVY_VALIDATOR_INTERVAL)
            self._effective_rtdetr_interval = max(1, RTDETR_INTERVAL)
            self._effective_plate_scan_interval = PLATE_SCAN_INTERVAL_SECONDS
            self._effective_plate_refresh_interval = PLATE_REFRESH_INTERVAL_SECONDS
            self._effective_face_scan_interval = FACE_SCAN_INTERVAL_SECONDS
            self._effective_gemini_enabled = bool(getattr(self, "gemini_enabled", False))
            return

        mode = self._adaptive_mode
        if mode == "pressure":
            self._effective_sahi_enabled = False
            self._effective_heavy_enabled = self._base_heavy_enabled
            self._effective_rtdetr_enabled = False
            self._effective_sahi_interval = max(8, SAHI_INTERVAL * 4)
            self._effective_heavy_interval = max(6, HEAVY_VALIDATOR_INTERVAL * 3)
            self._effective_rtdetr_interval = max(8, RTDETR_INTERVAL * 4)
            self._effective_plate_scan_interval = PLATE_SCAN_INTERVAL_SECONDS * 3.0
            self._effective_plate_refresh_interval = PLATE_REFRESH_INTERVAL_SECONDS * 2.0
            self._effective_face_scan_interval = FACE_SCAN_INTERVAL_SECONDS * 2.0
            self._effective_gemini_enabled = False
            return

        if mode == "caution":
            self._effective_sahi_enabled = self._base_sahi_enabled
            self._effective_heavy_enabled = self._base_heavy_enabled
            self._effective_rtdetr_enabled = self._base_rtdetr_enabled and self.device != "cpu"
            self._effective_sahi_interval = max(SAHI_INTERVAL + 1, SAHI_INTERVAL * 2)
            self._effective_heavy_interval = max(HEAVY_VALIDATOR_INTERVAL + 1, HEAVY_VALIDATOR_INTERVAL * 2)
            self._effective_rtdetr_interval = max(RTDETR_INTERVAL + 2, RTDETR_INTERVAL * 2)
            self._effective_plate_scan_interval = PLATE_SCAN_INTERVAL_SECONDS * 1.5
            self._effective_plate_refresh_interval = PLATE_REFRESH_INTERVAL_SECONDS * 1.5
            self._effective_face_scan_interval = FACE_SCAN_INTERVAL_SECONDS * 1.5
            self._effective_gemini_enabled = bool(getattr(self, "gemini_enabled", False)) and self.device != "cpu"
            return

        self._effective_sahi_enabled = self._base_sahi_enabled
        self._effective_heavy_enabled = self._base_heavy_enabled
        self._effective_rtdetr_enabled = self._base_rtdetr_enabled
        self._effective_sahi_interval = max(1, SAHI_INTERVAL)
        self._effective_heavy_interval = max(1, HEAVY_VALIDATOR_INTERVAL)
        self._effective_rtdetr_interval = max(1, RTDETR_INTERVAL)
        self._effective_plate_scan_interval = PLATE_SCAN_INTERVAL_SECONDS
        self._effective_plate_refresh_interval = PLATE_REFRESH_INTERVAL_SECONDS
        self._effective_face_scan_interval = FACE_SCAN_INTERVAL_SECONDS
        self._effective_gemini_enabled = bool(getattr(self, "gemini_enabled", False))

    def _update_adaptive_governor(self, state: Dict[str, Any]) -> None:
        if not self.adaptive_governor_enabled:
            self._adaptive_mode = "disabled"
            self._adaptive_pending_mode = "disabled"
            self._adaptive_pending_frames = 0
            self._apply_adaptive_policy()
            return

        desired_mode = self._determine_adaptive_mode(float(state.get("analytics_fps") or 0.0))
        if desired_mode == self._adaptive_mode:
            self._adaptive_pending_mode = desired_mode
            self._adaptive_pending_frames = 0
            self._apply_adaptive_policy()
            return

        if desired_mode != self._adaptive_pending_mode:
            self._adaptive_pending_mode = desired_mode
            self._adaptive_pending_frames = 1
        else:
            self._adaptive_pending_frames += 1

        if self._adaptive_pending_frames >= ADAPTIVE_HYSTERESIS_FRAMES:
            self._adaptive_mode = desired_mode
            self._adaptive_pending_frames = 0
        self._apply_adaptive_policy()

    def _predict_with_sahi(self, frame: np.ndarray) -> sv.Detections:
        if not self.sahi_enabled or AutoDetectionModel is None or get_sliced_prediction is None:
            return self._predict_primary(frame)
        try:
            if self._sahi_model is None:
                self._sahi_model = AutoDetectionModel.from_pretrained(
                    model_type="ultralytics",
                    model_path=DETECTION_MODEL_NAME,
                    confidence_threshold=DETECTION_CONFIDENCE,
                    device=self.device,
                )

            prediction = get_sliced_prediction(
                image=frame,
                detection_model=self._sahi_model,
                slice_height=SAHI_SLICE_HEIGHT,
                slice_width=SAHI_SLICE_WIDTH,
                overlap_height_ratio=SAHI_OVERLAP_HEIGHT,
                overlap_width_ratio=SAHI_OVERLAP_WIDTH,
            )

            object_predictions = prediction.object_prediction_list or []
            if not object_predictions:
                return self._empty_detections()

            boxes = []
            scores = []
            classes = []
            for obj in object_predictions:
                class_id = int(getattr(obj.category, "id", -1))
                if class_id not in TARGET_CLASSES:
                    continue
                box = obj.bbox
                boxes.append([float(box.minx), float(box.miny), float(box.maxx), float(box.maxy)])
                scores.append(float(obj.score.value))
                classes.append(class_id)

            if not boxes:
                return self._empty_detections()

            return sv.Detections(
                xyxy=np.asarray(boxes, dtype=np.float32),
                confidence=np.asarray(scores, dtype=np.float32),
                class_id=np.asarray(classes, dtype=np.int64),
            )
        except Exception as exc:
            self._sahi_failures += 1
            print(f"SAHI inference failed: {exc}")
            if self._sahi_failures >= 6:
                self.sahi_enabled = False
            return self._predict_primary(frame)

    @staticmethod
    def _expand_box(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        width: int,
        height: int,
        scale_x: float = 0.08,
        scale_y: float = 0.12,
    ) -> tuple[int, int, int, int]:
        box_width = x2 - x1
        box_height = y2 - y1
        pad_x = int(box_width * scale_x)
        pad_y = int(box_height * scale_y)
        return (
            max(x1 - pad_x, 0),
            max(y1 - pad_y, 0),
            min(x2 + pad_x, width),
            min(y2 + pad_y, height),
        )

    @staticmethod
    def _prepare_plate_variants(region) -> list:
        if region.size == 0:
            return []

        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
        if gray.size == 0:
            return []

        scale = max(PLATE_OCR_TARGET_WIDTH / max(gray.shape[1], 1), 1.0)
        interpolation = cv2.INTER_LANCZOS4 if scale > 1.5 else cv2.INTER_CUBIC
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(resized)
        filtered = cv2.bilateralFilter(clahe, 9, 75, 75)
        sharpened = cv2.addWeighted(filtered, 1.45, cv2.GaussianBlur(filtered, (0, 0), 2.0), -0.45, 0)
        adaptive = cv2.adaptiveThreshold(
            sharpened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        # Extra contrast-normalized variant for glare and low-light scenes.
        contrast = cv2.convertScaleAbs(sharpened, alpha=1.65, beta=8)
        sharp_kernel = np.array([[0, -1, 0], [-1, 5.2, -1], [0, -1, 0]], dtype=np.float32)
        contrast_sharp = cv2.filter2D(contrast, -1, sharp_kernel)
        adaptive_inv = cv2.bitwise_not(adaptive)
        _, otsu = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        otsu_inv = cv2.bitwise_not(otsu)
        return [clahe, sharpened, contrast, contrast_sharp, adaptive, adaptive_inv, otsu, otsu_inv]

    @staticmethod
    def _plate_search_windows(vehicle_crop) -> list[tuple[Any, int, int]]:
        height, width = vehicle_crop.shape[:2]
        if height == 0 or width == 0:
            return []

        windows: list[tuple[Any, int, int]] = [(vehicle_crop, 0, 0)]
        if width >= 100 and height >= 50:
            top = int(height * 0.10)
            bottom = min(height, int(height * 0.95))
            left = int(width * 0.04)
            right = min(width, int(width * 0.96))
            focused = vehicle_crop[top:bottom, left:right]
            if focused.size:
                windows.append((focused, left, top))
        return windows

    def _candidate_plate_regions(self, vehicle_crop) -> list[tuple[Any, float]]:
        regions: list[tuple[Any, float]] = []
        height, width = vehicle_crop.shape[:2]
        if height == 0 or width == 0:
            return regions

        if self.plate_detector is not None:
            for window, offset_x, offset_y in self._plate_search_windows(vehicle_crop):
                try:
                    with SharedResources.plate_lock:
                        with torch.inference_mode():
                            plate_results = self.plate_detector.predict(
                                source=window,
                                conf=PLATE_CONFIDENCE,
                                imgsz=PLATE_IMAGE_SIZE,
                                verbose=False,
                                device=self.device,
                                half=(str(self.device) != "cpu"),
                            )
                    if not plate_results:
                        continue
                    boxes = plate_results[0].boxes
                    if boxes is None:
                        continue
                    for box in boxes:
                        confidence = float(box.conf[0])
                        if confidence < PLATE_CONFIDENCE:
                            continue
                        x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
                        left, top, right, bottom = self._expand_box(
                            x1 + offset_x,
                            y1 + offset_y,
                            x2 + offset_x,
                            y2 + offset_y,
                            width,
                            height,
                        )
                        region = vehicle_crop[top:bottom, left:right]
                        if region.size == 0:
                            continue
                        regions.append((region, confidence))
                except Exception:
                    continue

        if regions:
            return regions

        if (
            width < PLATE_HEURISTIC_MIN_VEHICLE_WIDTH
            or height < PLATE_HEURISTIC_MIN_VEHICLE_HEIGHT
        ):
            return regions

        fallback_top = int(height * 0.48)
        fallback_bottom = min(height, int(height * 0.92))
        fallback_left = int(width * 0.08)
        fallback_right = min(width, int(width * 0.92))
        heuristic_region = vehicle_crop[fallback_top:fallback_bottom, fallback_left:fallback_right]
        if heuristic_region.size:
            regions.append((heuristic_region, 0.35))
        return regions

    @staticmethod
    def _vote_plate_candidate(
        candidates: Dict[str, Dict[str, float]],
        normalized_text: str,
        confidence: float,
        region_confidence: float,
    ) -> None:
        bucket = candidates.setdefault(
            normalized_text,
            {"hits": 0.0, "score": 0.0, "confidence": 0.0},
        )
        bucket["hits"] += 1.0
        bucket["score"] += max(float(confidence), 0.0) + max(float(region_confidence), 0.0)
        bucket["confidence"] = max(bucket["confidence"], max(float(confidence), 0.0))

    @staticmethod
    def _finalize_local_vote(
        candidates: Dict[str, Dict[str, float]],
        source: str,
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None
        best_text, best_vote = max(
            candidates.items(),
            key=lambda item: (item[1]["hits"], item[1]["score"], item[1]["confidence"]),
        )
        derived_confidence = min(
            0.99,
            max(best_vote["confidence"], best_vote["score"] / max(best_vote["hits"], 1.0) / 2.0),
        )
        return {
            "text": best_text,
            "confidence": round(derived_confidence, 3),
            "make": "Unknown",
            "model": "",
            "color": "",
            "source": source,
        }

    @staticmethod
    def _iter_paddle_text_candidates(results: Any) -> list[tuple[str, float]]:
        parsed: list[tuple[str, float]] = []
        if not results:
            return parsed

        def add_candidate(text: Any, score: Any) -> None:
            try:
                confidence = float(score or 0.0)
            except (TypeError, ValueError):
                return
            parsed.append((str(text or ""), confidence))

        # Paddle classic output:
        # [[[[x,y]...], (text, score)], ...]
        if isinstance(results, list):
            for item in results:
                if isinstance(item, list):
                    for line in item:
                        if not isinstance(line, (list, tuple)) or len(line) < 2:
                            continue
                        text_conf = line[1]
                        if isinstance(text_conf, (list, tuple)) and len(text_conf) >= 2:
                            add_candidate(text_conf[0], text_conf[1])
                elif isinstance(item, dict):
                    rec_texts = item.get("rec_texts") or []
                    rec_scores = item.get("rec_scores") or []
                    for idx, text in enumerate(rec_texts):
                        score = rec_scores[idx] if idx < len(rec_scores) else 0.0
                        add_candidate(text, score)

        # Paddle structured dict output:
        # {"rec_texts": [...], "rec_scores": [...]}
        if isinstance(results, dict):
            rec_texts = results.get("rec_texts") or []
            rec_scores = results.get("rec_scores") or []
            for idx, text in enumerate(rec_texts):
                score = rec_scores[idx] if idx < len(rec_scores) else 0.0
                add_candidate(text, score)

        return parsed

    def _extract_plate_paddle(self, vehicle_crop) -> Optional[Dict[str, Any]]:
        if vehicle_crop.size == 0 or self.paddle_ocr_reader is None:
            return None

        candidates: Dict[str, Dict[str, float]] = {}
        for region, region_confidence in self._candidate_plate_regions(vehicle_crop):
            variants = self._prepare_plate_variants(region)
            paddle_inputs = [region]
            if variants:
                paddle_inputs.extend(variants[:4])

            for image_input in paddle_inputs:
                try:
                    results = self.paddle_ocr_reader.ocr(image_input, cls=True)
                except Exception:
                    try:
                        results = self.paddle_ocr_reader.ocr(image_input, cls=False)
                    except Exception:
                        continue

                for raw_text, confidence in self._iter_paddle_text_candidates(results):
                    normalized = normalize_plate_text(raw_text)
                    if not normalized:
                        continue
                    if confidence < LOCAL_OCR_MIN_CONFIDENCE:
                        continue
                    self._vote_plate_candidate(candidates, normalized, confidence, region_confidence)

        result = self._finalize_local_vote(candidates, "paddle")
        if result and result["confidence"] >= PADDLE_PRIMARY_MIN_CONFIDENCE:
            return result
        return result

    def _extract_plate_cloud(self, vehicle_crop) -> Optional[Dict[str, Any]]:
        if vehicle_crop.size == 0 or not PLATE_RECOGNIZER_API_TOKEN:
            return None
        if time.time() < self._plate_api_disabled_until:
            return None

        ok, img_encoded = cv2.imencode('.jpg', vehicle_crop)
        if not ok:
            return None

        for attempt in range(3):
            try:
                response = requests.post(
                    'https://api.platerecognizer.com/v1/plate-reader/',
                    headers={'Authorization': f'Token {PLATE_RECOGNIZER_API_TOKEN}'},
                    files={'upload': ('image.jpg', img_encoded.tobytes(), 'image/jpeg')},
                    data={'features': 'mmc', 'regions': 'in'},
                    timeout=15,
                )
                if response.status_code == 429:
                    self._plate_api_disabled_until = time.time() + PLATE_API_COOLDOWN_SECONDS
                    print(
                        "Plate Recognizer quota or rate limit reached; disabling cloud OCR "
                        f"for {PLATE_API_COOLDOWN_SECONDS:.0f}s and falling back to local OCR."
                    )
                    return None
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                print(f"Plate Recognizer API Error: {exc}")
                if attempt == 2:
                    self._plate_api_disabled_until = time.time() + min(PLATE_API_COOLDOWN_SECONDS, 60.0)
                    return None
                time.sleep(2 ** attempt)
        else:
            return None

        data = response.json()
        if not data.get('results'):
            return None

        result = data['results'][0]
        plate_text = normalize_plate_text(result.get('plate', ''))
        if not plate_text:
            return None
        cloud_confidence = float(result.get('score', 0.0) or 0.0)
        if cloud_confidence < CLOUD_OCR_MIN_CONFIDENCE:
            return None

        vehicle_props = result.get('vehicle', {}).get('props', {})

        def pick_attribute(key, fallback_key=None):
            val = result.get(key)
            if not val and fallback_key:
                val = result.get(fallback_key)
            if not val:
                val = vehicle_props.get(key)
            if isinstance(val, list) and len(val) > 0:
                return val[0].get('name', 'Unknown')
            if isinstance(val, str) and val.strip():
                return val
            return 'Unknown'

        make = pick_attribute('make')
        model = pick_attribute('make_model', fallback_key='model')
        color = pick_attribute('color')
        if model != 'Unknown' and make != 'Unknown' and model.lower().startswith(make.lower()):
            model = model[len(make):].strip() or model

        return {
            "text": plate_text,
            "confidence": cloud_confidence,
            "make": make.capitalize(),
            "model": model.capitalize() if model != "Unknown" else "",
            "color": color.capitalize() if color != "Unknown" else "",
            "source": "cloud",
        }

    def _extract_plate_local(self, vehicle_crop) -> Optional[Dict[str, Any]]:
        if vehicle_crop.size == 0 or self.ocr_reader is None:
            return None

        candidates: Dict[str, Dict[str, float]] = {}
        for region, region_confidence in self._candidate_plate_regions(vehicle_crop):
            # Reference approach: plain grayscale first (AarohiSingla/ANPR), then enhanced variants
            raw_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) if region.ndim == 3 else region
            ocr_inputs = [raw_gray] + self._prepare_plate_variants(region)
            for variant in ocr_inputs:
                try:
                    results = self.ocr_reader.readtext(
                        variant,
                        detail=1,
                        paragraph=False,
                    )
                except Exception:
                    continue

                for result in results:
                    if not isinstance(result, (list, tuple)) or len(result) < 3:
                        continue
                    raw_text = str(result[1] or "")
                    confidence = float(result[2] or 0.0)
                    normalized = normalize_plate_text(raw_text)
                    if not normalized or confidence < LOCAL_OCR_MIN_CONFIDENCE:
                        continue
                    self._vote_plate_candidate(candidates, normalized, confidence, region_confidence)

        return self._finalize_local_vote(candidates, "easyocr")

    def _extract_plate_and_mmc(self, vehicle_crop) -> Optional[Dict[str, Any]]:
        paddle_result = self._extract_plate_paddle(vehicle_crop)
        if paddle_result and paddle_result.get("confidence", 0.0) >= PADDLE_PRIMARY_MIN_CONFIDENCE:
            return paddle_result

        easy_result = self._extract_plate_local(vehicle_crop)
        if easy_result and (not paddle_result or easy_result.get("confidence", 0.0) > paddle_result.get("confidence", 0.0)):
            return easy_result

        if paddle_result:
            return paddle_result

        return self._extract_plate_cloud(vehicle_crop)

    @staticmethod
    def _strip_json_fence(raw_text: str) -> str:
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\\s*", "", text)
            text = re.sub(r"\\s*```$", "", text)
        return text.strip()

    @staticmethod
    def _box_iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
        left = max(float(box_a[0]), float(box_b[0]))
        top = max(float(box_a[1]), float(box_b[1]))
        right = min(float(box_a[2]), float(box_b[2]))
        bottom = min(float(box_a[3]), float(box_b[3]))
        if right <= left or bottom <= top:
            return 0.0
        inter = (right - left) * (bottom - top)
        area_a = max((float(box_a[2]) - float(box_a[0])) * (float(box_a[3]) - float(box_a[1])), 0.0)
        area_b = max((float(box_b[2]) - float(box_b[0])) * (float(box_b[3]) - float(box_b[1])), 0.0)
        denom = area_a + area_b - inter
        return (inter / denom) if denom > 0 else 0.0

    def _init_gemini_model(self):
        if not self.gemini_enabled or genai is None:
            return None
        if self._gemini_model is not None:
            return self._gemini_model
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self._gemini_model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        except Exception as exc:
            self._gemini_failures += 1
            print(f"Gemini model initialization failed: {exc}")
            if self._gemini_failures >= 3:
                self.gemini_enabled = False
            return None
        return self._gemini_model

    def enrich_with_gemini(self, record: dict, entity_type: str) -> dict:
        if not self._effective_gemini_enabled:
            return record
        model = self._init_gemini_model()
        if model is None:
            return record

        payload = dict(record)
        prompt = (
            "You are a security analytics assistant. "
            "Return JSON only with keys: summary, risk_level, tags. "
            "risk_level must be one of low, medium, high. "
            f"Entity type: {entity_type}. Input record: {json.dumps(payload, ensure_ascii=True)}"
        )
        try:
            response = model.generate_content(prompt)
            text = self._strip_json_fence(getattr(response, "text", ""))
            if not text:
                return record
            parsed = json.loads(text)
            summary = str(parsed.get("summary") or "").strip()
            risk_level = str(parsed.get("risk_level") or "medium").strip().lower()
            if risk_level not in {"low", "medium", "high"}:
                risk_level = "medium"
            tags = parsed.get("tags") or []
            if not isinstance(tags, list):
                tags = [str(tags)]
            record["gemini"] = {
                "summary": summary,
                "risk_level": risk_level,
                "tags": [str(tag) for tag in tags[:8]],
                "model": GEMINI_MODEL_NAME,
            }
        except Exception as exc:
            self._gemini_failures += 1
            print(f"Gemini enrichment failed: {exc}")
            if self._gemini_failures >= 5:
                self.gemini_enabled = False
        return record

    def _apply_heavy_validator(self, frame: np.ndarray, detections: sv.Detections) -> sv.Detections:
        if self.heavy_validator is None:
            return detections
        if detections.confidence is None or detections.class_id is None or len(detections) == 0:
            return detections
        if HEAVY_VALIDATOR_MAX_CONF <= HEAVY_VALIDATOR_MIN_CONF:
            return detections

        confidences = np.asarray(detections.confidence)
        low_band = np.where((confidences >= HEAVY_VALIDATOR_MIN_CONF) & (confidences <= HEAVY_VALIDATOR_MAX_CONF))[0]
        if low_band.size == 0:
            return detections

        try:
            with SharedResources.detector_lock:
                with torch.inference_mode():
                    results = self.heavy_validator.predict(
                        source=frame,
                        conf=HEAVY_VALIDATOR_MIN_CONF,
                        imgsz=DETECTION_IMAGE_SIZE,
                        classes=list(TARGET_CLASSES.keys()),
                        device=self.device,
                        half=(str(self.device) != "cpu"),
                        verbose=False,
                    )
            validator_detections = sv.Detections.from_ultralytics(results[0])
            if len(validator_detections) == 0 or validator_detections.class_id is None:
                return detections

            keep_indices = [index for index in range(len(detections)) if index not in set(low_band.tolist())]
            validator_boxes = np.asarray(validator_detections.xyxy)
            validator_classes = np.asarray(validator_detections.class_id)

            for index in low_band.tolist():
                candidate_box = np.asarray(detections.xyxy[index])
                candidate_class = int(detections.class_id[index])
                class_matches = np.where(validator_classes == candidate_class)[0]
                best_iou = 0.0
                for match_idx in class_matches.tolist():
                    best_iou = max(best_iou, self._box_iou(candidate_box, validator_boxes[match_idx]))
                if best_iou >= HEAVY_VALIDATOR_IOU:
                    keep_indices.append(index)

            if len(keep_indices) == len(detections):
                return detections
            if not keep_indices:
                return detections
            keep_indices = sorted(set(keep_indices))
            filtered = detections[np.array(keep_indices)]
            if isinstance(filtered, sv.Detections):
                return filtered
            return detections
        except Exception as exc:
            self._heavy_validator_failures += 1
            print(f"Heavy validator failed: {exc}")
            if self._heavy_validator_failures >= 6:
                self.heavy_validator = None
            return detections

    def _apply_rtdetr_confirmation(self, frame: np.ndarray, detections: sv.Detections) -> sv.Detections:
        if self.rtdetr_validator is None:
            return detections
        if detections.confidence is None or detections.class_id is None or len(detections) == 0:
            return detections
        if self._frame_counter % RTDETR_INTERVAL != 0:
            return detections

        try:
            with SharedResources.detector_lock:
                with torch.inference_mode():
                    results = self.rtdetr_validator.predict(
                        source=frame,
                        conf=RTDETR_MIN_CONF,
                        imgsz=DETECTION_IMAGE_SIZE,
                        classes=list(TARGET_CLASSES.keys()),
                        device=self.device,
                        half=(str(self.device) != "cpu"),
                        verbose=False,
                    )
            rtdetr_detections = sv.Detections.from_ultralytics(results[0])
            if len(rtdetr_detections) == 0 or rtdetr_detections.class_id is None:
                return detections

            keep_indices: list[int] = []
            rtdetr_boxes = np.asarray(rtdetr_detections.xyxy)
            rtdetr_classes = np.asarray(rtdetr_detections.class_id)
            for index in range(len(detections)):
                class_id = int(detections.class_id[index])
                box = np.asarray(detections.xyxy[index])
                class_matches = np.where(rtdetr_classes == class_id)[0]
                best_iou = 0.0
                for match_idx in class_matches.tolist():
                    best_iou = max(best_iou, self._box_iou(box, rtdetr_boxes[match_idx]))
                if best_iou >= RTDETR_IOU or float(detections.confidence[index]) >= max(HEAVY_VALIDATOR_MAX_CONF, 0.5):
                    keep_indices.append(index)

            if not keep_indices:
                return detections
            if len(keep_indices) == len(detections):
                return detections

            filtered = detections[np.asarray(sorted(set(keep_indices)), dtype=np.int64)]
            if isinstance(filtered, sv.Detections):
                return filtered
            return detections
        except Exception as exc:
            self._rtdetr_failures += 1
            print(f"RT-DETR confirmation failed: {exc}")
            if self._rtdetr_failures >= 6:
                self.rtdetr_validator = None
            return detections

    def get_runtime_status(self) -> Dict[str, Any]:
        cooldown = max(self._plate_api_disabled_until - time.time(), 0.0)
        paddle_ready = self.paddle_ocr_reader is not None
        easy_ready = self.ocr_reader is not None
        cloud_ready = bool(PLATE_RECOGNIZER_API_TOKEN)
        warnings: list[Dict[str, str | float]] = []
        if cooldown > 0.0:
            warnings.append(
                {
                    "code": "cloud_ocr_cooldown",
                    "severity": "warning",
                    "component": "cloud_ocr",
                    "message": "Cloud OCR fallback is temporarily cooling down after a recent failure.",
                    "cooldown_seconds": round(cooldown, 1),
                }
            )
        return {
            "plate_detector_ready": self.plate_detector is not None,
            "paddle_ocr_ready": paddle_ready,
            "easyocr_ready": easy_ready,
            "cloud_ocr_ready": cloud_ready,
            "ocr_fallback_ready": bool(paddle_ready or easy_ready or cloud_ready),
            "cloud_ocr_cooldown_seconds": round(cooldown, 1),
            "gemini_enabled": self.gemini_enabled,
            "heavy_validator_enabled": self.heavy_validator is not None,
            "sahi_enabled": self.sahi_enabled,
            "rtdetr_confirmation_enabled": self.rtdetr_validator is not None,
            "adaptive_governor_enabled": self.adaptive_governor_enabled,
            "adaptive_mode": self._adaptive_mode,
            "adaptive_pending_mode": self._adaptive_pending_mode,
            "adaptive_pending_frames": self._adaptive_pending_frames,
            "adaptive_target_fps": round(self._adaptive_target_fps, 2),
            "adaptive_max_infer_ms": round(self._adaptive_max_infer_ms, 2),
            "detector_latency_ms": round(self._last_detection_latency_ms, 2),
            "detector_latency_ema_ms": round(self._adaptive_infer_ema_ms, 2),
            "effective_sahi_enabled": self._effective_sahi_enabled,
            "effective_heavy_validator_enabled": self._effective_heavy_enabled,
            "effective_rtdetr_enabled": self._effective_rtdetr_enabled,
            "effective_sahi_interval": self._effective_sahi_interval,
            "effective_heavy_validator_interval": self._effective_heavy_interval,
            "effective_rtdetr_interval": self._effective_rtdetr_interval,
            "warnings": warnings,
        }

    def _match_watchlist(self, embedding) -> Optional[str]:
        if not self._watchlist_has_images(self.watchlist_dir) or embedding is None:
            return None

        self._refresh_watchlist_cache()

        best_match_name = None
        best_distance = float('inf')
        threshold = self.face_match_threshold

        for match_name, target_embedding in self._cached_watchlist_embeddings.items():
            if target_embedding is None:
                continue
            dist = float(np.linalg.norm(embedding - target_embedding))
            if dist < best_distance:
                best_distance = dist
                best_match_name = match_name

        if best_distance < threshold:
            return best_match_name
        return None

    def _schedule_plate_task(
        self,
        frame,
        state: Dict[str, Any],
        tracker_id: int,
        class_name: str,
        box: tuple[int, int, int, int],
    ) -> None:
        task_id = f"plate:{tracker_id}"
        now = time.time()
        with self.state_lock:
            if task_id in self.pending_tasks:
                return
            refresh_interval = (
                self._effective_plate_refresh_interval
                if tracker_id in self.plate_results
                else self._effective_plate_scan_interval
            )
            if now - self.last_plate_attempt.get(tracker_id, 0.0) < refresh_interval:
                return
            self.pending_tasks.add(task_id)
            self.last_plate_attempt[tracker_id] = now

        x1, y1, x2, y2 = box
        # Implement 15% padding for vehicle crops to improve MMC accuracy
        h, w = frame.shape[:2]
        px1, py1, px2, py2 = self._expand_box(x1, y1, x2, y2, w, h, scale_x=0.15, scale_y=0.15)
        vehicle_crop = frame[py1:py2, px1:px2].copy()
        
        if vehicle_crop.size == 0:
            with self.state_lock:
                self.pending_tasks.discard(task_id)
            return
        if not self._submit_executor_task(
            self.plate_executor,
            self.pending_plate_futures,
            PLATE_QUEUE_LIMIT,
            self._process_plate_async,
            vehicle_crop,
            state,
            tracker_id,
            class_name,
        ):
            with self.state_lock:
                self.pending_tasks.discard(task_id)

    def _schedule_face_task(
        self,
        frame,
        state: Dict[str, Any],
        tracker_id: int,
        box: tuple[int, int, int, int],
    ) -> None:
        task_id = f"face:{tracker_id}"
        now = time.time()
        with self.state_lock:
            if task_id in self.pending_tasks:
                return
            if now - self.last_face_attempt.get(tracker_id, 0.0) < self._effective_face_scan_interval:
                return
            self.pending_tasks.add(task_id)
            self.last_face_attempt[tracker_id] = now

        x1, y1, x2, y2 = box
        clip_x1 = max(x1, 0)
        clip_y1 = max(y1, 0)
        clip_x2 = min(x2, frame.shape[1])
        clip_y2 = min(y2, frame.shape[0])
        person_crop = frame[clip_y1:clip_y2, clip_x1:clip_x2].copy()
        if person_crop.size == 0:
            with self.state_lock:
                self.pending_tasks.discard(task_id)
            return
        if not self._submit_executor_task(
            self.face_executor,
            self.pending_face_futures,
            FACE_QUEUE_LIMIT,
            self._process_face_async,
            person_crop,
            (clip_x1, clip_y1),
            state,
            tracker_id,
        ):
            with self.state_lock:
                self.pending_tasks.discard(task_id)

    @staticmethod
    def _is_plate_vote_confirmed(vote: Dict[str, float]) -> bool:
        hits = float(vote.get("hits", 0.0) or 0.0)
        best_confidence = float(vote.get("best_confidence", 0.0) or 0.0)
        score = float(vote.get("score", 0.0) or 0.0)
        direct_accept = best_confidence >= PLATE_DIRECT_ACCEPT_CONFIDENCE and hits >= 1.0
        aggregate_accept = hits >= float(PLATE_CONFIRMATION_HITS) and score >= PLATE_MIN_AGGREGATE_SCORE
        return direct_accept or aggregate_accept

    def _process_plate_async(
        self,
        vehicle_crop,
        state: Dict[str, Any],
        tracker_id: int,
        class_name: str,
    ) -> None:
        try:
            mmc_data = self._extract_plate_and_mmc(vehicle_crop)
            if not mmc_data or not mmc_data["text"]:
                return

            plate_text = normalize_plate_text(str(mmc_data.get("text") or ""))
            if not plate_text:
                return
            plate_confidence = mmc_data["confidence"]
            vehicle_type_enriched = self._compose_vehicle_label(
                class_name,
                mmc_data.get("make", "Unknown"),
                mmc_data.get("model", ""),
                mmc_data.get("color", ""),
            )

            with self.state_lock:
                now = time.time()
                
                # 1. Vote on Plate Text
                vote_bucket = self.plate_votes.setdefault(tracker_id, {})
                vote = vote_bucket.setdefault(
                    plate_text,
                    {"hits": 0.0, "score": 0.0, "best_confidence": 0.0},
                )
                vote["hits"] += 1.0
                vote["score"] += float(plate_confidence or 0.0)
                vote["best_confidence"] = max(vote["best_confidence"], float(plate_confidence or 0.0))

                best_text, best_vote = max(
                    vote_bucket.items(),
                    key=lambda item: (item[1]["hits"], item[1]["score"], item[1]["best_confidence"]),
                )
                
                # 2. Vote on MMC (Make, Model, Color)
                # We vote on the tuple to ensure attribute consistency (e.g. no "Blue Red Toyota")
                mmc_tuple = (mmc_data["make"], mmc_data["model"], mmc_data["color"])
                mmc_bucket = self.mmc_votes.setdefault(tracker_id, {})
                m_vote = mmc_bucket.setdefault(
                    str(mmc_tuple), 
                    {"hits": 0, "make": mmc_data["make"], "model": mmc_data["model"], "color": mmc_data["color"]}
                )
                m_vote["hits"] += 1
                
                best_mmc_raw = max(mmc_bucket.values(), key=lambda v: v["hits"])
                
                # 3. Check Confirmations
                plate_confirmed = self._is_plate_vote_confirmed(best_vote)
                
                # MMC consensus: require at least 2 hits if we have low confidence, or just take the best after 1 if plate is confirmed.
                # However, for stability, we'll prefer the most frequent MMC.
                v_make = str(best_mmc_raw.get("make") or "Unknown")
                v_model = str(best_mmc_raw.get("model") or "")
                v_color = str(best_mmc_raw.get("color") or "")
                
                if not plate_confirmed:
                    self._push_recent(
                        state,
                        "pending_plates",
                        {
                            "tracker_id": tracker_id,
                            "candidate_text": best_text,
                            "hits": int(best_vote["hits"]),
                            "confidence": round(best_vote["best_confidence"], 3),
                            "source": mmc_data.get("source", "unknown"),
                            "time": self._format_clock(),
                        },
                        "tracker_id",
                    )
                    if now - self.last_low_confidence_log.get(tracker_id, 0.0) >= 3.0:
                        self._append_event(
                            state,
                            "ANPR Low Confidence",
                            (
                                f"Pending plate for #{tracker_id}: '{best_text}' "
                                f"hits={int(best_vote['hits'])} conf={best_vote['best_confidence']:.2f}"
                            ),
                        )
                        self.last_low_confidence_log[tracker_id] = now
                    return

                # Construct enriched string from VOTED MMC
                vehicle_type_enriched = self._compose_vehicle_label(class_name, v_make, v_model, v_color)

                state["pending_plates"] = [
                    item for item in state.get("pending_plates", []) if item.get("tracker_id") != tracker_id
                ]

                existing_text = self.plate_results.get(tracker_id, {}).get("text")
                if existing_text == best_text:
                    self.plate_results[tracker_id]["expires"] = now + 8.0
                    touch_timestamp_cache(self.detected_plate_texts, best_text, now)
                    return

                if best_text not in self.detected_plate_texts:
                    state["plates_detected"] += 1
                touch_timestamp_cache(self.detected_plate_texts, best_text, now)

                self.plate_results[tracker_id] = {
                    "text": best_text,
                    "confidence": round(best_vote["best_confidence"], 3),
                    "make": v_make,
                    "model": v_model,
                    "color": v_color,
                    "expires": now + 8.0,
                }
                self._push_recent(
                    state,
                    "recent_plates",
                    self.enrich_with_gemini({
                        "tracker_id": tracker_id,
                        "plate_text": best_text,
                        "vehicle_type": vehicle_type_enriched,
                        "confidence": round(best_vote["best_confidence"], 3),
                        "ocr_source": mmc_data.get("source", "unknown"),
                        "time": self._format_clock(),
                    }, "plate"),
                    "plate_text",
                )
                self._push_recent(
                    state,
                    "recent_vehicles",
                    self.enrich_with_gemini({
                        "tracker_id": tracker_id,
                        "vehicle_type": vehicle_type_enriched,
                        "plate_text": best_text,
                        "confidence": round(best_vote["best_confidence"], 3),
                        "ocr_source": mmc_data.get("source", "unknown"),
                        "time": self._format_clock(),
                    }, "vehicle"),
                    "tracker_id",
                )
                detail = (
                    f"Plate '{best_text}' detected on {class_name} #{tracker_id} "
                    f"via {mmc_data.get('source', 'unknown')}"
                )
                self._append_event(state, "ANPR Match", detail)

            self._submit_db_task(
                upsert_plate_read,
                self.camera_id,
                tracker_id,
                best_text,
                vehicle_type_enriched,
                round(best_vote["best_confidence"], 3),
                mmc_data.get("source", "unknown"),
            )
            self._submit_db_task(
                upsert_vehicle_record,
                self.camera_id,
                tracker_id,
                vehicle_type_enriched,
                best_text,
            )
        finally:
            with self.state_lock:
                self.pending_tasks.discard(f"plate:{tracker_id}")

    def _process_face_async(self, person_crop, crop_origin: tuple[int, int], state: Dict[str, Any], tracker_id: int) -> None:
        try:
            if person_crop.size == 0 or not self.face_analyzer:
                return

            upper_crop = person_crop[: max(int(person_crop.shape[0] * 0.55), 1), :]
            face_rgb = cv2.cvtColor(upper_crop, cv2.COLOR_BGR2RGB)

            with SharedResources.face_lock:
                faces = self.face_analyzer.get(face_rgb)
                
            if not faces:
                return

            best_face = faces[0]
            bbox = best_face.bbox.astype(int)
            fx, fy, fx2, fy2 = bbox.tolist()
            abs_left = max(crop_origin[0] + max(fx, 0), 0)
            abs_top = max(crop_origin[1] + max(fy, 0), 0)
            abs_right = max(crop_origin[0] + max(fx2, 0), abs_left)
            abs_bottom = max(crop_origin[1] + max(fy2, 0), abs_top)

            gender_value = getattr(best_face, "gender", None)
            gender_label = None
            if gender_value == 1:
                gender_label = "man"
            elif gender_value == 0:
                gender_label = "woman"
            gender = self._normalize_gender(gender_label)

            age_value = getattr(best_face, "age", None)
            age = None
            if isinstance(age_value, (int, float)) and 0 <= float(age_value) <= 120:
                age = int(round(float(age_value)))

            embedding = getattr(best_face, "embedding", None)
            match_name = self._match_watchlist(embedding)
            watchlist_hit = bool(match_name)

            with self.state_lock:
                now = time.time()
                cached_face = self.face_results.get(tracker_id)
                previous_gender = cached_face.get("gender") if cached_face else None
                is_new_face = tracker_id not in self.analyzed_face_track_ids
                self.face_results[tracker_id] = {
                    "gender": gender,
                    "age": age,
                    "match_name": match_name,
                    "watchlist_hit": watchlist_hit,
                    "face_box": (abs_left, abs_top, abs_right, abs_bottom),
                    "expires": now + 8.0,
                }
                if is_new_face:
                    state["faces_detected"] += 1
                    if gender in state["gender_stats"]:
                        state["gender_stats"][gender] += 1
                elif previous_gender is None and gender in state["gender_stats"]:
                    state["gender_stats"][gender] += 1
                touch_timestamp_cache(self.analyzed_face_track_ids, tracker_id, now)

                face_record = {
                    "tracker_id": tracker_id,
                    "identity": match_name or "Anonymous",
                    "gender": gender,
                    "age": age,
                    "watchlist_hit": watchlist_hit,
                    "time": self._format_clock(),
                }
                if watchlist_hit or is_new_face:
                    face_record = self.enrich_with_gemini(face_record, "face")
                self._push_recent(state, "recent_faces", face_record, "tracker_id")
                if watchlist_hit:
                    detail = f"Watchlist match '{match_name}' on person #{tracker_id}"
                    self._append_event(state, "Watchlist Alert", detail)
                else:
                    detail = f"Face analytics completed for person #{tracker_id} ({gender})"
                    self._append_event(state, "Face Analytics", detail)

            self._submit_db_task(
                upsert_face_record,
                self.camera_id,
                tracker_id,
                match_name,
                gender,
                age,
                watchlist_hit,
            )
        finally:
            with self.state_lock:
                self.pending_tasks.discard(f"face:{tracker_id}")

    def _cleanup_expired_cache(self) -> None:
        now = time.time()
        stale_track_ids = [track_id for track_id, seen_at in self.last_seen.items() if now - seen_at > TRACK_STALE_SECONDS]
        for track_id in stale_track_ids:
            self.last_seen.pop(track_id, None)
            self.track_states.pop(track_id, None)
            self.render_tracks.pop(track_id, None)
            self.face_results.pop(track_id, None)
            self.plate_results.pop(track_id, None)
            self.plate_votes.pop(track_id, None)
            self.mmc_votes.pop(track_id, None)
            self.last_face_attempt.pop(track_id, None)
            self.last_plate_attempt.pop(track_id, None)
            self.analyzed_face_track_ids.pop(track_id, None)

        self.render_tracks = {
            track_id: result
            for track_id, result in self.render_tracks.items()
            if result.get("expires", 0.0) > now
        }
        self.face_results = {
            track_id: result
            for track_id, result in self.face_results.items()
            if result.get("expires", 0.0) > now
        }
        self.plate_results = {
            track_id: result
            for track_id, result in self.plate_results.items()
            if result.get("expires", 0.0) > now
        }
        trim_timestamp_cache(self.detected_plate_texts, now, UNIQUE_CACHE_TTL_SECONDS, PLATE_CACHE_LIMIT)
        trim_timestamp_cache(self.analyzed_face_track_ids, now, UNIQUE_CACHE_TTL_SECONDS, FACE_TRACK_CACHE_LIMIT)

    @staticmethod
    def _clip_box(frame, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = box
        return (
            max(x1, 0),
            max(y1, 0),
            min(x2, frame.shape[1]),
            min(y2, frame.shape[0]),
        )

    def _annotate_face(self, frame, box: tuple[int, int, int, int], face_result: Optional[Dict[str, Any]]) -> None:
        x1, y1, x2, y2 = box
        if face_result and face_result.get("face_box"):
            face_left, face_top, face_right, face_bottom = face_result["face_box"]
        else:
            width = x2 - x1
            height = y2 - y1
            face_left = x1 + int(width * 0.2)
            face_top = y1
            face_right = x1 + int(width * 0.8)
            face_bottom = y1 + int(height * 0.3)

        face_left = max(face_left, 0)
        face_top = max(face_top, 0)
        face_right = min(face_right, frame.shape[1])
        face_bottom = min(face_bottom, frame.shape[0])

        if face_right <= face_left or face_bottom <= face_top:
            return

        if not face_result or not face_result.get("watchlist_hit"):
            face_region = frame[face_top:face_bottom, face_left:face_right]
            if face_region.size:
                frame[face_top:face_bottom, face_left:face_right] = cv2.GaussianBlur(face_region, (51, 51), 20)

        if face_result and face_result.get("watchlist_hit"):
            label = f"WATCHLIST: {face_result['match_name']}"
            color = (0, 0, 255)
        elif face_result and face_result.get("gender"):
            age = face_result.get("age")
            label = f"{face_result['gender']}" if age is None else f"{face_result['gender']}, {age}"
            color = (255, 0, 255)
        else:
            label = "ANONYMIZED"
            color = (255, 0, 255)

        self._draw_label(frame, label, (x1, max(y1 - 12, 20)), color)

    @staticmethod
    def _draw_label(frame, text: str, anchor: tuple[int, int], color: tuple[int, int, int]) -> None:
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.55
        thickness = 2
        (text_width, text_height), baseline = cv2.getTextSize(text, font, scale, thickness)
        x = max(anchor[0], 0)
        y = max(anchor[1], text_height + baseline + 6)

        left = max(x - 4, 0)
        top = max(y - text_height - baseline - 8, 0)
        right = min(x + text_width + 8, frame.shape[1] - 1)
        bottom = min(y + 2, frame.shape[0] - 1)
        cv2.rectangle(frame, (left, top), (right, bottom), color, -1)
        cv2.putText(frame, text, (x, y - 4), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)

    @staticmethod
    def _draw_zone(frame) -> int:
        frame_height, frame_width = frame.shape[:2]
        zone_y = int(frame_height * 0.55)
        cv2.line(frame, (0, zone_y), (frame_width, zone_y), (0, 165, 255), 2)
        cv2.putText(
            frame,
            "Analytics Zone",
            (12, max(zone_y - 12, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 165, 255),
            2,
        )
        return zone_y

    def _draw_scene(self, frame):
        self._draw_zone(frame)
        with self.state_lock:
            render_tracks = copy.deepcopy(self.render_tracks)
            face_results = copy.deepcopy(self.face_results)
            plate_results = copy.deepcopy(self.plate_results)

        for tracker_id in sorted(render_tracks.keys()):
            render_track = render_tracks[tracker_id]
            box = self._clip_box(frame, render_track["box"])
            x1, y1, x2, y2 = box
            if x2 <= x1 or y2 <= y1:
                continue

            class_name = render_track["class_name"]
            confidence = render_track["confidence"]
            if class_name in VEHICLE_CLASSES:
                label = f"#{tracker_id} {class_name} {confidence:.2f}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), (59, 130, 246), 2)
                self._draw_label(frame, label, (x1, max(y1 - 10, 20)), (59, 130, 246))

                plate_result = plate_results.get(tracker_id)
                if plate_result:
                    self._draw_label(
                        frame,
                        plate_result["text"],
                        (x1, min(y2 + 26, frame.shape[0] - 8)),
                        (0, 180, 255),
                    )
            else:
                face_result = face_results.get(tracker_id)
                self._annotate_face(frame, box, face_result)

                color = (0, 0, 255) if face_result and face_result.get("watchlist_hit") else (34, 197, 94)
                label = f"#{tracker_id} person {confidence:.2f}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                self._draw_label(frame, label, (x1, min(y2 + 26, frame.shape[0] - 8)), color)

        return frame

    def render_frame(self, frame):
        with self.state_lock:
            self._cleanup_expired_cache()
        return self._draw_scene(frame)

    def refresh_track_tasks(self, frame, state: Dict[str, Any]) -> None:
        with self.state_lock:
            self._cleanup_expired_cache()
            render_tracks = copy.deepcopy(self.render_tracks)
            track_states = copy.deepcopy(self.track_states)

        for tracker_id, render_track in render_tracks.items():
            track_state = track_states.get(tracker_id, {})
            if track_state.get("frames_seen", 0) < MIN_STABLE_FRAMES:
                continue

            box = self._clip_box(frame, render_track["box"])
            x1, y1, x2, y2 = box
            if x2 <= x1 or y2 <= y1:
                continue

            class_name = render_track["class_name"]
            if class_name in VEHICLE_CLASSES:
                if (x2 - x1) >= 90 and (y2 - y1) >= 70:
                    self._schedule_plate_task(frame, state, tracker_id, class_name, box)
            elif (x2 - x1) >= 90 and (y2 - y1) >= 120:
                self._schedule_face_task(frame, state, tracker_id, box)

    def process_frame(self, frame, state: Dict[str, Any]):
        frame_height, frame_width = frame.shape[:2]
        zone_y = int(frame_height * 0.55)
        now = time.time()
        render_track_ttl = self._render_track_ttl(state)
        self._frame_counter += 1
        self._update_adaptive_governor(state)

        detection_start = time.perf_counter()
        detections = self._predict_with_sahi(frame) if self._should_use_sahi(frame) else self._predict_primary(frame)
        if (
            self._effective_heavy_enabled
            and self.heavy_validator is not None
            and (self._frame_counter % self._effective_heavy_interval == 0)
        ):
            detections = self._apply_heavy_validator(frame, detections)
        if (
            self._effective_rtdetr_enabled
            and self.rtdetr_validator is not None
            and (self._frame_counter % self._effective_rtdetr_interval == 0)
        ):
            detections = self._apply_rtdetr_confirmation(frame, detections)
        detections = self.tracker.update_with_detections(detections)
        self._last_detection_latency_ms = (time.perf_counter() - detection_start) * 1000.0
        self._adaptive_infer_ema_ms = (self._adaptive_infer_ema_ms * 0.85) + (self._last_detection_latency_ms * 0.15)

        current_vehicle_ids: set[int] = set()
        current_people_ids: set[int] = set()
        current_vehicle_types = {vehicle_type: 0 for vehicle_type in VEHICLE_CLASSES}
        motorcycle_tracks: list[tuple[int, tuple[int, int, int, int]]] = []
        stable_person_boxes: list[tuple[int, int, int, int]] = []
        zone_count = 0

        with self.state_lock:
            class_ids = detections.class_id
            confidences = detections.confidence
            if class_ids is None or confidences is None:
                return self._draw_scene(frame)
            for index in range(len(detections)):
                tracker_id = None
                if detections.tracker_id is not None:
                    tracker_id = int(detections.tracker_id[index])
                if tracker_id is None:
                    continue

                x1, y1, x2, y2 = [int(value) for value in detections.xyxy[index].tolist()]
                class_id = int(class_ids[index])
                confidence = float(confidences[index])
                class_name = TARGET_CLASSES.get(class_id)
                if class_name is None:
                    continue

                self.last_seen[tracker_id] = now
                self.render_tracks[tracker_id] = {
                    "box": (x1, y1, x2, y2),
                    "class_name": class_name,
                    "confidence": confidence,
                    "expires": now + render_track_ttl,
                }
                track_state = self.track_states.setdefault(
                    tracker_id,
                    {
                        "frames_seen": 0,
                        "person_recorded": False,
                        "vehicle_recorded": False,
                        "vehicle_db_recorded": False,
                    },
                )
                track_state["frames_seen"] += 1
                center_y = (y1 + y2) // 2
                is_stable_track = track_state["frames_seen"] >= MIN_STABLE_FRAMES
                ts_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if is_stable_track and center_y >= zone_y:
                    zone_count += 1

                box = (x1, y1, x2, y2)
                if class_name in VEHICLE_CLASSES:
                    if is_stable_track:
                        current_vehicle_ids.add(tracker_id)
                        current_vehicle_types[class_name] += 1
                        if not track_state["vehicle_db_recorded"]:
                            track_state["vehicle_db_recorded"] = True
                            self._submit_db_task(
                                upsert_vehicle_record,
                                self.camera_id,
                                tracker_id,
                                class_name,
                            )
                        if not track_state["vehicle_recorded"]:
                            track_state["vehicle_recorded"] = True
                            state["vehicle_total_count"] += 1
                            state["vehicle_types"][class_name] += 1
                            self._push_recent(
                                state,
                                "recent_vehicles",
                                {
                                    "tracker_id": tracker_id,
                                    "vehicle_type": class_name,
                                    "plate_text": None,
                                    "time": self._format_clock(),
                                },
                                "tracker_id",
                            )
                else:
                    if is_stable_track:
                        current_people_ids.add(tracker_id)
                        stable_person_boxes.append(box)
                    if is_stable_track and not track_state["person_recorded"]:
                        track_state["person_recorded"] = True
                        state["people_total_count"] += 1

                if class_name == "motorcycle" and is_stable_track:
                    motorcycle_tracks.append((tracker_id, box))

                if is_stable_track and self.osint_service is not None:
                    try:
                        self.osint_service.collect_detection(
                            camera_id=self.camera_id,
                            tracker_id=tracker_id,
                            class_name=class_name,
                            frame=frame,
                            bbox_xyxy=(x1, y1, x2, y2),
                            ts_iso=ts_iso,
                            confidence=confidence,
                        )
                    except Exception as exc:
                        print(f"OSINT collect failed: {exc}")

            # Rider proxy: treat unmatched motorcycle tracks as one visible person.
            rider_proxy_count = 0
            for rider_track_id, rider_box in motorcycle_tracks:
                if any(self._box_overlaps(rider_box, person_box) for person_box in stable_person_boxes):
                    continue
                rider_proxy_count += 1
                touch_timestamp_cache(self.rider_proxy_track_ids, rider_track_id, now)

            trim_timestamp_cache(self.rider_proxy_track_ids, now, TRACK_STALE_SECONDS, FACE_TRACK_CACHE_LIMIT)

            state["vehicle_count"] = len(current_vehicle_ids)
            state["people_count"] = len(current_people_ids) + rider_proxy_count
            state["vehicle_current_types"] = current_vehicle_types
            state["zone_count"] = zone_count
            state["crowd_density"] = self._estimate_density(
                state["people_count"],
                frame_width,
                frame_height,
            )
            state["last_updated"] = self._format_clock()
            status = self.get_runtime_status()
            state["plate_detector_ready"] = status["plate_detector_ready"]
            state["paddle_ocr_ready"] = status["paddle_ocr_ready"]
            state["easyocr_ready"] = status["easyocr_ready"]
            state["cloud_ocr_ready"] = status["cloud_ocr_ready"]
            state["cloud_ocr_cooldown_seconds"] = status["cloud_ocr_cooldown_seconds"]
            state["ocr_fallback_ready"] = status["ocr_fallback_ready"]
            state["detector_model"] = DETECTION_MODEL_NAME
            state["plate_model"] = PLATE_MODEL_NAME
            state["device"] = "cuda" if str(self.device) != "cpu" else "cpu"
            state["adaptive_governor_enabled"] = status["adaptive_governor_enabled"]
            state["adaptive_mode"] = status["adaptive_mode"]
            state["adaptive_target_fps"] = status["adaptive_target_fps"]
            state["detector_latency_ms"] = status["detector_latency_ms"]
            state["detector_latency_ema_ms"] = status["detector_latency_ema_ms"]
            state["effective_sahi_enabled"] = status["effective_sahi_enabled"]
            state["effective_heavy_validator_enabled"] = status["effective_heavy_validator_enabled"]
            state["effective_rtdetr_enabled"] = status["effective_rtdetr_enabled"]
            state["effective_sahi_interval"] = status["effective_sahi_interval"]
            state["effective_heavy_validator_interval"] = status["effective_heavy_validator_interval"]
            state["effective_rtdetr_interval"] = status["effective_rtdetr_interval"]

            if time.time() - self.last_metric_write >= METRIC_WRITE_INTERVAL_SECONDS:
                self.last_metric_write = time.time()
                self._submit_db_task(
                    store_metric,
                    self.camera_id,
                    state["vehicle_count"],
                    state["people_count"],
                    state["zone_count"],
                )

            self._cleanup_expired_cache()

            if self.osint_service is not None:
                try:
                    self.osint_service.flush_stale()
                except Exception as exc:
                    print(f"OSINT flush failed: {exc}")

        return self._draw_scene(frame)
