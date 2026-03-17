# CyberShield — System Architecture & Implementation Reference

**Last updated:** 2026-03-17
**Repo:** https://github.com/navneetxdd/CyberShield
**Latest commit:** `af84bbd4` — feat: OSINT graph, Weapons/Persons views, camera grid fix, demo sequence

---

## 1. Project Overview

CyberShield is a real-time AI-powered video surveillance platform. It processes live or recorded camera feeds through a multi-stage ML pipeline (detection → tracking → ANPR → face recognition → ReID → cross-camera identity linkage) and presents results through a React dashboard served directly by the FastAPI backend.

**Key capabilities:**
- Multi-camera live feed processing with GPU/CPU adaptive scheduling
- Automatic Number Plate Recognition (ANPR) with dual OCR (PaddleOCR + EasyOCR)
- Face detection, matching, and watchlist alerting (InsightFace)
- Person re-identification across cameras (OSNet ReID)
- Cross-camera identity continuity (tracklet aggregation + cosine similarity matching)
- OSINT entity graph: visualises watchlisted persons and their camera sightings
- Weapons detection event logging
- Vehicle classification (make/model/color)
- PDF report generation, Maltego export, CSV export
- Real-time WebSocket analytics stream per camera

---

## 2. Repository Structure

```
CyberShield/
├── integrated-video-analytics/       ← Main application root
│   ├── main.py                       ← FastAPI app, all HTTP/WS endpoints
│   ├── pipeline.py                   ← Per-camera ML processing pipeline
│   ├── runtime.py                    ← CameraRuntime: manages pipeline threads
│   ├── database.py                   ← SQLite analytics DB (events, metrics, faces, plates, vehicles)
│   ├── auth.py                       ← Admin token auth helpers
│   ├── analytics.db                  ← SQLite DB (gitignored)
│   ├── weights/best.pt               ← Local plate detector weights (gitignored)
│   ├── yolo11s.pt                    ← Primary detector (gitignored)
│   ├── uploads/                      ← Staged video files + snapshots
│   ├── watchlist/                    ← Enrolled face images (.jpg/.png)
│   ├── snapshots/                    ← Auto-captured face/plate/vehicle crops
│   │   ├── faces/
│   │   ├── plates/
│   │   └── vehicles/
│   ├── static_ui/                    ← Compiled React frontend (served by FastAPI)
│   │   ├── index.html
│   │   └── assets/
│   │       ├── index-GIURsKmK.js    ← Current production bundle
│   │       └── index-DegkAA9L.css
│   ├── frontend/                     ← React/TypeScript source
│   │   ├── vite.config.ts
│   │   ├── src/
│   │   │   ├── pages/
│   │   │   │   ├── Index.tsx         ← Root dashboard, state orchestration
│   │   │   │   ├── Analytics.tsx     ← Analytics dashboard page
│   │   │   │   └── NotFound.tsx
│   │   │   ├── views/
│   │   │   │   ├── LiveView.tsx      ← Multi-camera live feed
│   │   │   │   ├── WatchlistView.tsx ← Watchlist enrolment & management
│   │   │   │   ├── OSINTView.tsx     ← Entity graph, profile panel, tracklets
│   │   │   │   ├── WeaponsView.tsx   ← Weapon event log, threat level KPIs
│   │   │   │   ├── PersonsView.tsx   ← Person registry table
│   │   │   │   └── SettingsView.tsx  ← Runtime configuration
│   │   │   ├── components/
│   │   │   │   ├── layout/
│   │   │   │   │   ├── Sidebar.tsx   ← Nav: LIVE/ANALYTICS/WATCHLIST/OSINT/WEAPONS/PERSONS/SETTINGS
│   │   │   │   │   └── TopBar.tsx
│   │   │   │   ├── live/
│   │   │   │   │   ├── CameraGrid.tsx  ← Responsive 1/2/2×2/3×2/3×3 grid
│   │   │   │   │   └── CameraCell.tsx  ← Single feed cell (MJPEG img stream)
│   │   │   │   ├── modals/
│   │   │   │   │   ├── AddFeedModal.tsx      ← Upload/stage/mount cameras + demo sequence
│   │   │   │   │   ├── PlateDetailModal.tsx  ← Plate detail drill-down
│   │   │   │   │   ├── QuickEnrollModal.tsx  ← Face enrolment from detection
│   │   │   │   │   └── AlertHistoryPopover.tsx
│   │   │   │   ├── AlertOverlay.tsx
│   │   │   │   ├── MetricsRow.tsx
│   │   │   │   ├── VideoPlayer.tsx
│   │   │   │   ├── ThreatMap.tsx
│   │   │   │   ├── CrowdDensityGauge.tsx
│   │   │   │   ├── IntelligenceHub.tsx
│   │   │   │   ├── SessionSummaryDrawer.tsx
│   │   │   │   └── WatchlistPanel.tsx
│   │   │   ├── hooks/
│   │   │   │   └── useBackendStream.ts  ← WebSocket → CyberShieldState
│   │   │   ├── lib/
│   │   │   │   ├── api.ts             ← apiFetch(), apiUpload()
│   │   │   │   ├── config.ts          ← API_URL, WS_URL, API_KEY from env/origin
│   │   │   │   └── utils.ts           ← cn() tailwind helper
│   ├── osint_reid/                   ← OSINT & ReID subsystem
│   │   ├── api.py                    ← FastAPI router, all /api/osint/* and /ws/state
│   │   ├── service.py                ← OSINTService: orchestrates pipeline → DB → matcher
│   │   ├── db.py                     ← OSINTDB: SQLite WAL, tracklets/global_identities/incidents
│   │   ├── reid_worker.py            ← OSNet ReID + InsightFace embeddings (graceful degradation)
│   │   ├── cross_camera_matcher.py   ← CrossCameraMatcher: cosine similarity, fused scoring
│   │   ├── aggregation.py            ← Tracklet payload aggregation
│   │   ├── vehicle_classifier.py     ← ViT Stanford Cars classifier + HSV color voting
│   │   ├── camera_graph.py           ← Camera adjacency/topology graph
│   │   ├── config.py                 ← Env-driven configuration constants
│   │   └── migrations/
│   │       └── 0001_add_tracklets_global_sql.sql
│   ├── migrations/
│   │   └── run.py                    ← Migration runner
│   ├── seed_osint.py                 ← Seeds Marcus J. Webb demo watchlist entry
│   ├── config/
│   │   └── camera_graph.json         ← Camera adjacency topology
│   ├── tests/
│   └── requirements.txt
├── context.md                        ← This file
├── README.md
└── C-Shield-ref/                     ← Reference UI source (LovableUI origin)
```

---

## 3. Backend Architecture

### 3.1 FastAPI Application (`main.py`)

**App startup (lifespan):**
1. Loads `.env` file (KEY=VALUE parser)
2. Creates `UPLOAD_DIR`, `WATCHLIST_DIR`, `SNAPSHOT_DIR`
3. Calls `warm_shared_resources()` to pre-load ML models into shared pool
4. Mounts OSINT router: `app.include_router(osint_router)`
5. Mounts `/assets` static files from `static_ui/assets/`

**Static serving / SPA:**
- `GET /` — serves `static_ui/index.html` if present, else `templates/index.html`, else 503
- `GET /{full_path}` (catch-all) — blocks `/api`, `/docs`, `/openapi.json`; serves file if found; else serves SPA index fallback

**CORS origins allowed:** `http://127.0.0.1:5173`, `http://localhost:5173` (Vite dev), plus production origin

### 3.2 Complete API Surface

#### Camera / Video Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras` | List mounted cameras with status |
| POST | `/api/cameras/add` | Mount camera (requires `camera_id` + `source` params) |
| DELETE | `/api/cameras/{camera_id}` | Unmount and stop camera pipeline |
| POST | `/api/admin/cameras/remove-all` | Bulk remove all cameras (admin) |
| POST | `/api/video/upload` | Upload video file, returns staged path |
| POST | `/api/video/stage` | Stage uploaded file, returns resolved camera ID |
| GET | `/api/video/stream/{camera_id}` | MJPEG stream with annotations |
| GET/POST | `/api/video/profile` | Get/set stream quality profile (`low`/`balanced`/`high`) |

#### Analytics & Records
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/status` | Pipeline status per camera |
| GET | `/api/analytics/traffic` | Vehicle/person traffic over time |
| GET | `/api/analytics/ocr` | Plate read statistics |
| GET | `/api/analytics/summary` | Aggregate summary: counts, watchlist hits, gender/vehicle breakdowns, top plates |
| GET | `/api/metrics` | Raw time-series metrics |
| GET | `/api/records/plates` | Plate read history |
| GET | `/api/records/vehicles` | Vehicle detection records |
| GET | `/api/records/faces` | Face detection records (used by PersonsView) |
| GET | `/api/logs/history` | Event log history |
| GET | `/api/health` | System health check |
| GET | `/api/system/stats` | CPU, RAM, GPU utilization via psutil/pynvml |

#### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/settings/runtime` | Runtime config (confidence, intervals, etc.) |
| GET/POST | `/api/settings/face-threshold` | Face match threshold (in-memory RUNTIME_SETTINGS) |

#### Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/events/clear` | Clear event log |

#### Watchlist
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/watchlist/files` | List enrolled face image files |
| POST | `/api/watchlist/files` | Upload face image to watchlist |
| DELETE | `/api/watchlist/files` | Remove face image from watchlist |

#### Export / Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/export/maltego` | Maltego-format entity export |
| GET | `/api/reports/download` | Generate and download PDF report (fpdf2) |

#### WebSocket
| Endpoint | Description |
|----------|-------------|
| `WS /ws/analytics/{camera_id}` | Real-time analytics stream for active camera |

#### OSINT / ReID (mounted from `osint_reid/api.py`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| WS | `/ws/state` | Live incident broadcast (admin-gated) |
| GET | `/api/watchlist` | List all global identities with watchlist_flag=1 |
| POST | `/api/watchlist` | Enroll new watchlist person (image upload + meta JSON) |
| GET | `/api/watchlist/{global_id}` | Full identity profile + match history + incidents |
| DELETE | `/api/watchlist/{global_id}` | Remove identity + snapshot cleanup |
| GET | `/api/records/tracklets` | Recent tracklets list |
| GET | `/api/osint/graph` | Entity graph: person + camera nodes, tracklet edges |
| POST | `/api/tracklet/{tracklet_id}/enrich` | Trigger manual Gemini enrichment (admin) |
| GET | `/api/incident/{incident_id}` | Incident details |
| GET | `/api/metrics/worker_queue` | OSINT worker queue metrics |
| GET | `/api/stream/snapshot/{global_id}/{ts}.jpg` | Subject snapshot image |

---

## 4. ML Pipeline (`pipeline.py`)

### 4.1 Shared Resources (singleton, lazy-loaded)

```
SharedResources
├── primary_detector      YOLO11s (yolo11s.pt) or env-override
├── plate_detector        Custom YOLO (weights/best.pt or HuggingFace download)
├── heavy_validator       YOLOv8x (optional, env-gated)
├── rtdetr_validator      RT-DETR-L (optional, env-gated)
├── ocr_reader            EasyOCR (fallback)
├── ocr_paddle            PaddleOCR (preferred, use_textline_orientation=True)
├── face_analyzer         InsightFace FaceAnalysis buffalo_l (optional)
├── sahi_model            SAHI sliced detection wrapper (optional)
└── reid_model            OSNet x0_25 imagenet (via torchreid)
```

All optional dependencies use `HAS_*` flags and degrade gracefully if not installed.

### 4.2 Detection Pipeline (per frame, per camera)

```
Frame (CV2 BGR)
  │
  ▼
Primary YOLO Detection
  ├── Classes: person(0), car(2), motorcycle(3), bus(5), truck(7)
  ├── Confidence threshold: 0.20 (default)
  └── Image size: 1024px

  │
  ▼
supervision ByteTrack Tracker
  └── Assigns stable tracker IDs across frames

  │
  ├── PERSON PATH ──────────────────────────────────────────────
  │   ├── Face detection via InsightFace (if HAS_INSIGHTFACE)
  │   │   ├── Gender/age estimation
  │   │   ├── 512D face embedding extraction
  │   │   └── Watchlist cosine similarity matching (threshold: configurable, default 0.4)
  │   ├── Rider proxy: motorcycles without matched person box counted as proxy person
  │   ├── Zone counting (configurable polygon zones)
  │   ├── Crowd density: Low/Medium/High by person_count thresholds
  │   └── Face snapshot saved to snapshots/faces/
  │
  ├── VEHICLE PATH ─────────────────────────────────────────────
  │   ├── Vehicle crop saved to snapshots/vehicles/
  │   └── ANPR (triggered by PLATE_SCAN_INTERVAL_SECONDS = 2.0):
  │       ├── Plate detector YOLO (confidence threshold: 0.50)
  │       ├── Plate region crop (search window: 10%–95% of vehicle bbox height)
  │       ├── Preprocessing variants:
  │       │   gray, resized, clahe, sharpened, binary, contrast, sharpened-contrast
  │       ├── PaddleOCR (cls=True then cls=False retry)
  │       ├── EasyOCR fallback
  │       ├── PlateVote TypedDict: aggregates OCR candidates with confidence scores
  │       ├── normalize_plate_text(): enforces ^(?=.*[A-Z])(?=.*\d)[A-Z0-9]{5,10}$
  │       │   + Indian plate patterns (state code + format validation)
  │       │   + OCR confusion correction (O↔0, I↔1, S↔5, B↔8, etc.)
  │       └── Plate snapshot saved to snapshots/plates/
  │
  └── ADAPTIVE GOVERNOR ────────────────────────────────────────
      Monitors CPU/GPU pressure and adjusts:
      ├── plate_scan_interval_seconds
      ├── plate_refresh_interval_seconds
      ├── face_scan_interval_seconds
      └── gemini_enabled (disabled under pressure)
```

### 4.3 Key Pipeline Constants (env-overridable)

| Constant | Default | Purpose |
|----------|---------|---------|
| `DETECTION_CONFIDENCE` | 0.20 | YOLO detection threshold |
| `DETECTION_IMAGE_SIZE` | 1024 | YOLO input resolution |
| `PLATE_SCAN_INTERVAL_SECONDS` | 2.0 | How often to run ANPR |
| `PLATE_REFRESH_INTERVAL_SECONDS` | 8.0 | Plate cache refresh |
| `PLATE_CONFIDENCE` | 0.50 | Plate detector min confidence |
| `PLATE_DIRECT_ACCEPT_CONFIDENCE` | 0.50 | Accept plate without voting |
| `PLATE_MIN_AGGREGATE_SCORE` | 0.28 | Vote aggregation threshold |
| `PLATE_CONFIRMATION_HITS` | 1 | Hits needed to confirm plate |
| `FACE_MATCH_THRESHOLD` | 0.40 | Cosine threshold for watchlist match |
| `LOCAL_OCR_MIN_CONFIDENCE` | 0.20 | EasyOCR minimum accepted score |
| `PADDLE_PRIMARY_MIN_CONFIDENCE` | 0.60 | PaddleOCR minimum accepted score |

---

## 5. OSINT / ReID Subsystem (`osint_reid/`)

### 5.1 Architecture Overview

```
Pipeline frame events
        │
        ▼
  OSINTService.ingest_frame(camera_id, tracker_id, class_name, crops, face_crops, ...)
        │
        ├── TrackletBuffer (in-memory, per tracker_id per camera)
        │   Accumulates: body crops, face crops, bbox history
        │   Evicted after TRACKLET_IDLE_SECONDS = 2.5s inactivity
        │   Min frames to persist: MIN_TRACKLET_FRAMES = 5
        │   Max crops per tracklet: MAX_CROPS_PER_TRACKLET = 16
        │
        ▼
  ThreadPoolExecutor (WORKER_POOL_SIZE = 4 threads)
        │
        ├── ReIDWorker.compute_reid_embeddings(body_crops)
        │   └── OSNet x0_25 → 512D L2-normalised vector (avg across crops)
        │
        ├── ReIDWorker.compute_face_embeddings(face_crops)
        │   └── InsightFace buffalo_l → 512D face vector (avg, conf-filtered)
        │
        ├── aggregation.aggregate_tracklet_payload()
        │   └── Color histogram (HSV), bbox history JSON
        │
        └── OSINTDB.insert_tracklet(...)
                │
                ▼
        CrossCameraMatcher.match_tracklet(...)
                │
                ├── Loads all global_identities from DB
                ├── Fused score = 0.60 × face_cosine + 0.30 × reid_cosine
                │              + 0.05 × color_score + 0.05 × plausibility
                ├── Thresholds:
                │   FACE_LINK_TH = 0.45, REID_LINK_TH = 0.65, FUSED_LINK_TH = 0.70
                │   AMBIGUITY_LOWER = 0.50 (rejects ambiguous matches)
                ├── Match found → links tracklet to existing global_identity
                └── No match → creates new global_identity
                        │
                        ▼
                Watchlist check: if global_identity.watchlist_flag = 1
                        └── Creates identity_incident + broadcasts to /ws/state
```

### 5.2 Database Schema (`analytics.db` — SQLite WAL mode)

**Table: `tracklets`**
```sql
tracklet_id              TEXT PRIMARY KEY
camera_id                TEXT
start_ts                 TEXT (ISO 8601 UTC)
end_ts                   TEXT
frame_count              INTEGER
aggregated_reid          BLOB  (float32 array, pickled)
aggregated_face          BLOB  (float32 array, pickled)
color_histogram          BLOB  (pickled)
bbox_history             TEXT  (JSON list of [x1,y1,x2,y2,ts])
plate_assoc              TEXT  (linked plate text if vehicle tracklet)
resolved_global_id       TEXT  (FK → global_identities)
enrichment_started_at    TEXT
enrichment_completed_at  TEXT
last_updated             TEXT
```

**Table: `global_identities`**
```sql
global_id          TEXT PRIMARY KEY  (gid_{12 hex chars})
created_at         TEXT
last_seen_ts       TEXT
last_seen_camera   TEXT
face_embedding     BLOB  (float32)
reid_embedding     BLOB  (float32)
watchlist_flag     INTEGER (0/1)
watchlist_meta     TEXT  (JSON: full_name, dob, nationality, phone, email,
                           last_known_address, vehicle_reg, vehicle_desc,
                           threat_level, notes, snapshot_filename)
confidence         REAL
```

**Table: `identity_incidents`**
```sql
incident_id           TEXT PRIMARY KEY  (uuid4)
tracklet_id           TEXT
candidate_global_id   TEXT
reason                TEXT
score                 REAL
created_at            TEXT
resolved              INTEGER (0/1)
operator_action       TEXT
```

**Table: `vehicles`**
```sql
vehicle_id            TEXT PRIMARY KEY
tracklet_id           TEXT
first_seen_ts         TEXT
last_seen_ts          TEXT
camera_id             TEXT
make_model            TEXT
make_model_confidence REAL
color                 TEXT
color_confidence      REAL
```

**Analytics DB tables** (managed by `database.py`, separate connection):
- `events` — event_type, detail, camera_id, timestamp
- `metrics` — vehicle_count, people_count, zone_count, stream_fps, etc.
- `face_records` — tracker_id, camera_id, identity, gender, age, watchlist_hit, first_seen, last_seen
- `plate_reads` — plate_text, camera_id, confidence, timestamp
- `vehicle_records` — vehicle class, camera_id, timestamp

### 5.3 OSINT Configuration (env-overridable, `osint_reid/config.py`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `MIN_TRACKLET_FRAMES` | 5 | Min frames before tracklet is persisted |
| `FACE_CONF_THRESHOLD` | 0.60 | Min InsightFace detection confidence |
| `FACE_LINK_TH` | 0.45 | Cosine threshold to link on face alone |
| `REID_LINK_TH` | 0.65 | Cosine threshold to link on ReID alone |
| `FUSED_LINK_TH` | 0.70 | Fused score threshold to link |
| `AMBIGUITY_LOWER` | 0.50 | Reject if second-best candidate within this margin |
| `REID_MODEL` | `osnet_x0_25` | OSNet variant |
| `WORKER_POOL_SIZE` | 4 | ThreadPoolExecutor workers |
| `TRACKLET_IDLE_SECONDS` | 2.5 | Seconds of inactivity before tracklet is flushed |
| `MAX_CROPS_PER_TRACKLET` | 16 | Max body crops stored per tracklet |
| `OSINT_DB_PATH` | `analytics.db` | SQLite DB path |

---

## 6. Frontend Architecture

### 6.1 Build & Dev

- **Framework:** React 18 + TypeScript + Vite
- **Styling:** Tailwind CSS + custom CSS variables (dark theme, `--primary`, `--status-alert`, etc.)
- **Component library:** shadcn/ui (Radix primitives)
- **Build output:** `static_ui/` (served directly by FastAPI)
- **Dev proxy:** Vite proxies `/api` → `http://localhost:8080`, `/ws` → `ws://localhost:8080`
- **Build command:** `cd frontend && npm run build`

### 6.2 State Management

Global state flows through `pages/Index.tsx`:

```
Index.tsx
  ├── cameras: string[]            ← Camera ID list from /api/cameras
  ├── activeCamera: string         ← Currently selected camera
  ├── activeView: ViewType         ← live | analytics | watchlist | osint | weapons | persons | settings
  ├── state: CyberShieldState      ← Live data from WebSocket
  ├── alertHistory: any[]          ← Watchlist alert events
  └── useBackendStream(activeCamera) → WebSocket /ws/analytics/{id}
        └── Merges incoming JSON into CyberShieldState via setState(p => ({...p, ...wsData}))
```

`CyberShieldState` fields (streamed per-frame from backend):
```typescript
vehicle_count, people_count, stream_fps, analytics_fps,
inference_latency_ms, crowd_density, is_processing,
vehicle_types, vehicle_current_types, gender_stats,
recent_plates, pending_plates, recent_faces, recent_vehicles,
event_logs, system_health, zone_count,
plate_detector_ready, device, stream_profile,
detection_confidence, plate_confidence, face_match_threshold,
faces_detected, plates_detected, people_total_count
```

### 6.3 Views

| View | Route key | Data source |
|------|-----------|-------------|
| LiveView | `live` | MJPEG stream `/api/video/stream/{id}`, WS analytics |
| Analytics | `analytics` | `/api/analytics/*`, `/api/metrics`, `/api/records/*` |
| WatchlistView | `watchlist` | `/api/watchlist`, `/api/records/faces` |
| OSINTView | `osint` | `/api/osint/graph`, `/api/records/tracklets`, `/api/metrics/worker_queue`, `WS /ws/state` |
| WeaponsView | `weapons` | `/api/events?event_type=weapon` with regex fallback |
| PersonsView | `persons` | `/api/records/faces?limit=200` (polls every 8s) |
| SettingsView | `settings` | `/api/settings/runtime`, `/api/settings/face-threshold` |

### 6.4 Camera Grid Layout

`CameraGrid` computes layout based on `cameras.length + 1` (including ADD FEED placeholder):

| Total cells | Columns | Rows |
|-------------|---------|------|
| 1 | 1 | 1 |
| 2 | 2 | 1 |
| 3–4 | 2 | 2 |
| 5–6 | 3 | 2 |
| 7–9 | 3 | 3 |
| 10+ | 4 | ceil(n/4) |

`CameraCell` uses `style={{ minHeight: 0 }}` (not `aspectRatio`) so cells fill `1fr` grid rows exactly. Image uses `object-cover`.

### 6.5 OSINT View Architecture

```
OSINTView
  ├── loadData() → parallel fetch:
  │   ├── /api/osint/graph    → GraphData {nodes[], edges[]}
  │   ├── /api/records/tracklets → tracklets[]
  │   └── /api/metrics/worker_queue → queue stats
  │
  ├── WebSocket /ws/state → live incident push → incidents[]
  │
  ├── KPI Row: Watchlisted | Cameras | Tracklets | Incidents
  │
  ├── EntityGraph (SVG W=720 H=420)
  │   ├── layoutNodes(): persons in horizontal row (H/2), cameras in arc above
  │   ├── Person nodes: ellipse with threat color (HIGH=red, MEDIUM=amber, LOW=green)
  │   ├── Camera nodes: circles
  │   ├── Edges: dashed lines with arrowhead marker, timestamp + frame_count labels
  │   └── onClick → setSelectedNode (drives ProfilePanel)
  │
  ├── ProfilePanel (280px right column)
  │   ├── Subject snapshot image (/api/stream/snapshot/{gid}/{ts}.jpg)
  │   ├── Global ID, threat level badge
  │   ├── Meta fields: full_name, dob, nationality, phone, email,
  │   │               last_known_address, vehicle_reg, vehicle_desc, notes
  │   └── Camera sightings: tracklet_id, start→end time, frame count
  │
  └── Recent Tracklets table + Live Incidents feed
```

### 6.6 Demo Sequence (AddFeedModal)

Three-video parallel staging flow:
1. User uploads 3 video files in the Demo tab (pre-filled: camera_1/2/3, delays 0/5/10s)
2. All 3 files staged in parallel via `POST /api/video/stage`
3. On success: modal closes immediately, live view shown
4. Cameras mount in background with staggered `setTimeout(delay * 1000)`
5. Each mount: `POST /api/cameras/add?camera_id=camera_N&source=<staged_path>`
6. `window.dispatchEvent(new CustomEvent("cameras-updated"))` triggers camera list refresh

---

## 7. Optional ML Integrations

| Package | Feature | Fallback behaviour |
|---------|---------|-------------------|
| `insightface` | Face detection, embeddings, gender/age | Face features disabled; face_model=None |
| `paddleocr` | Primary OCR engine for ANPR | Falls back to EasyOCR only |
| `easyocr` | Secondary OCR engine | ANPR disabled if neither available |
| `torchreid` | OSNet ReID embeddings | ReID disabled; reid_model=None |
| `transformers` | Stanford Cars vehicle classifier | Vehicle classification disabled |
| `sahi` | Sliced inference for small objects | Standard YOLO inference only |
| `google.generativeai` | Gemini tracklet enrichment | Enrichment disabled |
| `pynvml` | GPU metrics | GPU stats omitted from system health |

---

## 8. Authentication

`auth.py` provides two helpers:
- `ensure_admin_request(request)` — checks `Authorization: Bearer <token>` or `X-API-Key` header or `?api_key=` query param against `ADMIN_API_TOKEN` env var
- `ensure_admin_websocket(ws)` — same check for WebSocket connections

If `ADMIN_API_TOKEN` is empty/unset, all admin checks pass (open mode). Most read endpoints are unauthenticated. Admin-gated endpoints: `/ws/state`, `/api/tracklet/*/enrich`, camera remove-all, events clear.

---

## 9. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ADMIN_API_TOKEN` | `""` | Admin auth token (empty = open) |
| `CYBERSHIELD_WS_INTERVAL` | `1.0` | WebSocket push interval (seconds) |
| `CYBERSHIELD_DETECTOR_MODEL` | `yolo11s.pt` | Primary YOLO model path |
| `ANPR_MODE` | `local` | `local` or `cloud` (cloud uses Gemini Vision) |
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `MIN_TRACKLET_FRAMES` | `5` | OSINT min frames threshold |
| `FACE_LINK_TH` | `0.45` | Face cosine link threshold |
| `REID_LINK_TH` | `0.65` | ReID cosine link threshold |
| `FUSED_LINK_TH` | `0.70` | Fused score link threshold |
| `WORKER_POOL_SIZE` | `4` | OSINT worker threads |
| `TRACKLET_IDLE_SECONDS` | `2.5` | Tracklet flush timeout |
| `ENABLE_SAHI` | `true` | Enable SAHI sliced inference |
| `ENABLE_RTDETR_VALIDATOR` | `true` | Enable RT-DETR validation pass |
| `CAMERA_GRAPH_PATH` | `config/camera_graph.json` | Camera topology file |

---

## 10. Startup & Runtime

```bash
# Start server
cd integrated-video-analytics
py -m uvicorn main:app --host 0.0.0.0 --port 8080

# Build frontend
cd integrated-video-analytics/frontend
npm run build
# Output: ../static_ui/assets/index-GIURsKmK.js + index-DegkAA9L.css

# Seed OSINT demo data (Marcus J. Webb)
py seed_osint.py
```

Server runs at `http://localhost:8080`. Frontend is served from `static_ui/`.

**Model loading sequence on first camera add:**
1. `warm_shared_resources()` pre-loads primary YOLO detector
2. First `POST /api/cameras/add` triggers `CameraRuntime` which spins up `VideoPipeline` thread
3. Pipeline loads plate detector, OCR engines, InsightFace, OSNet lazily on first use
4. OSINT service initialises on first OSINT API call via `get_osint_service()` singleton

---

## 11. Known Gaps & Future Work

| Area | Gap | Notes |
|------|-----|-------|
| Weapons detection | No weapon-class YOLO model | `WeaponsView` polls events but `yolo11s` has no weapon classes; events will be empty without a finetuned model |
| Live graph refresh | OSINT graph is static (manual refresh only) | Should poll `/api/osint/graph` every 15s or subscribe to `/ws/state` |
| Per-cell analytics | Only `activeCamera` gets live stats over WebSocket | Other grid cells show stale counts |
| Movement timeline | No chronological subject movement view | Camera sightings in ProfilePanel are listed but not visualised as timeline |
| Enrichment UI | Tracklet enrichment result never surfaced | `/api/tracklet/{id}/enrich` submits job but result stored silently |
| Plate history search | No historical plate lookup UI | Data is in DB; no search interface |
| Authentication | Most read endpoints unauthenticated | Fine for local deployment; needs hardening for network exposure |
| Snapshot in ProfilePanel | Shows blank if InsightFace not installed | No fallback silhouette |

---

## 12. Commit History (key milestones)

| Hash | Summary |
|------|---------|
| `af84bbd4` | OSINT graph endpoint, Weapons/Persons views, camera grid fix, demo sequence |
| `cc935ab4` | Enhanced ANPR cloud-primary mode, state validation, snapshot storage |
| `def801b9` | ANPR logic refinement, TypedDict for votes, scan interval optimisation |
| `7a523a2d` | UI refresh, ANPR optimisation, technical audit |
| `232178fd` | OSINT/ReID subsystem: cross-camera identity, vehicle classification, migrations, API, tests |
| `db3d3b42` | Vehicle recall defaults, model path cleanup |
| `5afa04af` | Root README documentation |
| `fa658dde` | Production hardening: operator UI, ANPR quality gates, repo cleanup |
