from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2


def fail(msg: str) -> int:
    print(msg)
    print("Install guidance: pip install sahi ultralytics")
    return 2


def main() -> int:
    base_dir = Path(__file__).resolve().parents[1]
    sample_path = base_dir / "tests" / "assets" / "sample1.jpg"
    if not sample_path.exists():
        return fail(f"Sample image missing: {sample_path}")

    image = cv2.imread(str(sample_path))
    if image is None:
        return fail(f"Could not read sample image: {sample_path}")

    try:
        from sahi import AutoDetectionModel
        from sahi.predict import get_sliced_prediction
    except Exception as exc:
        return fail(f"SAHI import failed: {exc}")

    try:
        from ultralytics import RTDETR
    except Exception as exc:
        return fail(f"RT-DETR import failed from ultralytics: {exc}")

    yolo_model_path = base_dir / "yolo11s.pt"
    if not yolo_model_path.exists():
        yolo_model_path = Path("yolo11s.pt")

    device = "cuda:0" if __import__("torch").cuda.is_available() else "cpu"

    try:
        detection_model = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=str(yolo_model_path),
            confidence_threshold=0.15,
            device=device,
        )
    except Exception as exc:
        return fail(f"Failed to initialize SAHI model: {exc}")

    start = time.perf_counter()
    sahi_pred = get_sliced_prediction(
        image=image,
        detection_model=detection_model,
        slice_height=512,
        slice_width=512,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
    )
    sahi_ms = (time.perf_counter() - start) * 1000.0
    sahi_count = len(sahi_pred.object_prediction_list or [])
    print(f"SAHI detections={sahi_count} latency_ms={sahi_ms:.2f}")
    if sahi_count <= 0:
        return fail("SAHI produced zero detections on sample image.")

    try:
        rtdetr = RTDETR("rtdetr-l.pt")
    except Exception as exc:
        return fail(f"Failed to initialize RT-DETR model: {exc}")

    start = time.perf_counter()
    results = rtdetr.predict(source=image, conf=0.15, verbose=False, device=device)
    rt_ms = (time.perf_counter() - start) * 1000.0
    boxes = 0
    if results and results[0].boxes is not None:
        boxes = len(results[0].boxes)
    print(f"RT-DETR detections={boxes} latency_ms={rt_ms:.2f}")
    if boxes <= 0:
        return fail("RT-DETR produced zero detections on sample image.")

    print("SAHI and RT-DETR validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
