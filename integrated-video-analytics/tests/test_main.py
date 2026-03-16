import main
from fastapi.testclient import TestClient


def test_parse_size_bytes_supports_human_units():
    assert main.parse_size_bytes("16MB", 1) == 16 * 1024 * 1024
    assert main.parse_size_bytes("2048", 1) == 2048
    assert main.parse_size_bytes("bad", 7) == 7


def test_sanitize_upload_name_drops_path_components():
    assert main.sanitize_upload_name("../unsafe name!!.mp4") == "unsafe_name.mp4"
    assert main.sanitize_upload_name(None) == "video.mp4"


def test_health_snapshot_contains_runtime_flags():
    snapshot = main.get_health_snapshot()

    assert "device" in snapshot
    assert "ocr_ready" in snapshot
    assert "active_camera_count" in snapshot
    assert "gpu_ready" in snapshot
    assert "detector_gpu_ready" in snapshot
    assert "face_gpu_ready" in snapshot
    assert "startup" in snapshot
    assert "warnings" in snapshot


def test_get_ocr_summary_passthrough(monkeypatch):
    expected = {
        "total_reads": 2,
        "average_confidence": 0.81,
        "sources": [{"ocr_source": "paddle", "reads": 2, "share_percent": 100.0, "average_confidence": 0.81}],
    }

    monkeypatch.setattr(main, "get_ocr_analytics", lambda camera_id=None: expected)

    assert main.get_ocr_summary("cam_a") == expected


def test_health_endpoint_contract(monkeypatch):
    expected = {
        "device": "cpu",
        "ocr_ready": True,
        "active_camera_count": 0,
        "gpu_ready": False,
        "detector_gpu_ready": False,
        "face_gpu_ready": False,
        "warnings": [],
        "startup": {"phase": "ready", "ready": True, "preload_enabled": False, "preload_complete": False, "error": None, "last_updated": 0},
    }

    monkeypatch.setattr(main, "PRELOAD_SHARED_MODELS", False)
    monkeypatch.setattr(main, "REQUIRE_OCR_READY", False)
    monkeypatch.setattr(main, "get_health_snapshot", lambda: expected)

    with TestClient(main.app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == expected


def test_health_snapshot_merges_runtime_warnings(monkeypatch):
    expected_base = {
        "device": "cpu",
        "ocr_ready": True,
        "gpu_ready": False,
        "detector_gpu_ready": False,
        "face_gpu_ready": False,
        "warnings": [
            {"code": "face_gpu_fallback", "severity": "info", "component": "face_analyzer", "message": "CUDA is available but InsightFace is running on CPU fallback."}
        ],
    }

    class RuntimeStub:
        camera_id = "cam_warn"
        running = True
        state = {
            "cloud_ocr_cooldown_seconds": 12.5,
            "ocr_fallback_ready": True,
            "runtime_warnings": [
                {
                    "code": "cloud_ocr_cooldown",
                    "severity": "warning",
                    "component": "cloud_ocr",
                    "message": "Cloud OCR fallback is temporarily cooling down after a recent failure.",
                    "cooldown_seconds": 12.5,
                }
            ],
        }

    monkeypatch.setattr(main, "get_system_health_snapshot", lambda: expected_base.copy())
    monkeypatch.setattr(main, "runtimes", {"cam_warn": RuntimeStub()})

    snapshot = main.get_health_snapshot()

    assert snapshot["active_camera_count"] == 1
    assert snapshot["cloud_ocr_cooldown_seconds"] == 12.5
    assert len(snapshot["warnings"]) == 2
    assert any(item["code"] == "cloud_ocr_cooldown" and item.get("camera_id") == "cam_warn" for item in snapshot["warnings"])


def test_ocr_analytics_endpoint_contract(monkeypatch):
    expected = {
        "total_reads": 3,
        "average_confidence": 0.77,
        "sources": [
            {"ocr_source": "paddle", "reads": 2, "share_percent": 66.67, "average_confidence": 0.82},
            {"ocr_source": "easyocr", "reads": 1, "share_percent": 33.33, "average_confidence": 0.68},
        ],
    }

    monkeypatch.setattr(main, "PRELOAD_SHARED_MODELS", False)
    monkeypatch.setattr(main, "REQUIRE_OCR_READY", False)
    monkeypatch.setattr(main, "get_ocr_analytics", lambda camera_id=None: expected)

    with TestClient(main.app) as client:
        response = client.get("/api/analytics/ocr", params={"camera_id": "cam_a"})

    assert response.status_code == 200
    assert response.json() == expected
