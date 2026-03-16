# CyberShield — Integrated Video Analytics

Full documentation, setup instructions, system architecture, and API reference are maintained in the [root README](../README.md).

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
- Automatic number plate recognition with a dedicated `YOLOv8` plate detector, local `PaddleOCR` as the primary OCR engine, `EasyOCR` fallback for uncertain reads, and optional cloud fallback
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
- Watchlist identities can be managed from the dashboard or by placing images inside `watchlist/`.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Open `http://localhost:8080`.

## Key configuration

- `PLATE_RECOGNIZER_API_TOKEN`: Enables cloud ANPR enrichment; leave unset to use local OCR only
- `CYBERSHIELD_ENABLE_PADDLE_OCR`: Enable/disable PaddleOCR primary local OCR path
- `CYBERSHIELD_ENABLE_EASYOCR_FALLBACK`: Enable/disable EasyOCR fallback path
- `CYBERSHIELD_PADDLE_PRIMARY_MIN_CONFIDENCE`: Confidence threshold for accepting PaddleOCR results directly
- `CYBERSHIELD_ALLOWED_ORIGINS`: Comma-separated frontend origins allowed by CORS
- `CYBERSHIELD_DETECT_MODEL`: Override the primary YOLO detector path or model name
- `CYBERSHIELD_PLATE_MODEL`: Override the plate detector path or URL
- `CYBERSHIELD_DETECT_IMGSZ`: Detector inference size
- `CYBERSHIELD_TRACK_ACTIVATION_THRESHOLD`: ByteTrack activation threshold
- `CYBERSHIELD_TRACK_MATCHING_THRESHOLD`: ByteTrack matching threshold
- `CYBERSHIELD_MAX_UPLOAD_SIZE`: Upload size limit such as `512MB`

## Notes

- Uploaded videos are stored in `uploads/`.
- Watchlist images are stored in `watchlist/`.
- SQLite data is stored in `analytics.db`.
- Metrics history is persisted and exposed to the dashboard and PDF reports.
- The included sample videos can be used for smoke testing.
