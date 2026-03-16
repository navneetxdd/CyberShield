from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from migrations.run import run_migration
from osint_reid.db import OSINTDB, now_utc_iso


def test_osint_end_to_end(monkeypatch, tmp_path):
    db_path = tmp_path / "analytics_osint.db"
    run_migration(db_path=db_path)
    db = OSINTDB(db_path=db_path)

    vec = np.ones((128,), dtype=np.float32)
    db.insert_tracklet(
        tracklet_id="cam_a:1:person",
        camera_id="cam_a",
        start_ts=now_utc_iso(),
        end_ts=now_utc_iso(),
        frame_count=8,
        aggregated_reid=vec,
        aggregated_face=vec,
        color_histogram=np.zeros((8 * 8 * 8,), dtype=np.float32),
        bbox_history=[[now_utc_iso(), 0, 0, 100, 200]],
        plate_assoc=None,
    )

    import osint_reid.api as osint_api

    class StubService:
        def __init__(self):
            self.db = db

        def submit_manual_enrichment(self, tracklet_id: str):
            return {"status": "queued", "tracklet_id": tracklet_id}

        def enrich_tracklet_now(self, tracklet_id: str):
            gid = self.db.create_global_identity(
                camera_id="cam_a",
                seen_ts=now_utc_iso(),
                face_embedding=vec,
                reid_embedding=vec,
                confidence=0.91,
            )
            self.db.set_tracklet_global(tracklet_id, gid)
            return {"status": "linked", "global_id": gid, "score": 0.91}

        def queue_metrics(self):
            return {"pending_enrichments": 0, "active_tracklet_buffers": 0, "incident_buffer": 0}

        def pop_incidents(self):
            return []

    stub = StubService()
    monkeypatch.setattr(osint_api, "get_osint_service", lambda: stub)

    monkeypatch.setenv("ADMIN_API_TOKEN", "secret123")

    import main

    with TestClient(main.app) as client:
        res = client.post(
            "/api/tracklet/cam_a:1:person/enrich",
            headers={"Authorization": "Bearer secret123"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["result"]["status"] == "queued"

        records = client.get("/api/records/tracklets").json()["records"]
        assert any(row["tracklet_id"] == "cam_a:1:person" for row in records)


def test_sahi_rtdetr_script_behavior():
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "osint_reid" / "sahi_rtdetr_test.py"
    result = subprocess.run([sys.executable, str(script)], cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stdout + "\n" + result.stderr).strip()
        raise AssertionError(
            "SAHI/RT-DETR validation failed. Install dependencies with: pip install sahi ultralytics. Details: " + message
        )


test_sahi_rtdetr_script_behavior = pytest.mark.slow(test_sahi_rtdetr_script_behavior)
