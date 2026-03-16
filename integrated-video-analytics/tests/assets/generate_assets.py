from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import requests

BASE_DIR = Path(__file__).resolve().parent


def _download(url: str, path: Path) -> None:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    path.write_bytes(response.content)


def ensure_assets() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    sample = BASE_DIR / "sample1.jpg"
    face = BASE_DIR / "face1.jpg"
    vehicle = BASE_DIR / "vehicle1.jpg"
    video = BASE_DIR / "video_sample.mp4"

    if not sample.exists():
        _download("https://ultralytics.com/images/bus.jpg", sample)
    if not face.exists():
        _download("https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg", face)
    if not vehicle.exists():
        _download("https://ultralytics.com/images/bus.jpg", vehicle)

    if not video.exists():
        frame = cv2.imread(str(sample))
        if frame is None:
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        height, width = frame.shape[:2]
        _fourcc_fn = getattr(cv2, "VideoWriter_fourcc")
        fourcc = _fourcc_fn(*"mp4v")
        writer = cv2.VideoWriter(str(video), fourcc, 10.0, (width, height))
        for i in range(50):
            canvas = frame.copy()
            cv2.putText(canvas, f"frame {i}", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            writer.write(canvas)
        writer.release()


if __name__ == "__main__":
    ensure_assets()
    print("Assets ready in", BASE_DIR)
