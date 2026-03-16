from __future__ import annotations

import concurrent.futures
import os
import threading
import time
from typing import Iterator

import cv2

from camera import CameraStream
from pipeline import DETECTION_MODEL_NAME, PLATE_MODEL_NAME, VideoPipeline

DEFAULT_STREAM_FPS = "24" if VideoPipeline.gpu_available() else "14"
DEFAULT_JPEG_QUALITY = "82" if VideoPipeline.gpu_available() else "72"
DEFAULT_STREAM_WIDTH = "1280" if VideoPipeline.gpu_available() else "960"
DEFAULT_STREAM_PROFILE = (os.getenv("CYBERSHIELD_STREAM_PROFILE") or "balanced").strip().lower()

MAX_OUTPUT_FPS = float(os.getenv("CYBERSHIELD_STREAM_MAX_FPS", DEFAULT_STREAM_FPS))
JPEG_QUALITY = int(os.getenv("CYBERSHIELD_STREAM_JPEG_QUALITY", DEFAULT_JPEG_QUALITY))
MAX_STREAM_WIDTH = int(os.getenv("CYBERSHIELD_STREAM_MAX_WIDTH", DEFAULT_STREAM_WIDTH))
ANALYTICS_FPS = float(
    os.getenv("CYBERSHIELD_ANALYTICS_FPS", "10" if VideoPipeline.gpu_available() else "8")
)
TASK_REFRESH_FPS = float(
    os.getenv("CYBERSHIELD_TASK_REFRESH_FPS", "10" if VideoPipeline.gpu_available() else "6")
)

STREAM_PROFILES = {
    "low": {
        "max_fps": max(6.0, min(MAX_OUTPUT_FPS, 10.0 if VideoPipeline.gpu_available() else 8.0)),
        "jpeg_quality": max(50, min(JPEG_QUALITY, 68)),
        "max_width": max(640, min(MAX_STREAM_WIDTH, 960)),
    },
    "balanced": {
        "max_fps": max(8.0, MAX_OUTPUT_FPS),
        "jpeg_quality": JPEG_QUALITY,
        "max_width": MAX_STREAM_WIDTH,
    },
    "high": {
        "max_fps": max(12.0, MAX_OUTPUT_FPS + (4.0 if VideoPipeline.gpu_available() else 2.0)),
        "jpeg_quality": min(92, JPEG_QUALITY + 8),
        "max_width": max(MAX_STREAM_WIDTH, 1600 if VideoPipeline.gpu_available() else 1280),
    },
}


def normalize_stream_profile(profile: str | None) -> str:
    normalized = (profile or "").strip().lower()
    return normalized if normalized in STREAM_PROFILES else "balanced"


class CameraRuntime:
    """Own the long-lived capture, analytics, and streaming loop for one camera."""

    def __init__(self, camera_id: str, source: str, state: dict):
        self.camera_id = camera_id
        self.source = source
        self.stream = CameraStream(source)
        self.pipeline = VideoPipeline(camera_id)
        self.state = state
        self.stream_profile = normalize_stream_profile(DEFAULT_STREAM_PROFILE)
        self._output_config = dict(STREAM_PROFILES[self.stream_profile])
        with self.pipeline.state_lock:
            runtime_status = self.pipeline.get_runtime_status()
            self.state["plate_detector_ready"] = runtime_status["plate_detector_ready"]
            self.state["paddle_ocr_ready"] = runtime_status["paddle_ocr_ready"]
            self.state["easyocr_ready"] = runtime_status["easyocr_ready"]
            self.state["cloud_ocr_ready"] = runtime_status["cloud_ocr_ready"]
            self.state["cloud_ocr_cooldown_seconds"] = runtime_status["cloud_ocr_cooldown_seconds"]
            self.state["ocr_fallback_ready"] = runtime_status["ocr_fallback_ready"]
            self.state["runtime_warnings"] = runtime_status["warnings"]
            self.state["detector_model"] = DETECTION_MODEL_NAME
            self.state["plate_model"] = PLATE_MODEL_NAME
            self.state["device"] = "cuda" if str(self.pipeline.device) != "cpu" else "cpu"
            self.state["stream_profile"] = self.stream_profile

        self._stop_event = threading.Event()
        self._frame_ready = threading.Condition()
        self._analysis_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._analysis_future: concurrent.futures.Future[float] | None = None
        self._latest_jpeg: bytes | None = None
        self._frame_sequence = 0
        self._worker = threading.Thread(
            target=self._run,
            name=f"cybershield-camera-{camera_id}",
            daemon=True,
        )
        self._worker.start()

    @property
    def running(self) -> bool:
        return self.stream.running and self._worker.is_alive() and not self._stop_event.is_set()

    def snapshot_state(self) -> dict:
        return self.pipeline.snapshot_state(self.state)

    def get_stream_profile(self) -> str:
        return self.stream_profile

    def set_stream_profile(self, profile: str) -> None:
        normalized = normalize_stream_profile(profile)
        self.stream_profile = normalized
        self._output_config = dict(STREAM_PROFILES[normalized])
        with self.pipeline.state_lock:
            self.state["stream_profile"] = normalized

    def apply_runtime_settings(self, settings: dict) -> None:
        if "detection_confidence" in settings:
            self.pipeline.set_detection_confidence(float(settings["detection_confidence"]))
        if "plate_confidence" in settings:
            self.pipeline.set_plate_confidence(float(settings["plate_confidence"]))
        if "face_threshold" in settings:
            self.pipeline.set_face_match_threshold(float(settings["face_threshold"]))

    def set_face_match_threshold(self, value: float) -> None:
        self.pipeline.set_face_match_threshold(float(value))

    def release(self) -> None:
        self._stop_event.set()
        self.stream.release()
        with self._frame_ready:
            self._frame_ready.notify_all()
        if self._worker.is_alive():
            self._worker.join(timeout=2.0)
        self._analysis_executor.shutdown(wait=False, cancel_futures=True)
        self.pipeline.shutdown()

    def frame_generator(self) -> Iterator[bytes]:
        last_sequence = -1

        while True:
            with self._frame_ready:
                while (
                    not self._stop_event.is_set()
                    and self.stream.running
                    and self._frame_sequence == last_sequence
                ):
                    self._frame_ready.wait(timeout=1.0)

                if self._frame_sequence == last_sequence:
                    if self._stop_event.is_set() or not self.stream.running:
                        return
                    continue

                payload = self._latest_jpeg
                last_sequence = self._frame_sequence

            if not payload:
                if self._stop_event.is_set() or not self.stream.running:
                    return
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
            )

    def _run(self) -> None:
        analytics_interval = 1.0 / max(ANALYTICS_FPS, 1.0)
        task_refresh_interval = 1.0 / max(TASK_REFRESH_FPS, 1.0)
        last_analysis_submitted_at = 0.0
        last_task_refresh_at = 0.0

        try:
            while not self._stop_event.is_set():
                output_interval = 1.0 / max(min(self.stream.fps, float(self._output_config["max_fps"])), 1.0)
                loop_started = time.perf_counter()
                self._collect_analysis_result()

                success, frame = self.stream.read()
                if not success or frame is None:
                    if self.stream.is_live and not self._stop_event.is_set():
                        time.sleep(0.01)
                        continue
                    break

                now = time.perf_counter()
                analysis_due = (now - last_analysis_submitted_at) >= analytics_interval
                if analysis_due and self._analysis_future is None:
                    with self.pipeline.state_lock:
                        self.state["is_processing"] = True
                    self._analysis_future = self._analysis_executor.submit(self._run_analysis, frame.copy())
                    last_analysis_submitted_at = now

                if (now - last_task_refresh_at) >= task_refresh_interval:
                    self.pipeline.refresh_track_tasks(frame, self.state)
                    last_task_refresh_at = now
                rendered = self.pipeline.render_frame(frame)

                encoded = self._encode_frame(rendered)
                if encoded:
                    with self._frame_ready:
                        self._latest_jpeg = encoded
                        self._frame_sequence += 1
                        self.state["throughput_gbps"] = round((len(encoded) * max(float(self.state.get("stream_fps") or 0.0), 1.0)) / 1_000_000_000, 6)
                        self._frame_ready.notify_all()

                elapsed = time.perf_counter() - loop_started
                sleep_for = max(output_interval - elapsed, 0.0)
                if sleep_for > 0.0:
                    time.sleep(sleep_for)
                with self.pipeline.state_lock:
                    self.state["stream_fps"] = round(1.0 / max(elapsed + sleep_for, 1e-6), 2)
        finally:
            self._collect_analysis_result()
            with self.pipeline.state_lock:
                self.state["is_processing"] = False
            self.stream.running = False
            with self._frame_ready:
                self._frame_ready.notify_all()

    def _collect_analysis_result(self) -> None:
        if self._analysis_future is None or not self._analysis_future.done():
            return

        duration = 0.0
        try:
            duration = float(self._analysis_future.result())
        except Exception:
            duration = 0.0
        finally:
            self._analysis_future = None
            with self.pipeline.state_lock:
                if duration > 0.0:
                    self.state["analytics_fps"] = round(1.0 / max(duration, 1e-6), 2)
                    self.state["inference_latency_ms"] = round(duration * 1000.0, 1)
                self.state["is_processing"] = False

    def _run_analysis(self, frame) -> float:
        started_at = time.perf_counter()
        self.pipeline.process_frame(frame, self.state)
        return time.perf_counter() - started_at

    def _encode_frame(self, frame) -> bytes | None:
        max_stream_width = int(self._output_config["max_width"])
        jpeg_quality = int(self._output_config["jpeg_quality"])
        if max_stream_width > 0 and frame.shape[1] > max_stream_width:
            scale = max_stream_width / frame.shape[1]
            target_size = (max_stream_width, max(int(frame.shape[0] * scale), 1))
            frame = cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)
        ok, buffer = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
        )
        if not ok:
            return None
        return buffer.tobytes()
