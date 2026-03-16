from __future__ import annotations

import asyncio
import io
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
import csv
import io

from typing import Dict, List

import matplotlib
import psutil
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from matplotlib import pyplot as plt

from database import (
    acknowledge_helmet_event,
    acknowledge_weapon_event,
    get_face_records,
    get_face_snapshot,
    get_helmet_events,
    get_metric_history,
    get_ocr_analytics,
    get_plate_reads,
    get_recent_events,
    get_traffic_analytics,
    get_vehicle_records,
    get_weapon_events,
    get_weapon_summary,
    insert_helmet_event,
    insert_weapon_event,
)
from pipeline import get_system_health_snapshot, has_any_ocr_path, warm_shared_resources
from runtime import CameraRuntime
from osint_reid.api import router as osint_router

matplotlib.use("Agg")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
WATCHLIST_DIR = BASE_DIR / "watchlist"
FRONTEND_DIST_DIR = BASE_DIR / "static_ui"
FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"
LEGACY_INDEX_PATH = BASE_DIR / "templates" / "index.html"

runtimes: Dict[str, CameraRuntime] = {}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".webm", ".ts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
UPLOAD_CHUNK_SIZE = 1024 * 1024
STARTUP_STATE = {
    "phase": "booting",
    "ready": False,
    "preload_enabled": False,
    "preload_complete": False,
    "error": None,
    "last_updated": None,
}
RUNTIME_SETTINGS = {
    "face_threshold": 1.05,
}


def load_local_env(env_path: Path) -> None:
    if not env_path.exists() or not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_local_env(BASE_DIR / ".env")

try:
    import pynvml  # type: ignore[import-untyped]

    _NVML_AVAILABLE = True
except Exception:
    pynvml = None
    _NVML_AVAILABLE = False


def env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def parse_size_bytes(value: str | None, default: int) -> int:
    if value is None:
        return default
    normalized = value.strip().upper()
    if not normalized:
        return default
    suffixes = {
        "GB": 1024 * 1024 * 1024,
        "MB": 1024 * 1024,
        "KB": 1024,
        "B": 1,
    }
    for suffix, multiplier in suffixes.items():
        if normalized.endswith(suffix):
            number = normalized[: -len(suffix)].strip()
            try:
                return max(int(float(number) * multiplier), 1)
            except ValueError:
                return default
    try:
        return max(int(normalized), 1)
    except ValueError:
        return default


def sanitize_upload_name(filename: str | None) -> str:
    original = Path(filename or "video.mp4").name
    suffix = Path(original).suffix.lower() or ".mp4"
    stem = Path(original).stem
    safe_stem = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in stem).strip("._")
    return f"{safe_stem or 'video'}{suffix}"


def sanitize_watchlist_name(value: str | None) -> str:
    safe_value = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (value or "").strip())
    return safe_value.strip("._-")


def parse_csv_env(name: str, default: List[str]) -> List[str]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or default


def resolve_cors_settings() -> tuple[List[str], bool]:
    origins = parse_csv_env(
        "CYBERSHIELD_ALLOWED_ORIGINS",
        [
            "http://127.0.0.1:8080",
            "http://localhost:8080",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ],
    )
    allow_credentials = True
    if origins == ["*"]:
        allow_credentials = False
    return origins, allow_credentials


def list_watchlist_entries() -> List[dict]:
    WATCHLIST_DIR.mkdir(exist_ok=True)
    entries: List[dict] = []
    for path in sorted(WATCHLIST_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        stat = path.stat()
        entries.append(
            {
                "identity": path.stem,
                "filename": path.name,
                "size_bytes": stat.st_size,
                "updated_at": int(stat.st_mtime),
            }
        )
    return entries


def _render_chart_to_tempfile(plotter) -> Path:
    fd, temp_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    figure, axis = plt.subplots(figsize=(8.5, 3.2), dpi=160)
    try:
        plotter(figure, axis)
        figure.tight_layout()
        figure.savefig(temp_path, format="png", facecolor="#ffffff", bbox_inches="tight")
    finally:
        plt.close(figure)
    return Path(temp_path)


def build_vehicle_totals_chart(vehicle_totals: Dict[str, int]) -> Path:
    labels = [label.capitalize() for label in vehicle_totals.keys()]
    values = [int(vehicle_totals[label.lower()]) for label in labels]

    def plotter(_, axis):
        colors = ["#60a5fa", "#22d3ee", "#34d399", "#fbbf24"]
        axis.bar(labels, values, color=colors[: len(labels)], width=0.55)
        axis.set_title("Vehicle Classification Totals", fontsize=12, pad=12)
        axis.set_ylabel("Count")
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)

    return _render_chart_to_tempfile(plotter)


def build_gender_chart(gender_totals: Dict[str, int]) -> Path:
    labels = list(gender_totals.keys())
    values = [int(gender_totals[label]) for label in labels]

    def plotter(_, axis):
        axis.pie(
            values,
            labels=labels,
            autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else "",
            colors=["#3b82f6", "#f472b6", "#64748b"],
            startangle=90,
            wedgeprops={"linewidth": 1, "edgecolor": "white"},
        )
        axis.set_title("Gender Analytics", fontsize=12, pad=12)

    return _render_chart_to_tempfile(plotter)


def build_metrics_trend_chart(metrics_history: List[dict]) -> Path | None:
    if not metrics_history:
        return None

    labels = [str(item.get("timestamp", ""))[-8:] for item in metrics_history]
    vehicle_values = [int(item.get("vehicle_count") or 0) for item in metrics_history]
    people_values = [int(item.get("people_count") or 0) for item in metrics_history]

    def plotter(_, axis):
        axis.plot(labels, vehicle_values, color="#60a5fa", linewidth=2.0, label="Vehicles")
        axis.plot(labels, people_values, color="#34d399", linewidth=2.0, label="People")
        axis.set_title("Traffic and Crowd Trend", fontsize=12, pad=12)
        axis.set_ylabel("Tracked count")
        axis.grid(alpha=0.2)
        axis.legend(loc="upper left")
        if len(labels) > 8:
            step = max(len(labels) // 8, 1)
            axis.set_xticks(range(0, len(labels), step))
            axis.set_xticklabels([labels[index] for index in range(0, len(labels), step)], rotation=20)
        else:
            axis.tick_params(axis="x", rotation=20)

    return _render_chart_to_tempfile(plotter)


def build_hourly_flow_chart(flow_rows: List[dict]) -> Path | None:
    if not flow_rows:
        return None

    labels = [str(item.get("timestamp", ""))[11:16] or str(item.get("timestamp", "")) for item in flow_rows]
    values = [int(item.get("vehicle_count") or 0) for item in flow_rows]

    def plotter(_, axis):
        axis.fill_between(range(len(values)), values, color="#22d3ee", alpha=0.25)
        axis.plot(range(len(values)), values, color="#0891b2", linewidth=2.0)
        axis.set_title("Hourly Vehicle Flow", fontsize=12, pad=12)
        axis.set_ylabel("Peak vehicles")
        axis.grid(alpha=0.2)
        axis.set_xticks(range(len(labels)))
        axis.set_xticklabels(labels, rotation=20)

    return _render_chart_to_tempfile(plotter)


MAX_UPLOAD_SIZE_BYTES = parse_size_bytes(os.getenv("CYBERSHIELD_MAX_UPLOAD_SIZE"), 512 * 1024 * 1024)
PRELOAD_SHARED_MODELS = env_flag("CYBERSHIELD_PRELOAD_MODELS", True)
REQUIRE_OCR_READY = env_flag("CYBERSHIELD_REQUIRE_OCR_READY", True)
WS_UPDATE_INTERVAL_SECONDS = max(float(os.getenv("CYBERSHIELD_WS_INTERVAL", "1.0")), 0.25)
CORS_ALLOWED_ORIGINS, CORS_ALLOW_CREDENTIALS = resolve_cors_settings()


def sanitize_camera_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())
    return cleaned or f"camera_{int(time.time())}"


def next_camera_id() -> str:
    index = 1
    while f"camera_{index}" in runtimes:
        index += 1
    return f"camera_{index}"


async def persist_upload(file: UploadFile, target_path: Path) -> None:
    total_written = 0
    try:
        with target_path.open("wb") as output_file:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds the {MAX_UPLOAD_SIZE_BYTES} byte limit.",
                    )
                output_file.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


def get_initial_state(camera_id: str, source: str = "") -> dict:
    return {
        "camera_id": camera_id,
        "source": source,
        "vehicle_count": 0,
        "vehicle_total_count": 0,
        "vehicle_types": {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0},
        "vehicle_current_types": {"car": 0, "motorcycle": 0, "bus": 0, "truck": 0},
        "people_count": 0,
        "people_total_count": 0,
        "gender_stats": {"Man": 0, "Woman": 0, "Unknown": 0},
        "crowd_density": "Low",
        "faces_detected": 0,
        "plates_detected": 0,
        "zone_count": 0,
        "recent_vehicles": [],
        "recent_plates": [],
        "pending_plates": [],
        "recent_faces": [],
        "event_logs": [],
        "last_updated": None,
        "is_processing": False,
        "stream_fps": 0.0,
        "analytics_fps": 0.0,
        "inference_latency_ms": 0.0,
        "plate_detector_ready": False,
        "paddle_ocr_ready": False,
        "easyocr_ready": False,
        "cloud_ocr_ready": False,
        "cloud_ocr_cooldown_seconds": 0.0,
        "ocr_fallback_ready": False,
        "runtime_warnings": [],
        "detector_model": None,
        "plate_model": None,
        "device": "cpu",
        "weapon_alert_count": 0,
        "weapon_detect_enabled": False,
    }


def get_state_snapshot(camera_id: str) -> dict:
    if camera_id not in runtimes:
        return get_initial_state(camera_id)
    return runtimes[camera_id].snapshot_state()


def release_camera(camera_id: str, drop_state: bool = False) -> None:
    runtime = runtimes.pop(camera_id, None)
    if runtime is not None:
        runtime.release()


def mount_camera(camera_id: str, source: str) -> None:
    release_camera(camera_id)
    state = get_initial_state(camera_id, str(source))
    runtimes[camera_id] = CameraRuntime(camera_id, str(source), state)


@asynccontextmanager
async def lifespan(_: FastAPI):
    UPLOAD_DIR.mkdir(exist_ok=True)
    WATCHLIST_DIR.mkdir(exist_ok=True)
    STARTUP_STATE["phase"] = "initializing"
    STARTUP_STATE["ready"] = False
    STARTUP_STATE["preload_enabled"] = PRELOAD_SHARED_MODELS
    STARTUP_STATE["preload_complete"] = False
    STARTUP_STATE["error"] = None
    STARTUP_STATE["last_updated"] = int(time.time())
    if REQUIRE_OCR_READY and not has_any_ocr_path():
        STARTUP_STATE["phase"] = "error"
        STARTUP_STATE["error"] = (
            "No OCR path is configured. Enable PaddleOCR/EasyOCR or provide PLATE_RECOGNIZER_API_TOKEN."
        )
        STARTUP_STATE["last_updated"] = int(time.time())
        raise RuntimeError(
            "No OCR path is configured. Enable PaddleOCR/EasyOCR or provide PLATE_RECOGNIZER_API_TOKEN."
        )
    try:
        if PRELOAD_SHARED_MODELS:
            STARTUP_STATE["phase"] = "preloading-models"
            STARTUP_STATE["last_updated"] = int(time.time())
            await asyncio.to_thread(warm_shared_resources)
            STARTUP_STATE["preload_complete"] = True
        STARTUP_STATE["phase"] = "ready"
        STARTUP_STATE["ready"] = True
        STARTUP_STATE["last_updated"] = int(time.time())
        yield
    except Exception as exc:
        STARTUP_STATE["phase"] = "error"
        STARTUP_STATE["ready"] = False
        STARTUP_STATE["error"] = str(exc)
        STARTUP_STATE["last_updated"] = int(time.time())
        raise
    finally:
        if STARTUP_STATE["phase"] != "error":
            STARTUP_STATE["phase"] = "shutdown"
            STARTUP_STATE["ready"] = False
            STARTUP_STATE["last_updated"] = int(time.time())
        for camera_id in list(runtimes.keys()):
            release_camera(camera_id, drop_state=False)


def get_health_snapshot() -> dict:
    base = get_system_health_snapshot()
    active = [runtime for runtime in runtimes.values() if runtime.running]
    max_cooldown = 0.0
    runtime_warnings: list[dict] = []
    for runtime in active:
        cooldown = float(runtime.state.get("cloud_ocr_cooldown_seconds") or 0.0)
        if cooldown > max_cooldown:
            max_cooldown = cooldown
        for warning in runtime.state.get("runtime_warnings") or []:
            runtime_warnings.append({**warning, "camera_id": runtime.camera_id})
    base["active_camera_count"] = len(active)
    base["runtimes_running"] = bool(active)
    base["cloud_ocr_cooldown_seconds"] = round(max_cooldown, 1)
    base["startup"] = dict(STARTUP_STATE)
    if active:
        base["ocr_ready"] = any(bool(runtime.state.get("ocr_fallback_ready")) for runtime in active) or bool(
            base.get("ocr_ready")
        )
    if max_cooldown > 0.0 and not any(item.get("code") == "cloud_ocr_cooldown" for item in runtime_warnings):
        runtime_warnings.append(
            {
                "code": "cloud_ocr_cooldown",
                "severity": "warning",
                "component": "cloud_ocr",
                "message": "Cloud OCR fallback is temporarily cooling down after a recent failure.",
                "cooldown_seconds": round(max_cooldown, 1),
            }
        )
    base["warnings"] = [*base.get("warnings", []), *runtime_warnings]
    return base


def get_system_stats_snapshot() -> dict:
    virtual_memory = psutil.virtual_memory()
    payload = {
        "cpu_percent": float(psutil.cpu_percent(interval=None)),
        "memory_percent": float(virtual_memory.percent),
        "memory_used_mb": round(float(virtual_memory.used) / (1024 * 1024), 2),
        "memory_total_mb": round(float(virtual_memory.total) / (1024 * 1024), 2),
        "gpu_available": False,
        "gpu_name": None,
        "gpu_percent": 0.0,
        "gpu_memory_used_mb": 0.0,
        "gpu_memory_total_mb": 0.0,
    }

    if not _NVML_AVAILABLE or pynvml is None:
        return payload

    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        payload.update(
            {
                "gpu_available": True,
                "gpu_name": pynvml.nvmlDeviceGetName(handle).decode("utf-8", errors="ignore"),
                "gpu_percent": float(util.gpu),
                "gpu_memory_used_mb": round(float(memory.used) / (1024 * 1024), 2),
                "gpu_memory_total_mb": round(float(memory.total) / (1024 * 1024), 2),
            }
        )
    except Exception:
        return payload
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass

    return payload


app = FastAPI(title="CyberShield AI Video Analytics", lifespan=lifespan)
app.include_router(osint_router)
app.mount("/assets", StaticFiles(directory=str(FRONTEND_ASSETS_DIR), check_dir=False), name="frontend-assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def enforce_upload_limits(request: Request, call_next):
    if request.url.path in ("/api/video/upload", "/api/video/stage"):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                announced_size = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
            if announced_size > MAX_UPLOAD_SIZE_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Upload exceeds the {MAX_UPLOAD_SIZE_BYTES} byte limit."},
                )
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def read_dashboard():
    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    if LEGACY_INDEX_PATH.exists():
        return FileResponse(LEGACY_INDEX_PATH)
    return HTMLResponse(
        "Frontend bundle is not available. Build the React app from integrated-video-analytics/frontend.",
        status_code=503,
    )


@app.get("/api/cameras")
async def list_cameras():
    return {
        "cameras": [
            {
                "camera_id": camera_id,
                "source": runtimes[camera_id].source,
                "running": runtimes[camera_id].running,
            }
            for camera_id in runtimes
        ]
    }


@app.post("/api/cameras/add")
async def add_camera(camera_id: str, source: str):
    camera_id = sanitize_camera_id(camera_id)
    try:
        mount_camera(camera_id, source)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "camera_id": camera_id, "info": f"Camera {camera_id} added."}


@app.delete("/api/cameras/{camera_id}")
async def remove_camera(camera_id: str):
    if camera_id not in runtimes:
        raise HTTPException(status_code=404, detail="Camera not found")
    release_camera(camera_id, drop_state=True)
    return {"status": "success", "camera_id": camera_id}


@app.post("/api/video/stage")
async def stage_video(request: Request, file: UploadFile = File(...), camera_id: str | None = None):
    """Upload a video file and return its server path without mounting a camera."""
    if camera_id is None:
        form = await request.form()
        raw_camera_id = form.get("camera_id")
        if isinstance(raw_camera_id, str) and raw_camera_id.strip():
            camera_id = raw_camera_id
    camera_id = sanitize_camera_id(camera_id) if camera_id else next_camera_id()
    safe_name = sanitize_upload_name(file.filename)
    if Path(safe_name).suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported video format.")
    target_path = UPLOAD_DIR / f"{camera_id}_{int(time.time())}_{safe_name}"
    await persist_upload(file, target_path)
    return {
        "status": "success",
        "camera_id": camera_id,
        "path": str(target_path),
        "filename": safe_name,
    }


@app.post("/api/video/upload")
async def upload_video(request: Request, file: UploadFile = File(...), camera_id: str | None = None):
    if camera_id is None:
        form = await request.form()
        raw_camera_id = form.get("camera_id")
        if isinstance(raw_camera_id, str) and raw_camera_id.strip():
            camera_id = raw_camera_id
    camera_id = sanitize_camera_id(camera_id) if camera_id else next_camera_id()
    safe_name = sanitize_upload_name(file.filename)
    if Path(safe_name).suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported video format.")
    target_path = UPLOAD_DIR / f"{camera_id}_{int(time.time())}_{safe_name}"

    await persist_upload(file, target_path)

    try:
        mount_camera(camera_id, str(target_path))
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "success",
        "camera_id": camera_id,
        "filename": safe_name,
        "info": f"File '{safe_name}' mounted as {camera_id}",
    }


def generate_frames(camera_id: str):
    runtime = runtimes.get(camera_id)
    if runtime is None:
        return
    yield from runtime.frame_generator()


@app.get("/api/video/stream")
def video_feed_default():
    if not runtimes:
        raise HTTPException(status_code=404, detail="No camera available")
    camera_id = next(iter(runtimes.keys()))
    return StreamingResponse(
        generate_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/video/stream/{camera_id}")
def video_feed(camera_id: str):
    if camera_id not in runtimes:
        raise HTTPException(status_code=404, detail="Camera not found")
    return StreamingResponse(
        generate_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/analytics/status")
def get_analytics_status(camera_id: str):
    return get_state_snapshot(camera_id)


@app.get("/api/health")
def health_check():
    return get_health_snapshot()


@app.get("/api/system/stats")
def system_stats():
    return get_system_stats_snapshot()


@app.get("/api/logs/history")
def get_logs_history(limit: int = 50, query: str | None = None, camera_id: str | None = None):
    return {"logs": get_recent_events(limit=limit, query=query, camera_id=camera_id)}


@app.get("/api/records/plates")
def get_plate_history(
    limit: int = 25,
    query: str | None = None,
    camera_id: str | None = None,
    min_confidence: float | None = None,
    ocr_source: str | None = None,
):
    normalized_source = (ocr_source or "").strip().lower() or None
    if normalized_source not in {None, "paddle", "easyocr", "cloud", "unknown"}:
        raise HTTPException(status_code=400, detail="Invalid ocr_source filter.")
    if min_confidence is not None and not (0.0 <= min_confidence <= 1.0):
        raise HTTPException(status_code=400, detail="min_confidence must be between 0 and 1.")
    return {
        "records": get_plate_reads(
            limit=limit,
            query=query,
            camera_id=camera_id,
            min_confidence=min_confidence,
            ocr_source=normalized_source,
        )
    }


@app.get("/api/records/vehicles")
def get_vehicle_history(
    limit: int = 25,
    query: str | None = None,
    camera_id: str | None = None,
    require_plate: bool = False,
):
    return {
        "records": get_vehicle_records(
            limit=limit,
            query=query,
            camera_id=camera_id,
            require_plate=require_plate,
        )
    }


@app.get("/api/records/faces")
def get_face_history(
    limit: int = 25,
    query: str | None = None,
    camera_id: str | None = None,
    watchlist_only: bool = False,
):
    return {
        "records": get_face_records(
            limit=limit,
            query=query,
            camera_id=camera_id,
            watchlist_only=watchlist_only,
        )
    }


@app.get("/api/metrics")
def get_metrics(limit: int = 120, camera_id: str | None = None):
    return {"history": get_metric_history(limit=limit, camera_id=camera_id)}


@app.get("/api/analytics/traffic")
def get_traffic(camera_id: str | None = None):
    return get_traffic_analytics(camera_id=camera_id)


@app.get("/api/analytics/ocr")
def get_ocr_summary(camera_id: str | None = None):
    return get_ocr_analytics(camera_id=camera_id)


@app.get("/api/analytics/summary")
def get_analytics_summary(camera_id: str | None = None):
    vehicle_records = get_vehicle_records(limit=500, camera_id=camera_id, require_plate=False)
    face_records = get_face_records(limit=500, camera_id=camera_id)
    plate_records = get_plate_reads(limit=500, camera_id=camera_id)
    events = get_recent_events(limit=1000, camera_id=camera_id)

    gender_breakdown: Dict[str, int] = {"Male": 0, "Female": 0, "Unknown": 0}
    for face in face_records:
        gender = str(face.get("gender") or "Unknown").strip().capitalize()
        if gender not in gender_breakdown:
            gender_breakdown[gender] = 0
        gender_breakdown[gender] += 1

    vehicle_type_breakdown: Dict[str, int] = {}
    for vehicle in vehicle_records:
        vehicle_type = str(vehicle.get("vehicle_type") or "Unknown").strip().upper()
        vehicle_type_breakdown[vehicle_type] = vehicle_type_breakdown.get(vehicle_type, 0) + 1

    plate_frequency: Dict[str, int] = {}
    for plate in plate_records:
        plate_text = str(plate.get("plate_text") or "").strip().upper()
        if plate_text:
            plate_frequency[plate_text] = plate_frequency.get(plate_text, 0) + 1

    event_count_by_type: Dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type") or "event")
        event_count_by_type[event_type] = event_count_by_type.get(event_type, 0) + 1

    top_plates = [
        {"plate_text": plate_text, "count": count}
        for plate_text, count in sorted(plate_frequency.items(), key=lambda item: item[1], reverse=True)[:5]
    ]

    return {
        "summary": {
            "camera_id": camera_id or "all",
            "total_vehicles": len(vehicle_records),
            "total_people": len(face_records),
            "total_plates": len(plate_records),
            "total_faces": len(face_records),
            "watchlist_hits": sum(1 for face in face_records if bool(face.get("watchlist_hit"))),
            "gender_breakdown": gender_breakdown,
            "vehicle_type_breakdown": vehicle_type_breakdown,
            "top_plates": top_plates,
            "event_count_by_type": event_count_by_type,
        }
    }


@app.get("/api/settings/face-threshold")
def get_face_threshold_setting():
    return {"value": float(RUNTIME_SETTINGS["face_threshold"])}


@app.post("/api/settings/face-threshold")
async def set_face_threshold_setting(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body is required")
    value = payload.get("value")
    if value is None:
        raise HTTPException(status_code=400, detail="value is required")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="value must be a number") from exc
    if parsed <= 0:
        raise HTTPException(status_code=400, detail="value must be positive")
    RUNTIME_SETTINGS["face_threshold"] = parsed
    return {"status": "success", "value": parsed}


@app.get("/api/export/maltego")
def export_maltego_graph(
    camera_id: str | None = None,
    entity: str = "faces",
    limit: int = 1000,
):
    normalized_entity = (entity or "faces").strip().lower()
    if normalized_entity not in {"faces", "vehicles", "plates", "events"}:
        raise HTTPException(status_code=400, detail="entity must be one of: faces, vehicles, plates, events")
    if limit < 1 or limit > 10000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 10000")

    if normalized_entity == "faces":
        records = get_face_records(limit=limit, camera_id=camera_id)
        rows = [
            {
                "entity_type": "Face",
                "camera_id": record.get("camera_id"),
                "tracker_id": record.get("tracker_id"),
                "identity": record.get("identity") or "Anonymous",
                "gender": record.get("gender") or "Unknown",
                "age": record.get("age"),
                "watchlist_hit": bool(record.get("watchlist_hit")),
                "first_seen": record.get("first_seen"),
                "last_seen": record.get("last_seen"),
            }
            for record in records
        ]
    elif normalized_entity == "vehicles":
        records = get_vehicle_records(limit=limit, camera_id=camera_id, require_plate=False)
        rows = [
            {
                "entity_type": "Vehicle",
                "camera_id": record.get("camera_id"),
                "tracker_id": record.get("tracker_id"),
                "vehicle_type": record.get("vehicle_type") or "Unknown",
                "plate_text": record.get("plate_text") or "",
                "first_seen": record.get("first_seen"),
                "last_seen": record.get("last_seen"),
            }
            for record in records
        ]
    elif normalized_entity == "plates":
        records = get_plate_reads(limit=limit, camera_id=camera_id)
        rows = [
            {
                "entity_type": "Plate",
                "camera_id": record.get("camera_id"),
                "tracker_id": record.get("tracker_id"),
                "plate_text": record.get("plate_text") or "",
                "vehicle_type": record.get("vehicle_type") or "Unknown",
                "confidence": record.get("confidence"),
                "ocr_source": record.get("ocr_source") or "unknown",
                "first_seen": record.get("first_seen"),
                "last_seen": record.get("last_seen"),
            }
            for record in records
        ]
    else:
        records = get_recent_events(limit=limit, camera_id=camera_id)
        rows = [
            {
                "entity_type": "Event",
                "camera_id": record.get("camera_id"),
                "event_type": record.get("type") or "event",
                "detail": record.get("detail") or "",
                "timestamp": record.get("timestamp"),
            }
            for record in records
        ]

    if not rows:
        rows = [{"entity_type": normalized_entity.capitalize(), "camera_id": camera_id or ""}]

    headers = list(rows[0].keys())
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    payload = stream.getvalue().encode("utf-8")
    stream.close()

    scoped = camera_id or "all_cameras"
    filename = f"maltego_{normalized_entity}_{scoped}.csv"
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/watchlist/files")
def get_watchlist():
    return {"entries": list_watchlist_entries()}


@app.post("/api/watchlist/files")
async def add_watchlist_entry(name: str = Form(...), file: UploadFile = File(...)):
    identity = sanitize_watchlist_name(name)
    if not identity:
        raise HTTPException(status_code=400, detail="A valid identity name is required.")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported watchlist image format.")

    target_path = WATCHLIST_DIR / f"{identity}{suffix}"
    if target_path.exists():
        raise HTTPException(status_code=409, detail="A watchlist image already exists for that identity.")

    await persist_upload(file, target_path)
    return {"status": "success", "entry": {"identity": identity, "filename": target_path.name}}


@app.delete("/api/watchlist/files/{identity}")
def delete_watchlist_entry(identity: str):
    safe_identity = sanitize_watchlist_name(identity)
    if not safe_identity:
        raise HTTPException(status_code=400, detail="Invalid identity.")

    deleted = False
    for path in WATCHLIST_DIR.glob(f"{safe_identity}.*"):
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            path.unlink(missing_ok=True)
            deleted = True

    if not deleted:
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")
    return {"status": "success", "identity": safe_identity}


@app.post("/api/demo/sequence")
async def start_demo_sequence(entries: list[dict]):
    async def _delayed_mount(camera_id: str, source: str, delay: float):
        if delay > 0:
            await asyncio.sleep(delay)
        mount_camera(camera_id, source)

    for entry in entries:
        cid = sanitize_camera_id(entry.get("camera_id") or next_camera_id())
        src = str(entry.get("source", ""))
        delay = float(entry.get("delay_seconds", 0))
        asyncio.create_task(_delayed_mount(cid, src, delay))

    return {"status": "sequence_started", "cameras": [e.get("camera_id") for e in entries]}


@app.get("/api/persons")
async def list_persons(watchlist_only: bool = False):
    from osint_reid.service import get_osint_service
    svc = get_osint_service()
    persons = svc.db.get_all_persons(watchlist_only=watchlist_only)
    return {"persons": persons}


@app.get("/api/persons/movements")
async def list_person_movements(since: str | None = None):
    from osint_reid.service import get_osint_service
    svc = get_osint_service()
    return {"movements": svc.get_movement_events(since_iso=since)}


@app.get("/api/persons/{global_id}/timeline")
async def get_person_timeline(global_id: str):
    from osint_reid.service import get_osint_service
    svc = get_osint_service()
    timeline = svc.db.get_person_timeline(global_id)
    return {"global_id": global_id, "timeline": timeline}


@app.get("/api/persons/{global_id}/snapshot.jpg")
async def get_person_snapshot(global_id: str):
    from osint_reid.service import get_osint_service
    svc = get_osint_service()
    latest = svc.db.get_latest_tracklet_for_global(global_id)
    if latest is None:
        raise HTTPException(status_code=404, detail="No tracklet found")
    # Extract camera_id and tracker_id from tracklet_id format "camera_id:tracker_id:class"
    parts = latest["tracklet_id"].split(":")
    if len(parts) >= 2:
        cam = parts[0]
        try:
            tid = int(parts[1])
        except ValueError:
            raise HTTPException(status_code=404, detail="Cannot parse tracker_id")
        blob = get_face_snapshot(cam, tid)
        if blob:
            return Response(content=blob, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="No snapshot available")


@app.post("/api/persons/{global_id}/watchlist")
async def set_person_watchlist(global_id: str, body: dict):
    from osint_reid.service import get_osint_service
    svc = get_osint_service()
    flag = bool(body.get("flag", True))
    meta = {"display_name": body.get("display_name", "")}
    svc.db.set_watchlist_flag(global_id, flag, meta)
    return {"status": "ok", "global_id": global_id, "watchlist_flag": flag}


@app.get("/api/helmet/events")
async def get_helmet_events_api(camera_id: str | None = None, limit: int = 50):
    return {"events": get_helmet_events(camera_id=camera_id, limit=limit)}


@app.post("/api/helmet/acknowledge/{event_id}")
async def ack_helmet_event(event_id: int):
    ok = acknowledge_helmet_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "acknowledged", "event_id": event_id}


@app.websocket("/ws/analytics/{camera_id}")
async def websocket_endpoint(websocket: WebSocket, camera_id: str):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(get_state_snapshot(camera_id))
            await asyncio.sleep(WS_UPDATE_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        return


@app.get("/api/reports/download")
async def download_report(camera_id: str):
    state = get_state_snapshot(camera_id)
    vehicle_records = get_vehicle_records(limit=10, camera_id=camera_id)
    plate_records = get_plate_reads(limit=10, camera_id=camera_id)
    face_records = get_face_records(limit=10, camera_id=camera_id)
    metrics_history = get_metric_history(limit=120, camera_id=camera_id)
    traffic_analytics = get_traffic_analytics(camera_id=camera_id)
    chart_paths: List[Path] = []

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    pdf.cell(190, 10, text="CyberShield AI Video Analytics Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    pdf.set_font("Arial", size=11)
    pdf.cell(190, 8, text=f"Camera ID: {camera_id}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Source: {state.get('source', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Last Updated: {state.get('last_updated', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    pdf.cell(190, 8, text=f"Vehicles in frame: {state.get('vehicle_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Stable vehicles recorded over session: {state.get('vehicle_total_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"People in frame: {state.get('people_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"People tracked over session: {state.get('people_total_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Crowd density: {state.get('crowd_density', 'Low')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Faces analyzed: {state.get('faces_detected', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Plates logged: {state.get('plates_detected', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Zone occupancy: {state.get('zone_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Output stream FPS: {state.get('stream_fps', 0.0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Analytics FPS: {state.get('analytics_fps', 0.0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Inference latency: {state.get('inference_latency_ms', 0.0)} ms", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 8, text=f"Device: {state.get('device', 'cpu')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_font("Arial", size=12)
    pdf.cell(190, 8, text="Vehicle classification totals", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Arial", size=11)
    for vehicle_type, count in state.get("vehicle_types", {}).items():
        pdf.cell(190, 7, text=f"{vehicle_type.capitalize()}: {count}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font("Arial", size=12)
    pdf.cell(190, 8, text="Gender analytics", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Arial", size=11)
    for gender, count in state.get("gender_stats", {}).items():
        pdf.cell(190, 7, text=f"{gender}: {count}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font("Arial", size=12)
    pdf.cell(190, 8, text="Traffic analytics summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Arial", size=11)
    pdf.cell(190, 7, text=f"Peak vehicle count: {traffic_analytics.get('peak_vehicle_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, text=f"Average vehicle count: {traffic_analytics.get('average_vehicle_count', 0.0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, text=f"Average people count: {traffic_analytics.get('average_people_count', 0.0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(190, 7, text=f"Peak zone occupancy: {traffic_analytics.get('peak_zone_count', 0)}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if traffic_analytics.get("peak_timestamp"):
        pdf.cell(190, 7, text=f"Peak observed at: {traffic_analytics['peak_timestamp']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    chart_paths.append(build_vehicle_totals_chart(state.get("vehicle_types", {})))
    chart_paths.append(build_gender_chart(state.get("gender_stats", {})))
    trend_chart = build_metrics_trend_chart(metrics_history)
    if trend_chart is not None:
        chart_paths.append(trend_chart)
    hourly_chart = build_hourly_flow_chart(traffic_analytics.get("hourly_vehicle_flow", []))
    if hourly_chart is not None:
        chart_paths.append(hourly_chart)

    for chart_path in chart_paths:
        pdf.add_page()
        pdf.image(str(chart_path), x=12, y=18, w=186)

    if vehicle_records:
        pdf.ln(4)
        pdf.set_font("Arial", size=12)
        pdf.cell(190, 8, text="Recent vehicle records", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Arial", size=10)
        for record in vehicle_records:
            plate_value = record["plate_text"] or "Plate pending"
            pdf.multi_cell(
                190,
                6,
                text=(
                    f"tracker #{record['tracker_id']} | {record['vehicle_type']} | {plate_value} | "
                    f"first seen {record['first_seen']} | last seen {record['last_seen']}"
                ),
            )

    if plate_records:
        pdf.ln(4)
        pdf.set_font("Arial", size=12)
        pdf.cell(190, 8, text="Recent ANPR records", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Arial", size=10)
        for record in plate_records:
            pdf.multi_cell(
                190,
                6,
                text=(
                    f"{record['plate_text']} | {record['vehicle_type']} | "
                    f"first seen {record['first_seen']} | last seen {record['last_seen']}"
                ),
            )

    if face_records:
        pdf.ln(4)
        pdf.set_font("Arial", size=12)
        pdf.cell(190, 8, text="Recent face records", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Arial", size=10)
        for record in face_records:
            identity = record["identity"] or "Anonymous"
            status = "Watchlist hit" if record["watchlist_hit"] else "No watchlist hit"
            pdf.multi_cell(
                190,
                6,
                text=(
                    f"{identity} | {record['gender'] or 'Unknown'} | {status} | "
                    f"first seen {record['first_seen']} | last seen {record['last_seen']}"
                ),
            )

    payload = pdf.output()
    if isinstance(payload, str):
        payload = payload.encode("latin-1")
    elif isinstance(payload, bytearray):
        payload = bytes(payload)
    for chart_path in chart_paths:
        chart_path.unlink(missing_ok=True)
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="CyberShield_{camera_id}_Analytics_Report.pdf"'
        },
    )


@app.get("/api/weapons/events")
def get_weapons_list(
    limit: int = 50,
    camera_id: str | None = None,
    unacknowledged_only: bool = False,
):
    return {
        "events": get_weapon_events(
            limit=limit,
            camera_id=camera_id,
            unacknowledged_only=unacknowledged_only,
        )
    }


@app.get("/api/weapons/summary")
def get_weapons_summary(camera_id: str | None = None):
    return get_weapon_summary(camera_id=camera_id)


@app.post("/api/weapons/acknowledge/{event_id}")
def acknowledge_weapon(event_id: int):
    success = acknowledge_weapon_event(event_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to acknowledge weapon event")
    return {"status": "success", "event_id": event_id}


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str):
    blocked_prefixes = ("api/", "ws/", "docs", "redoc", "openapi.json")
    if full_path.startswith(blocked_prefixes):
        raise HTTPException(status_code=404, detail="Not found")

    requested_path = FRONTEND_DIST_DIR / full_path
    if requested_path.exists() and requested_path.is_file():
        return FileResponse(requested_path)

    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    if LEGACY_INDEX_PATH.exists():
        return FileResponse(LEGACY_INDEX_PATH)

    return HTMLResponse(
        "Frontend bundle is not available. Build the React app from integrated-video-analytics/frontend.",
        status_code=503,
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
