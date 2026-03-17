"""
One-shot OSINT seed: inserts Marcus J. Webb into analytics.db with realistic
cross-camera movement data, face snapshot from vi3.mp4, and full watchlist profile.
Run from the integrated-video-analytics directory:
    python seed_osint.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "analytics.db"
SNAPSHOT_DIR = BASE_DIR / "uploads" / "snapshots"
WATCHLIST_DIR = BASE_DIR / "watchlist"
VIDEO_PATH = Path(r"C:\Users\jaipr\Downloads\vi3.mp4")

# ── helpers ───────────────────────────────────────────────────────────────────

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def ts_offset(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).isoformat(timespec="seconds")

def rand_vec(dim: int) -> bytes:
    vec = np.random.randn(dim).astype(np.float32)
    vec /= np.linalg.norm(vec) + 1e-8
    return vec.tobytes()

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# ── migrations (idempotent) ───────────────────────────────────────────────────

def run_migrations() -> None:
    sql_path = BASE_DIR / "migrations" / "0001_add_tracklets_global_sql.sql"
    if not sql_path.exists():
        print(f"[WARN] Migration SQL not found: {sql_path}")
        return
    conn = connect()
    try:
        conn.executescript(sql_path.read_text(encoding="utf-8"))
        # Also ensure analytics.db tables exist (from database.py)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                vehicle_count INTEGER DEFAULT 0,
                people_count INTEGER DEFAULT 0,
                zone_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS vehicle_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                tracker_id INTEGER NOT NULL,
                vehicle_type TEXT NOT NULL,
                plate_text TEXT,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, tracker_id)
            );
            CREATE TABLE IF NOT EXISTS plate_reads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                tracker_id INTEGER,
                plate_text TEXT NOT NULL,
                vehicle_type TEXT NOT NULL,
                confidence REAL,
                ocr_source TEXT NOT NULL DEFAULT 'unknown',
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, plate_text)
            );
            CREATE TABLE IF NOT EXISTS face_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT NOT NULL,
                tracker_id INTEGER NOT NULL,
                identity TEXT,
                gender TEXT,
                age INTEGER,
                watchlist_hit INTEGER NOT NULL DEFAULT 0,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(camera_id, tracker_id)
            );
        """)
        conn.commit()
        print("[OK] Migrations applied.")
    finally:
        conn.close()

# ── face snapshot from video ──────────────────────────────────────────────────

def extract_face_snapshot() -> bytes | None:
    if not VIDEO_PATH.exists():
        print(f"[WARN] Video not found at {VIDEO_PATH} — skipping snapshot extraction")
        return None
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        print("[WARN] Could not open video — skipping snapshot extraction")
        return None
    # Seek to ~2 seconds in where face is clearly visible
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 2.0))
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        print("[WARN] Could not read frame from video")
        return None
    # Resize to thumbnail
    h, w = frame.shape[:2]
    scale = 240 / max(h, w)
    thumb = cv2.resize(frame, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        return None
    print(f"[OK] Extracted face snapshot ({thumb.shape[1]}x{thumb.shape[0]}) from {VIDEO_PATH.name}")
    return bytes(buf)

# ── seed ──────────────────────────────────────────────────────────────────────

def seed() -> None:
    np.random.seed(42)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    WATCHLIST_DIR.mkdir(parents=True, exist_ok=True)

    run_migrations()

    conn = connect()

    # ── check if already seeded ──
    existing = conn.execute(
        "SELECT global_id FROM global_identities WHERE watchlist_meta LIKE '%Marcus%' LIMIT 1"
    ).fetchone()
    if existing:
        global_id = existing[0]
        print(f"[INFO] Marcus already seeded as {global_id} — refreshing data.")
        conn.execute("DELETE FROM tracklets WHERE resolved_global_id=?", (global_id,))
        conn.execute("DELETE FROM identity_incidents WHERE candidate_global_id=?", (global_id,))
        conn.execute("DELETE FROM global_identities WHERE global_id=?", (global_id,))
        conn.execute("DELETE FROM face_records WHERE identity='Marcus_Webb'", )
        conn.commit()

    conn.close()

    # ── timestamps (simulates a 12-min walk through 3 cameras) ──
    base = datetime(2026, 3, 17, 9, 14, 23, tzinfo=timezone.utc)
    cam_events = [
        ("camera_1", "Entry Gate",      0,    347),   # 0-5m 47s
        ("camera_2", "Main Corridor",   382,  612),   # +6m 22s later, 4m 10s duration
        ("camera_3", "Exit Lobby",      703,  890),   # +3m 29s after cam2, 3m 7s duration
    ]

    # ── global identity ──
    global_id = f"gid_{uuid.uuid4().hex[:12]}"
    face_snap = extract_face_snapshot()

    created_ts  = ts_offset(base, 0)
    last_seen   = ts_offset(base, cam_events[-1][2] + cam_events[-1][3])

    watchlist_meta = {
        "display_name":       "Marcus_Webb",
        "full_name":          "Marcus J. Webb",
        "dob":                "1984-06-15",
        "nationality":        "British",
        "phone":              "+44 7700 900 247",
        "email":              "m.webb@privateemail.net",
        "last_known_address": "Flat 4B, 22 Harrow Rd, London W2 1AN",
        "vehicle_reg":        "LK19 RVX",
        "vehicle_desc":       "Dark grey BMW 5-series",
        "threat_level":       "MEDIUM",
        "notes":              (
            "Person of interest — observed within 200m of restricted zone on "
            "2026-03-15 and again 2026-03-17. Known associate of watch-flagged "
            "individuals. Do not approach; maintain surveillance only."
        ),
        "snapshot_filename":  f"Marcus_Webb.jpg",
        "snapshot_path":      str(SNAPSHOT_DIR / f"{global_id}_{created_ts.replace(':', '-')}.jpg"),
    }

    # Save face snapshot to disk
    if face_snap:
        snap_path = Path(watchlist_meta["snapshot_path"])
        snap_path.write_bytes(face_snap)
        (WATCHLIST_DIR / "Marcus_Webb.jpg").write_bytes(face_snap)
        print(f"[OK] Snapshot saved -> {snap_path.name}")
    else:
        # Create a placeholder gray image
        placeholder = np.full((160, 120, 3), 60, dtype=np.uint8)
        cv2.putText(placeholder, "SUBJ", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (200, 200, 200), 2)
        _, buf = cv2.imencode(".jpg", placeholder)
        snap_path = Path(watchlist_meta["snapshot_path"])
        snap_path.write_bytes(bytes(buf))
        (WATCHLIST_DIR / "Marcus_Webb.jpg").write_bytes(bytes(buf))

    conn = connect()
    try:
        conn.execute(
            """INSERT INTO global_identities
               (global_id, created_at, last_seen_ts, last_seen_camera,
                face_embedding, reid_embedding, watchlist_flag, watchlist_meta, confidence)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0.94)""",
            (
                global_id, created_ts, last_seen, cam_events[-1][0],
                rand_vec(512), rand_vec(512),
                json.dumps(watchlist_meta),
            ),
        )
        print(f"[OK] Global identity created: {global_id} (Marcus J. Webb)")

        # ── tracklets ──
        tracklet_ids: list[str] = []
        for cam_id, cam_label, t_start, duration in cam_events:
            tid = f"trk_{uuid.uuid4().hex[:12]}"
            start_ts = ts_offset(base, t_start)
            end_ts   = ts_offset(base, t_start + duration)
            # Simulate 25fps × duration frames
            frame_count = int(duration * 12)   # ~12 fps effective analysis rate
            bbox_history = [[120 + i * 3, 80, 200, 380] for i in range(min(frame_count, 20))]

            conn.execute(
                """INSERT INTO tracklets
                   (tracklet_id, camera_id, start_ts, end_ts, frame_count,
                    aggregated_reid, aggregated_face, color_histogram, bbox_history,
                    plate_assoc, resolved_global_id,
                    enrichment_started_at, enrichment_completed_at, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)""",
                (
                    tid, cam_id, start_ts, end_ts, frame_count,
                    rand_vec(512), rand_vec(512), rand_vec(512),
                    json.dumps(bbox_history),
                    global_id,
                    start_ts,
                    end_ts,
                    end_ts,
                ),
            )
            tracklet_ids.append(tid)
            print(f"[OK] Tracklet {tid} — {cam_id} ({cam_label})  {start_ts} → {end_ts}  ({frame_count} frames)")

        # ── cross-camera incidents ──
        for i in range(1, len(tracklet_ids)):
            iid = f"iid_{uuid.uuid4().hex[:12]}"
            prev_cam = cam_events[i - 1][0]
            curr_cam = cam_events[i][0]
            conn.execute(
                """INSERT INTO identity_incidents
                   (incident_id, tracklet_id, candidate_global_id, reason, score,
                    created_at, resolved, operator_action)
                   VALUES (?, ?, ?, ?, ?, ?, 1, 'accepted')""",
                (
                    iid,
                    tracklet_ids[i],
                    global_id,
                    f"cross_camera_continuity:{prev_cam}→{curr_cam}",
                    round(0.87 + i * 0.03, 3),
                    ts_offset(base, cam_events[i][2]),
                ),
            )
            print(f"[OK] Incident {iid}: {prev_cam} → {curr_cam}")

        # ── face_records (analytics.db) ──
        for idx, (cam_id, _, t_start, duration) in enumerate(cam_events):
            tracker_id = 1000 + idx
            start_ts = ts_offset(base, t_start)
            end_ts   = ts_offset(base, t_start + duration)
            conn.execute(
                """INSERT OR REPLACE INTO face_records
                   (camera_id, tracker_id, identity, gender, age, watchlist_hit, first_seen, last_seen)
                   VALUES (?, ?, 'Marcus_Webb', 'M', 41, 1, ?, ?)""",
                (cam_id, tracker_id, start_ts, end_ts),
            )

        conn.commit()
        print(f"\n[DONE] Seeded Marcus J. Webb  global_id={global_id}")
        print(f"       DB  → {DB_PATH}")
        print(f"       Snap→ {SNAPSHOT_DIR}")

    finally:
        conn.close()

    # Write global_id to a temp file so the API endpoint can reference it
    (BASE_DIR / ".seed_global_id").write_text(global_id, encoding="utf-8")


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    sys.path.insert(0, str(BASE_DIR))
    seed()
