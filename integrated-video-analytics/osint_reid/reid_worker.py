from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from osint_reid.config import REID_MODEL

logger = logging.getLogger("osint_reid.reid_worker")


@dataclass
class InferenceDevice:
    torch_device: str
    batch_size: int


def _select_device() -> InferenceDevice:
    if torch.cuda.is_available():
        return InferenceDevice(torch_device="cuda:0", batch_size=16)
    logger.warning("CUDA not available, using CPU for ReID and face embedding.")
    return InferenceDevice(torch_device="cpu", batch_size=4)


def _normalize_image(frame: np.ndarray, size: tuple[int, int]) -> torch.Tensor:
    resized = cv2.resize(frame, size, interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    return tensor


class ReIDWorker:
    def __init__(self):
        self.device_info = _select_device()
        self.device = torch.device(self.device_info.torch_device)
        self.reid_model = self._load_reid_model()
        self.face_model = self._load_face_model()

    def _load_reid_model(self) -> Any:
        try:
            import torchreid  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "torchreid is required for OSNet ReID. Install with: pip install torchreid"
            ) from exc
        model = torchreid.models.build_model(name=REID_MODEL, num_classes=1000, pretrained=True)
        model.eval()
        model.to(self.device)
        logger.info("Loaded ReID model", extra={"stage": "reid_model", "device": self.device.type, "model": REID_MODEL})
        return model

    def _load_face_model(self) -> Any:
        try:
            from insightface.app import FaceAnalysis
        except ImportError as exc:
            raise RuntimeError(
                "insightface is required for face embeddings. Install with: pip install insightface onnxruntime"
            ) from exc

        model = FaceAnalysis(name="buffalo_l")
        ctx_id = 0 if self.device.type == "cuda" else -1
        model.prepare(ctx_id=ctx_id, det_size=(640, 640))
        logger.info("Loaded InsightFace buffalo_l", extra={"stage": "face_model", "ctx_id": ctx_id})
        return model

    def compute_reid_embeddings(self, tracklet_frames: list[np.ndarray]) -> np.ndarray:
        if not tracklet_frames:
            return np.empty((0, 0), dtype=np.float32)

        tensors = [_normalize_image(frame, (128, 256)) for frame in tracklet_frames]
        outputs: list[np.ndarray] = []
        with torch.inference_mode():
            for i in range(0, len(tensors), self.device_info.batch_size):
                batch = torch.stack(tensors[i : i + self.device_info.batch_size]).to(self.device)
                emb = self.reid_model(batch)
                emb = F.normalize(emb, p=2, dim=1)
                outputs.append(emb.detach().cpu().numpy().astype(np.float32))
        return np.concatenate(outputs, axis=0)

    def compute_face_embeddings(self, face_frames: list[np.ndarray]) -> np.ndarray:
        if not face_frames:
            return np.empty((0, 512), dtype=np.float32)

        embs: list[np.ndarray] = []
        for frame in face_frames:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = self.face_model.get(rgb)
            if not faces:
                continue
            best = max(faces, key=lambda x: float(getattr(x, "det_score", 0.0)))
            emb = np.asarray(best.embedding, dtype=np.float32)
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            embs.append(emb)
        if not embs:
            return np.empty((0, 512), dtype=np.float32)
        return np.vstack(embs).astype(np.float32)

    @staticmethod
    def serialize_embeddings(emb: np.ndarray) -> bytes:
        return np.asarray(emb, dtype=np.float32).tobytes()
