# CyberShield — Integrated Video Analytics

Full documentation, setup instructions, system architecture, and API reference are maintained in the [root README](../README.md).

## Latest session note

Recent implementation updates include React frontend integration under `frontend/`, backend static serving from `static_ui/`, API/auth hardening, OCR/ReID/runtime hardening, ANPR snapshot visibility, and frontend build/type compatibility fixes.

For a comprehensive verified implementation ledger (including backend, frontend, dependency, build, and test details), see [context.md](../context.md).

## Quick start (from repo root)

```bash
python run.py
```

Open **http://localhost:8080**.

## Manual start (from this directory)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Run tests

```bash
.venv\Scripts\activate
python -m pytest tests/ -v
```


## Core modules

- Vehicle counting and classification with `YOLO11s` object detection plus `ByteTrack` tracking
- Automatic number plate recognition with a dedicated fine-tuned `YOLOv8` plate detector (`weights/best.pt`), local `PaddleOCR` as the primary OCR engine, `EasyOCR` fallback for uncertain reads, and optional cloud fallback
- Facial recognition, gender analytics, and age estimation with `InsightFace` (`buffalo_l`)
- People counting and crowd density estimation
- Searchable SQLite-backed event, plate, face, vehicle, and metrics records
- FastAPI dashboard with live MJPEG streaming, historical trend charts, watchlist management, searchable records, and PDF report export with charts

## Runtime behavior

- The primary detector defaults to `yolo11s.pt` on both CPU and CUDA systems.
- You can override the detector via `CYBERSHIELD_DETECT_MODEL`.
- The first run downloads detector weights, InsightFace assets, and OCR assets automatically.
- Plate detection uses `https://huggingface.co/yasirfaizahmed/license-plate-object-detection/resolve/main/best.pt` by default and can be overridden with `CYBERSHIELD_PLATE_MODEL`.
- The ANPR pipeline runs local OCR first (`PaddleOCR` primary, `EasyOCR` fallback), then uses cloud OCR only when local OCR cannot produce a valid plate.
- If `PLATE_RECOGNIZER_API_TOKEN` is set, cloud OCR is used as a last-resort fallback and optional enrichment path, not as the primary recognition path.
- Pending and confirmed ANPR reads are surfaced in the React UI, and confirmed reads include vehicle and plate crop snapshots for review.
- Watchlist identities can be managed from the dashboard or by placing images inside `watchlist/`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python tests/assets/generate_assets.py
python -m migrations.run
python main.py
```

Open `http://localhost:8080`.

## Key configuration

- `PLATE_RECOGNIZER_API_TOKEN`: Enables cloud ANPR enrichment; leave unset to use local OCR only
- `GEMINI_API_KEY`: Enables Gemini 2.0 Flash enrichment when combined with `CYBERSHIELD_ENABLE_GEMINI_ENRICHMENT=true`
- `CYBERSHIELD_ENABLE_GEMINI_ENRICHMENT`: Toggle Gemini enrichment for high-value plate/vehicle/face records
- `CYBERSHIELD_GEMINI_MODEL`: Gemini model name (default: `gemini-2.0-flash`)
- `CYBERSHIELD_ENABLE_PADDLE_OCR`: Enable/disable PaddleOCR primary local OCR path
- `CYBERSHIELD_ENABLE_EASYOCR_FALLBACK`: Enable/disable EasyOCR fallback path
- `CYBERSHIELD_PADDLE_PRIMARY_MIN_CONFIDENCE`: Confidence threshold for accepting PaddleOCR results directly
- `CYBERSHIELD_ALLOWED_ORIGINS`: Comma-separated frontend origins allowed by CORS
- `CYBERSHIELD_DETECT_MODEL`: Override the primary YOLO detector path or model name
- `CYBERSHIELD_PLATE_MODEL`: Override the plate detector path or URL
- `CYBERSHIELD_ENABLE_ADVANCED_ON_GPU`: When true, advanced detectors default on for GPU deployments
- `CYBERSHIELD_ENABLE_HEAVY_VALIDATOR`: Enable secondary validation model for low-confidence detections (defaults on for GPU)
- `CYBERSHIELD_HEAVY_VALIDATOR_MODEL`: Validation model path/name (default: `yolov8x.pt`)
- `CYBERSHIELD_HEAVY_VALIDATOR_MIN_CONF`: Lower confidence bound for candidate revalidation
- `CYBERSHIELD_HEAVY_VALIDATOR_MAX_CONF`: Upper confidence bound for candidate revalidation
- `CYBERSHIELD_HEAVY_VALIDATOR_IOU`: IoU threshold used to keep validator-confirmed detections
- `CYBERSHIELD_HEAVY_VALIDATOR_INTERVAL`: Frame interval for running heavy validation
- `CYBERSHIELD_ENABLE_SAHI_INFERENCE`: Enable conditional SAHI sliced inference for small/distant object recovery (defaults on for GPU)
- `CYBERSHIELD_SAHI_SLICE_HEIGHT`: SAHI tile height
- `CYBERSHIELD_SAHI_SLICE_WIDTH`: SAHI tile width
- `CYBERSHIELD_SAHI_OVERLAP_HEIGHT`: SAHI vertical overlap ratio
- `CYBERSHIELD_SAHI_OVERLAP_WIDTH`: SAHI horizontal overlap ratio
- `CYBERSHIELD_SAHI_TRIGGER_MIN_WIDTH`: Minimum frame width required before SAHI triggers
- `CYBERSHIELD_SAHI_INTERVAL`: Frame interval for SAHI execution
- `CYBERSHIELD_ENABLE_RTDETR_CONFIRMATION`: Enable optional RT-DETR confirmation pass (defaults on for GPU)
- `CYBERSHIELD_RTDETR_MODEL`: RT-DETR model path/name (default: `rtdetr-l.pt`)
- `CYBERSHIELD_RTDETR_MIN_CONF`: RT-DETR minimum confidence
- `CYBERSHIELD_RTDETR_IOU`: IoU threshold used to confirm primary detections
- `CYBERSHIELD_RTDETR_INTERVAL`: Frame interval for RT-DETR confirmation
- `CYBERSHIELD_ENABLE_ADAPTIVE_GOVERNOR`: Dynamically adjusts heavy validation/SAHI/RT-DETR under runtime pressure
- `CYBERSHIELD_ADAPTIVE_TARGET_FPS`: Target per-camera FPS floor for adaptive balancing
- `CYBERSHIELD_ADAPTIVE_MAX_INFER_MS`: Inference latency budget used for governor pressure detection
- `CYBERSHIELD_ADAPTIVE_HYSTERESIS_FRAMES`: Number of consecutive frames before mode switch to avoid oscillation
- `CYBERSHIELD_ENABLE_OSINT_REID`: Enables post-ByteTrack OSINT tracklet collection and async enrichment
- `ADMIN_API_TOKEN`: Protects write routes plus live streams, snapshots, exports, and analytics websockets when configured
- `MIN_TRACKLET_FRAMES`: Minimum frames required before OSINT enrichment dispatch
- `WORKER_POOL_SIZE`: Thread pool size for async enrichment workers
- `ENABLE_SAHI`: Toggle SAHI in OSINT validator tests
- `ENABLE_RTDETR_VALIDATOR`: Toggle RT-DETR in OSINT validator tests
- `CYBERSHIELD_DETECT_IMGSZ`: Detector inference size
- `CYBERSHIELD_TRACK_ACTIVATION_THRESHOLD`: ByteTrack activation threshold
- `CYBERSHIELD_TRACK_MATCHING_THRESHOLD`: ByteTrack matching threshold
- `CYBERSHIELD_MAX_UPLOAD_SIZE`: Upload size limit such as `512MB`

## OSINT / Cross-Camera Continuity

The repository now includes OSINT identity continuity and vehicle enrichment modules under `osint_reid/`:

- ReID worker using OSNet (`torchreid`) and face embeddings via InsightFace (`buffalo_l`)
- Tracklet aggregation and persistence into `tracklets`
- Cross-camera matcher with multimodal score fusion and ambiguity incident generation
- Vehicle make/model classification via the Stanford Cars transformer pipeline plus HSV-based color classification
- FastAPI endpoints for watchlist, incidents, tracklets, enrich trigger, snapshots, and worker queue metrics

### Migration

```bash
python -m migrations.run
```

### Demo

```bash
python demos/enrich_demo.py tests/assets/video_sample.mp4
```

### API quick checks

```bash
curl http://localhost:8080/api/watchlist
curl http://localhost:8080/api/records/tracklets
curl http://localhost:8080/api/metrics/worker_queue
```

If `ADMIN_API_TOKEN` is configured, use `Authorization: Bearer <token>` or `X-API-Key: <token>` for protected writes, streams, snapshot fetches, exports, and websocket subscriptions.

### Protected API calls (PowerShell)

```powershell
$env:ADMIN_API_TOKEN="change-me"
curl -H "Authorization: Bearer change-me" -F "name=person_a" -F "file=@tests/assets/face1.jpg" http://localhost:8080/api/watchlist
curl -H "Authorization: Bearer change-me" -X POST http://localhost:8080/api/tracklet/camera_1:1:person/enrich
```

### SAHI + RT-DETR executable validation

```bash
python osint_reid/sahi_rtdetr_test.py
```

### Adaptive detector governor

- The pipeline runs a three-state governor: `normal`, `caution`, and `pressure`.
- In `normal`, all enabled advanced stages run at configured intervals for peak recall.
- In `caution`, advanced stages are retained but intervals are widened.
- In `pressure`, RT-DETR and SAHI are temporarily backed off while heavy validation runs less frequently.
- Runtime status includes effective stage toggles and intervals so operators can verify what is active.

## Maltego export

- Analytics view buttons: `Export Plates`, `Export Faces`, `Export Vehicles`, `Export Events`
- API route: `/api/export/maltego?camera_id=<id>&entity=faces|vehicles|plates|events&limit=1000`
- Output format: CSV, suitable for transform staging/import workflows.

## Notes

- Uploaded videos are stored in `uploads/`.
- Watchlist images are stored in `watchlist/`.
- SQLite data is stored in `analytics.db`.
- Metrics history is persisted and exposed to the dashboard and PDF reports.
- The included sample videos can be used for smoke testing.
