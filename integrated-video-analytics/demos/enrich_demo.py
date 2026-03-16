from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from osint_reid.service import get_osint_service
from tests.assets.generate_assets import ensure_assets


def run_demo(video_path: Path) -> None:
    service = get_osint_service()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    camera_id = "demo_cam"
    tracker_id = 1
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        x1 = int(w * 0.15)
        y1 = int(h * 0.2)
        x2 = int(w * 0.65)
        y2 = int(h * 0.9)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
        service.collect_detection(
            camera_id=camera_id,
            tracker_id=tracker_id,
            class_name="person",
            frame=frame,
            bbox_xyxy=(x1, y1, x2, y2),
            ts_iso=ts,
            confidence=0.85,
        )
        frame_idx += 1
        if frame_idx % 8 == 0:
            service.flush_stale()
        time.sleep(0.05)

    cap.release()
    time.sleep(3.0)
    service.flush_stale()
    time.sleep(2.0)

    records = service.db.list_tracklets(limit=10)
    print("Tracklets written:", len(records))
    for rec in records:
        print("-", rec["tracklet_id"], rec.get("resolved_global_id"), rec.get("enrichment_started_at"), rec.get("enrichment_completed_at"))

    incidents = service.pop_incidents()
    if incidents:
        print("Incidents:")
        for incident in incidents:
            print(incident)
    else:
        print("No incidents emitted.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", nargs="?", default="tests/assets/video_sample.mp4")
    args = parser.parse_args()

    ensure_assets()
    path = Path(args.video)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {path}")

    run_demo(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
