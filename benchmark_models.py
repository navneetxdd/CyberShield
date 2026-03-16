"""
CyberShield YOLO Model Benchmark
Tests yolov8n, yolov8s, yolov8m, yolo11n, yolo11s on the uploaded test video.
Metrics: inference latency, FPS, detection count, memory usage.
"""

import sys
import time
import gc
import os
import statistics

# Add venv to path
VENV_SITE = os.path.join(
    os.path.dirname(__file__),
    "integrated-video-analytics", ".venv", "Lib", "site-packages"
)
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

import cv2
import psutil
import torch
from ultralytics import YOLO

# ── Config ────────────────────────────────────────────────────────────────────
VIDEO_PATH = os.path.join(
    os.path.dirname(__file__),
    "integrated-video-analytics", "uploads",
    "camera_1_1773653659_131232-749706873.mp4"
)
MODELS = ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolo11n.pt", "yolo11s.pt"]
WARMUP_FRAMES = 10   # frames discarded before timing starts
BENCH_FRAMES  = 100  # frames timed
IMG_SIZE      = 736  # same as pipeline.py CPU default
CONF          = 0.25
# ─────────────────────────────────────────────────────────────────────────────


def get_ram_mb():
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / (1024 * 1024)


def bench_model(model_name: str, video_path: str):
    print(f"\n{'='*60}")
    print(f"  Benchmarking: {model_name}")
    print(f"{'='*60}")

    # Load model
    t0 = time.perf_counter()
    model = YOLO(model_name)
    load_time = time.perf_counter() - t0
    print(f"  Load time : {load_time:.2f}s")

    # Force CPU (no CUDA on this machine)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    print(f"  Device    : {device}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  ERROR: Cannot open {video_path}")
        return None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"  Video     : {total_frames} frames")

    latencies   = []
    det_counts  = []
    frame_idx   = 0
    errors      = 0

    while frame_idx < WARMUP_FRAMES + BENCH_FRAMES:
        ret, frame = cap.read()
        if not ret:
            # Loop video
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                errors += 1
                break

        if frame_idx < WARMUP_FRAMES:
            # Warmup — run inference but don't time
            try:
                model.predict(frame, imgsz=IMG_SIZE, conf=CONF,
                              device=device, verbose=False)
            except Exception:
                pass
            frame_idx += 1
            continue

        # Timed inference
        t_start = time.perf_counter()
        try:
            results = model.predict(frame, imgsz=IMG_SIZE, conf=CONF,
                                    device=device, verbose=False)
            t_end = time.perf_counter()
            latencies.append((t_end - t_start) * 1000)  # ms
            det_counts.append(len(results[0].boxes) if results[0].boxes else 0)
        except Exception as e:
            errors += 1
            t_end = time.perf_counter()

        frame_idx += 1

        if frame_idx % 30 == 0:
            pct = (frame_idx - WARMUP_FRAMES) / BENCH_FRAMES * 100
            print(f"  Progress  : {pct:.0f}%  (frame {frame_idx})", end="\r")

    cap.release()
    print(" " * 60, end="\r")  # clear progress line

    if not latencies:
        print("  ERROR: No frames processed")
        return None

    ram_mb = get_ram_mb()

    result = {
        "model"       : model_name,
        "load_s"      : round(load_time, 2),
        "frames"      : len(latencies),
        "errors"      : errors,
        "lat_mean_ms" : round(statistics.mean(latencies), 1),
        "lat_p99_ms"  : round(sorted(latencies)[int(len(latencies) * 0.99)], 1),
        "lat_min_ms"  : round(min(latencies), 1),
        "fps"         : round(1000 / statistics.mean(latencies), 1),
        "det_mean"    : round(statistics.mean(det_counts), 2),
        "ram_mb"      : round(ram_mb, 0),
    }

    print(f"  Latency   : {result['lat_mean_ms']} ms avg  |  {result['lat_p99_ms']} ms p99")
    print(f"  FPS       : {result['fps']}")
    print(f"  Detections: {result['det_mean']} avg/frame")
    print(f"  RAM       : {result['ram_mb']} MB")
    print(f"  Errors    : {errors}")

    # Free memory before next model
    del model
    gc.collect()
    torch.cuda.empty_cache() if torch.cuda.is_available() else None

    return result


def print_table(results):
    # Score formula:
    #   lower latency is better  → latency_score = 1000 / lat_mean_ms  (FPS equivalent)
    #   higher det_mean is better → normalised 0-1
    #   lower RAM is better       → normalised 0-1 inverted
    # Composite = 0.50*fps_score + 0.30*det_score + 0.20*ram_score  (all normalised)

    fps_vals  = [r["fps"]      for r in results]
    det_vals  = [r["det_mean"] for r in results]
    ram_vals  = [r["ram_mb"]   for r in results]

    fps_max  = max(fps_vals)  or 1
    det_max  = max(det_vals)  or 1
    ram_max  = max(ram_vals)  or 1

    scored = []
    for r in results:
        fps_s = r["fps"]      / fps_max        # higher is better → normalise by max
        det_s = r["det_mean"] / det_max         # higher is better
        ram_s = 1 - (r["ram_mb"] / ram_max)    # lower RAM is better
        composite = 0.50 * fps_s + 0.30 * det_s + 0.20 * ram_s
        scored.append({**r, "score": round(composite * 100, 1)})

    scored.sort(key=lambda x: -x["score"])

    col_w = [14, 8, 10, 10, 10, 10, 10, 8, 6]
    headers = ["Model", "FPS", "Lat(ms)", "P99(ms)", "Det/fr", "RAM(MB)", "Load(s)", "Errs", "Score"]

    sep = "+" + "+".join("-" * w for w in col_w) + "+"
    hdr = "|" + "|".join(h.center(w) for h, w in zip(headers, col_w)) + "|"

    print("\n\n" + "=" * 60)
    print("  BENCHMARK RESULTS  (sorted by composite score)")
    print("=" * 60)
    print(sep)
    print(hdr)
    print(sep)

    for i, r in enumerate(scored):
        tag = " ← WINNER" if i == 0 else ""
        row_vals = [
            r["model"],
            str(r["fps"]),
            str(r["lat_mean_ms"]),
            str(r["lat_p99_ms"]),
            str(r["det_mean"]),
            str(r["ram_mb"]),
            str(r["load_s"]),
            str(r["errors"]),
            str(r["score"]),
        ]
        print("|" + "|".join(v.center(w) for v, w in zip(row_vals, col_w)) + "|" + tag)

    print(sep)
    print("\nScore formula: 50% FPS + 30% Detection density + 20% RAM efficiency")
    print(f"\nWinner: {scored[0]['model']}")
    print(f"  → {scored[0]['fps']} FPS  |  {scored[0]['lat_mean_ms']} ms  |  {scored[0]['ram_mb']} MB RAM  |  score {scored[0]['score']}/100")


def main():
    if not os.path.exists(VIDEO_PATH):
        print(f"ERROR: Test video not found: {VIDEO_PATH}")
        print("Available uploads:")
        uploads = os.path.join(os.path.dirname(__file__), "integrated-video-analytics", "uploads")
        for f in os.listdir(uploads):
            print(f"  {f}")
        sys.exit(1)

    print("CyberShield YOLO Model Benchmark")
    print(f"Video : {os.path.basename(VIDEO_PATH)}")
    print(f"Frames: {WARMUP_FRAMES} warmup + {BENCH_FRAMES} timed  |  imgsize={IMG_SIZE}")
    print(f"Device: {'CUDA' if torch.cuda.is_available() else 'CPU'}")

    results = []
    for model_name in MODELS:
        r = bench_model(model_name, VIDEO_PATH)
        if r:
            results.append(r)

    if results:
        print_table(results)


if __name__ == "__main__":
    main()
