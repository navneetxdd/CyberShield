from pathlib import Path

import pipeline


def test_resolve_model_path_prefers_local_candidate(tmp_path):
    local_model = tmp_path / "best.pt"
    local_model.write_bytes(b"weights")

    resolved = pipeline.resolve_model_path(None, local_model, fallback="remote.pt")

    assert resolved == str(local_model)


def test_resolve_model_path_uses_fallback_when_missing(tmp_path):
    missing_model = tmp_path / "missing.pt"

    resolved = pipeline.resolve_model_path(None, missing_model, fallback="remote.pt")

    assert resolved == "remote.pt"


def test_normalize_plate_text_accepts_alphanumeric_plate():
    assert pipeline.normalize_plate_text("MH 12 AB 1234") == "MH12AB1234"


def test_normalize_plate_text_rejects_invalid_candidates():
    assert pipeline.normalize_plate_text("ABCDEFG") is None
    assert pipeline.normalize_plate_text("1234567") is None
    assert pipeline.normalize_plate_text("AB-1") is None


def test_read_env_float_uses_default_on_invalid_value(monkeypatch):
    monkeypatch.setenv("CYBERSHIELD_TEST_FLOAT", "O.30")

    assert pipeline.read_env_float("CYBERSHIELD_TEST_FLOAT", 0.3) == 0.3


def test_trim_timestamp_cache_expires_and_bounds_entries():
    cache = {
        "stale": 10.0,
        "fresh_a": 100.0,
        "fresh_b": 110.0,
        "fresh_c": 120.0,
    }

    pipeline.trim_timestamp_cache(cache, now=130.0, ttl_seconds=25.0, max_items=2)

    assert cache == {
        "fresh_b": 110.0,
        "fresh_c": 120.0,
    }


def test_plate_vote_confirmation_requires_valid_pathways(monkeypatch):
    monkeypatch.setattr(pipeline, "PLATE_CONFIRMATION_HITS", 2)
    monkeypatch.setattr(pipeline, "PLATE_DIRECT_ACCEPT_CONFIDENCE", 0.9)
    monkeypatch.setattr(pipeline, "PLATE_MIN_AGGREGATE_SCORE", 1.3)

    direct_vote = {"hits": 1.0, "best_confidence": 0.91, "score": 0.91}
    aggregate_vote = {"hits": 2.0, "best_confidence": 0.74, "score": 1.35}
    weak_vote = {"hits": 2.0, "best_confidence": 0.55, "score": 1.05}

    assert pipeline.VideoPipeline._is_plate_vote_confirmed(direct_vote) is True
    assert pipeline.VideoPipeline._is_plate_vote_confirmed(aggregate_vote) is True
    assert pipeline.VideoPipeline._is_plate_vote_confirmed(weak_vote) is False


def test_cloud_ocr_min_confidence_floor(monkeypatch):
    monkeypatch.setattr(pipeline, "PLATE_RECOGNIZER_API_TOKEN", "token")
    monkeypatch.setattr(pipeline, "CLOUD_OCR_MIN_CONFIDENCE", 0.8)

    class ResponseStub:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "plate": "MH12AB1234",
                        "score": 0.72,
                        "vehicle": {"props": {}},
                    }
                ]
            }

    monkeypatch.setattr(pipeline.requests, "post", lambda *args, **kwargs: ResponseStub())

    extractor = pipeline.VideoPipeline.__new__(pipeline.VideoPipeline)
    extractor._plate_api_disabled_until = 0.0

    class EncodedStub:
        @staticmethod
        def tobytes():
            return b"fake-bytes"

    monkeypatch.setattr(pipeline.cv2, "imencode", lambda *_args, **_kwargs: (True, EncodedStub()))

    class CropStub:
        size = 1

    result = pipeline.VideoPipeline._extract_plate_cloud(extractor, CropStub())

    assert result is None
