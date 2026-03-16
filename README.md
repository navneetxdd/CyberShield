# CyberShield — Integrated AI Video Analytics Platform

CyberShield is a production-grade AI video analytics platform that turns any IP camera or video file into an intelligent surveillance feed. It combines vehicle detection, automatic number plate recognition (ANPR), facial recognition, watchlist alerting, and real-time operator dashboarding in a single deployable FastAPI application.

---

## Table of Contents

1. [What is CyberShield?](#what-is-cybershield)
2. [Key Features](#key-features)
3. [System Architecture](#system-architecture)
4. [Technology Stack](#technology-stack)
5. [Prerequisites](#prerequisites)
6. [Quick Start](#quick-start)
7. [Manual Setup](#manual-setup)
8. [Running the Server](#running-the-server)
9. [Configuration](#configuration)
10. [Operator Dashboard](#operator-dashboard)
11. [ANPR Pipeline](#anpr-pipeline)
12. [API Reference](#api-reference)
13. [Directory Structure](#directory-structure)
14. [Running Tests](#running-tests)
15. [Database](#database)

---

## What is CyberShield?

CyberShield ingests live camera streams or uploaded video files and runs a multi-stage AI pipeline on each frame:

- Detects and tracks every vehicle and person using **YOLO11s + ByteTrack**
- Extracts and reads licence plates through a three-tier OCR stack — **PaddleOCR → EasyOCR → optional cloud OCR**
- Recognises faces, estimates age and gender, and matches against a managed **watchlist** using **InsightFace**
- Persists all events, plates, vehicles, and face records to a local **SQLite** database
- Streams annotated video and live state to an operator dashboard over **MJPEG + WebSocket**
- Exports analytic reports as **PDF** with embedded trend charts

Everything runs locally with no mandatory cloud dependencies. Cloud ANPR enrichment is an opt-in fallback.

---

## Key Features

### Vehicle Intelligence
- YOLO11s object detection (car, motorcycle, bus, truck, person)
- ByteTrack multi-object tracking with unique track IDs
- Vehicle counting, class breakdown, and occupancy metrics
- Per-vehicle plate association with confidence score

### ANPR (Automatic Number Plate Recognition)
- Dedicated YOLOv8 plate detector (fine-tuned `best.pt`) for plate bounding-box extraction
- Three-tier OCR stack with automatic per-frame fallback:
  - **Tier 1** — PaddleOCR (primary, fastest)
  - **Tier 2** — EasyOCR (fallback for low-confidence Paddle reads)
  - **Tier 3** — Cloud OCR via Plate Recognizer API (opt-in last resort)
- Confidence-weighted vote accumulation — plates are confirmed only when the aggregate evidence exceeds configurable thresholds
- Hard cloud confidence floor (`CYBERSHIELD_CLOUD_OCR_MIN_CONFIDENCE`) — low-quality cloud results are discarded before they enter the vote pool
- Plate text normalised and validated against the regex pattern `^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4}$` before any vote is cast
- `pending_plates` state propagated to the operator incident rail so in-progress reads are visible before confirmation

### Facial Recognition & Watchlist
- InsightFace `buffalo_l` model for 512-d face embeddings
- Age estimation and gender classification on every detected face
- Cosine-similarity watchlist matching with configurable threshold
- Watchlist identities managed from the dashboard or by dropping images into `watchlist/`
- Watchlist hit events generate immediate operator alerts

### Operator Dashboard
- Compact "Operations Overview" KPI strip — total vehicles, faces, plate reads, and OCR source breakdown
- "Operational Incidents" rail — real-time feed of watchlist hits, low-confidence plates, pending ANPR candidates, and system events
- Live MJPEG camera stream per feed
- Historical trend charts — traffic flow, vehicle class, gender
- Searchable, filterable record tabs for plates, faces, and vehicles
- Collapsible administration section for watchlist management
- PDF export of the full analytic session

### Production Record Filters
- **ANPR quality filter** — show only reads above a minimum confidence percentage
- **OCR source filter** — isolate records by `paddle`, `easyocr`, or `cloud` origin
- **Watchlist-only** — surface only face records that triggered a watchlist match
- **Vehicle with plate** — show only vehicles that have a confirmed plate association
- All filters are applied at the database query layer, not in JavaScript

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CyberShield                           │
│                                                              │
│  ┌──────────┐   ┌──────────────────────────────────────────┐│
│  │  Camera  │──▶│           CameraRuntime (runtime.py)     ││
│  │  /Video  │   │  - frame queue, lifecycle management     ││
│  └──────────┘   └────────────────┬─────────────────────────┘│
│                                  │ frames                    │
│                 ┌────────────────▼─────────────────────────┐│
│                 │           VideoPipeline (pipeline.py)     ││
│                 │                                           ││
│                 │  ①  YOLO11s detection (vehicles/people)  ││
│                 │  ②  ByteTrack multi-object tracking      ││
│                 │  ③  Plate detector (YOLOv8 crop)        ││
│                 │       └─ PaddleOCR                       ││
│                 │       └─ EasyOCR fallback                ││
│                 │       └─ Cloud OCR last resort           ││
│                 │  ④  Confidence vote accumulation         ││
│                 │  ⑤  InsightFace face analysis           ││
│                 │       └─ Embedding + watchlist match     ││
│                 │       └─ Age / gender estimation         ││
│                 │  ⑥  Annotated frame rendering           ││
│                 └───────────┬─────────────────┬────────────┘│
│                             │ state            │ frame       │
│              ┌──────────────▼──────┐  ┌───────▼───────────┐│
│              │  database.py        │  │  MJPEG stream      ││
│              │  SQLite analytics.db│  │  WebSocket state   ││
│              └──────────────┬──────┘  └───────────────────┘│
│                             │                               │
│              ┌──────────────▼──────────────────────────────┐│
│              │         FastAPI  (main.py)                   ││
│              │  - REST API    - PDF report endpoint         ││
│              │  - WebSocket   - Watchlist management        ││
│              │  - Upload API  - Record filter endpoints     ││
│              └──────────────┬──────────────────────────────┘│
│                             │ HTTP                           │
│              ┌──────────────▼──────────────────────────────┐│
│              │     Operator Dashboard (templates/index.html)││
│              │  Tailwind CSS · Chart.js · Vanilla JS        ││
│              └─────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Ingest** — `CameraRuntime` opens an OpenCV `VideoCapture` on the camera URL or uploaded file and pushes decoded frames into a bounded queue.
2. **Detect** — `VideoPipeline` runs YOLO11s inference on each frame producing bounding boxes and class labels.
3. **Track** — ByteTrack assigns a stable integer track ID to each detection across frames.
4. **ANPR** — For every vehicle track, a secondary fine-tuned YOLOv8 plate detector crops the plate region. The crop is passed through the OCR stack. Each OCR result is validated (`normalize_plate_text`) and entered into a per-tracker vote dictionary. A plate is confirmed only when `_is_plate_vote_confirmed()` is satisfied.
5. **Face** — InsightFace extracts 512-d embeddings from every detected face. Cosine similarity is computed against all watchlist embeddings. Hits are flagged and logged as events.
6. **Persist** — Confirmed plates, vehicles, faces, and system events are written to `analytics.db` via `database.py`.
7. **Stream** — Annotated frames are JPEG-encoded and emitted on an MJPEG endpoint. Live state (recent vehicles, plates, faces, incidents) is broadcast over a WebSocket.
8. **Dashboard** — The single-page operator dashboard polls the WebSocket and REST endpoints, renders the incident rail, KPI strip, record tables, and charts.

---

## Technology Stack

| Component | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Object detection | YOLO11s (Ultralytics) |
| Multi-object tracking | ByteTrack (via Supervision) |
| Plate detection | YOLOv8 fine-tuned on licence plates |
| Primary OCR | PaddleOCR |
| Fallback OCR | EasyOCR |
| Cloud OCR (opt-in) | Plate Recognizer API |
| Face analysis | InsightFace `buffalo_l` |
| Database | SQLite (WAL mode) |
| Frontend | Tailwind CSS, Chart.js, Vanilla JS |
| PDF reports | fpdf2 + Matplotlib |
| Video I/O | OpenCV |
| Testing | pytest |

---

## Prerequisites

- **Python 3.10 or 3.11** (3.12+ not tested with all ML dependencies)
- **pip** and **venv**
- **4 GB RAM minimum** (8 GB+ recommended for simultaneous face + plate analysis)
- NVIDIA GPU with CUDA optional but recommended for real-time multi-stream use
- Internet access on first run to download model weights (YOLOv8, InsightFace, OCR assets)

---

## Quick Start

Clone the repository and run from the workspace root using the provided launcher:

```bash
git clone https://github.com/navneetxdd/CyberShield.git
cd CyberShield
```

Create the virtual environment inside `integrated-video-analytics/`:

```bash
cd integrated-video-analytics
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS
pip install -r requirements.txt
cd ..
```

Start the server:

```bash
python run.py
```

Open **http://localhost:8080** in your browser.

> `run.py` is a thin launcher at the repo root that `chdir`s into `integrated-video-analytics/` and executes `main.py` using the project's own virtual environment. It handles relative-path resolution so you never need to `cd` manually.

---

## Manual Setup

If you prefer to run directly from inside the application directory:

```bash
cd integrated-video-analytics
.venv\Scripts\activate
python main.py
```

The server binds to `0.0.0.0:8080` by default.

---

## Running the Server

### First Run

On the first run the following assets are downloaded automatically if missing:

| Asset | Source |
|---|---|
| `yolo11s.pt` | Ultralytics |
| Plate detection model `best.pt` (if missing locally) | Hugging Face (yasirfaizahmed) |
| InsightFace `buffalo_l` | InsightFace model zoo |
| PaddleOCR recognition weights | PaddlePaddle CDN |
| EasyOCR recognition weights | GitHub release |

Subsequent starts are fast — all assets are cached locally.

### Upload a video

Use the **Upload** button on the dashboard or `POST /api/upload` to add a video file. Once uploaded the stream starts automatically and appears in the camera list.

---

## Configuration

All configuration is via environment variables. None are required — the system works with sensible defaults and local-only OCR.

### Core

| Variable | Default | Description |
|---|---|---|
| `CYBERSHIELD_DETECT_MODEL` | auto | Override the primary YOLO detector path or model name |
| `CYBERSHIELD_PLATE_MODEL` | HuggingFace URL | Override the plate detector path or URL |
| `CYBERSHIELD_DETECT_IMGSZ` | `896` | Detector inference image size |
| `CYBERSHIELD_MAX_UPLOAD_SIZE` | `512MB` | Maximum upload file size (e.g. `1GB`) |
| `CYBERSHIELD_ALLOWED_ORIGINS` | `*` | Comma-separated CORS allowed origins |

### ANPR / OCR

| Variable | Default | Description |
|---|---|---|
| `CYBERSHIELD_ENABLE_PADDLE_OCR` | `true` | Enable PaddleOCR primary path |
| `CYBERSHIELD_ENABLE_EASYOCR_FALLBACK` | `true` | Enable EasyOCR fallback path |
| `CYBERSHIELD_PADDLE_PRIMARY_MIN_CONFIDENCE` | `0.75` | Minimum confidence to accept a PaddleOCR result directly without fallback |
| `CYBERSHIELD_CLOUD_OCR_MIN_CONFIDENCE` | `0.78` | Hard floor on cloud OCR confidence — results below this are discarded |
| `PLATE_RECOGNIZER_API_TOKEN` | _(unset)_ | Enables cloud OCR via Plate Recognizer; leave unset to run local-only |

### Tracking

| Variable | Default | Description |
|---|---|---|
| `CYBERSHIELD_TRACK_ACTIVATION_THRESHOLD` | `0.13` | ByteTrack activation confidence threshold |
| `CYBERSHIELD_TRACK_MATCHING_THRESHOLD` | `0.65` | ByteTrack IoU matching threshold |
| `CYBERSHIELD_TRACK_LOST_BUFFER` | `60` | Frames to keep lost tracks before dropping |
| `CYBERSHIELD_TRACK_FRAME_RATE` | `8` (CPU), `12` (GPU) | Tracker frame-rate hint |

### Throughput Targets

| Variable | Default |
|---|---|
| `CYBERSHIELD_STREAM_MAX_FPS` | `14` (CPU), `24` (GPU) |
| `CYBERSHIELD_ANALYTICS_FPS` | `8` (CPU), `10` (GPU) |
| `CYBERSHIELD_TASK_REFRESH_FPS` | `6` (CPU), `10` (GPU) |

---

## Operator Dashboard

The dashboard is a single-page application served at `http://localhost:8080`.

### Layout

```
┌─────────────────────────────────────────────────────┐
│  Operations Overview  (KPI strip)                   │
│  Total Vehicles · Total Faces · Plate Reads ·       │
│  OCR source breakdown                               │
├─────────────────────┬───────────────────────────────┤
│                     │  Operational Incidents        │
│  Live Camera Feed   │  (watchlist hits, low-conf    │
│  (MJPEG stream)     │   plates, pending ANPR,       │
│                     │   system events)              │
├─────────────────────┴───────────────────────────────┤
│  Records                                            │
│  [ ANPR Records ] [ Face Records ] [ Vehicle ] ← filter controls per tab │
├──────────────────────────────────────────────────── │
│  ▶ Administration  (collapsible)                    │
│    Watchlist management                             │
└─────────────────────────────────────────────────────┘
```

### Record Filters

Each record tab has live filter controls that query the database in real time:

| Control | Applies to | Effect |
|---|---|---|
| ANPR quality | Plate records | Minimum confidence % |
| OCR source | Plate records | `paddle` / `easyocr` / `cloud` |
| Watchlist only | Face records | Hides non-watchlist faces |
| With plate only | Vehicle records | Hides vehicles without a confirmed plate |

---

## ANPR Pipeline

```
Frame
  │
  ▼
Plate detector (YOLOv8 fine-tuned)
  │ crop
  ▼
normalize_plate_text() ──── invalid → discard
  │ valid
  ▼
PaddleOCR
  │ confidence < threshold?
  ▼
EasyOCR fallback
  │ still low confidence?
  ▼
Cloud OCR (if PLATE_RECOGNIZER_API_TOKEN set)
  │ cloud_confidence < CYBERSHIELD_CLOUD_OCR_MIN_CONFIDENCE → discard
  ▼
normalize_plate_text() ──── invalid → discard
  │ valid
  ▼
Vote accumulator (per tracker)
  │
_is_plate_vote_confirmed()?
├── YES → confirmed plate stored → vehicle record updated
└── NO  → pending_plates[] → visible in incident rail
```

A plate is confirmed when either of the following is true:
- **Direct path**: Best single-read confidence ≥ `PLATE_DIRECT_ACCEPT_CONFIDENCE` AND at least 1 hit
- **Aggregate path**: Hit count ≥ `PLATE_CONFIRMATION_HITS` AND aggregate score ≥ `PLATE_MIN_AGGREGATE_SCORE`

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Operator dashboard HTML |
| `GET` | `/api/health` | System health snapshot |
| `GET` | `/api/state` | Live pipeline state (cameras, recent events) |
| `WS` | `/ws/state` | WebSocket — continuous state broadcast |
| `GET` | `/api/stream/{camera_id}` | MJPEG annotated video stream |
| `POST` | `/api/upload` | Upload a video file to create a camera feed |
| `DELETE` | `/api/camera/{camera_id}` | Stop and remove a camera |
| `GET` | `/api/records/plates` | Plate read history (`min_confidence`, `ocr_source`) |
| `GET` | `/api/records/faces` | Face record history (`watchlist_only`) |
| `GET` | `/api/records/vehicles` | Vehicle record history (`require_plate`) |
| `GET` | `/api/records/events` | System event log |
| `GET` | `/api/analytics/traffic` | Hourly traffic breakdown |
| `GET` | `/api/analytics/ocr` | OCR source and confidence distribution |
| `GET` | `/api/metrics/history` | Long-term metric time series |
| `GET` | `/api/watchlist` | Registered watchlist identities |
| `POST` | `/api/watchlist` | Add a watchlist identity (image upload) |
| `DELETE` | `/api/watchlist/{name}` | Remove a watchlist identity |
| `GET` | `/api/report/pdf` | Export full analytic report as PDF |

---

## Directory Structure

```
CyberShield/
├── run.py                          ← root-level launcher (start here)
├── pyrightconfig.json              ← type-checking config
├── README.md                       ← this file
└── integrated-video-analytics/
    ├── main.py                     ← FastAPI application, all routes
    ├── pipeline.py                 ← AI pipeline (detection, OCR, face)
    ├── database.py                 ← SQLite access layer
    ├── runtime.py                  ← camera lifecycle management
    ├── camera.py                   ← camera utilities
    ├── requirements.txt
    ├── analytics.db                ← SQLite database (auto-created)
    ├── yolo11s.pt                  ← primary detector weights
    ├── weights/
    │   └── best.pt                 ← plate detector weights
    ├── templates/
    │   └── index.html              ← single-page operator dashboard
    ├── uploads/                    ← uploaded video files
    ├── watchlist/                  ← watchlist identity images
    └── tests/
        ├── conftest.py
        ├── test_main.py
        ├── test_pipeline.py
        └── test_database.py
```

---

## Running Tests

```bash
cd integrated-video-analytics
.venv\Scripts\activate
python -m pytest tests/ -v
```

All 23 tests should pass. The test suite covers:

- Pipeline unit tests — `_is_plate_vote_confirmed`, cloud confidence floor, plate normalisation
- Database unit tests — all record filter combinations (confidence, source, watchlist-only, require-plate)
- API integration tests — route correctness, filter parameter validation, 400 error paths

---

## Database

CyberShield stores all data in `integrated-video-analytics/analytics.db` — a single SQLite file in WAL mode.

| Table | Contents |
|---|---|
| `plate_reads` | Confirmed licence plates with OCR source, confidence, timestamp |
| `vehicles` | Tracked vehicles with class, colour, plate association |
| `faces` | Detected faces with age, gender, watchlist hit flag, embedding hash |
| `events` | System event log (watchlist alerts, ANPR confirmations, errors) |
| `metrics` | Time-series KPI snapshots for trend charts |

The database is auto-created on first run. No migration steps are needed.
