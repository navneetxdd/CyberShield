from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn.functional as F

logger = logging.getLogger("osint_reid.vehicle_classifier")


_IMAGENET_CAR_MAP = {
    "sports car": [817, 511, 656],
    "suv": [609, 751, 656],
    "pickup": [717],
    "van": [654],
    "bus": [779],
}


class VehicleClassifier:
    def __init__(self):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model()

    def _load_model(self) -> Any:
        try:
            import timm  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("timm is required for vehicle classification. Install with: pip install timm") from exc
        model = timm.create_model("efficientnet_b0", pretrained=True)
        model.eval()
        model.to(self.device)
        logger.info("Loaded EfficientNet-B0", extra={"stage": "vehicle_model", "device": self.device.type})
        return model

    def _preprocess(self, crop: np.ndarray) -> torch.Tensor:
        resized = cv2.resize(crop, (224, 224), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
        mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        return (tensor - mean) / std

    def classify_vehicle_crops(self, crops: list[np.ndarray]) -> tuple[str, float]:
        if not crops:
            return ("Unknown", 0.0)
        tensors = [self._preprocess(crop) for crop in crops if crop.size > 0]
        if not tensors:
            return ("Unknown", 0.0)
        with torch.inference_mode():
            batch = torch.stack(tensors).to(self.device)
            logits = self.model(batch)
            probs = F.softmax(logits, dim=1)
            avg = probs.mean(dim=0).detach().cpu().numpy()

        best_label = "Unknown"
        best_score = 0.0
        for label, indices in _IMAGENET_CAR_MAP.items():
            score = float(np.max(avg[indices]))
            if score > best_score:
                best_score = score
                best_label = label
        return best_label, round(best_score, 4)

    def classify_color(self, crops: list[np.ndarray]) -> tuple[str, float, np.ndarray]:
        if not crops:
            return ("unknown", 0.0, np.zeros((8 * 8 * 8,), dtype=np.float32))

        all_hist = []
        for crop in crops:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten().astype(np.float32)
            all_hist.append(hist)

        hist_avg = np.mean(np.stack(all_hist), axis=0)

        hue_hist = np.zeros((8,), dtype=np.float32)
        for crop in crops:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            h = cv2.calcHist([hsv], [0], None, [8], [0, 180]).flatten()
            h = h / max(float(np.sum(h)), 1.0)
            hue_hist += h.astype(np.float32)
        hue_hist /= max(float(len(crops)), 1.0)

        dominant_bin = int(np.argmax(hue_hist))
        dominance = float(np.max(hue_hist))

        if dominance < 0.18:
            color = "gray"
        elif dominant_bin in {0, 7}:
            color = "red"
        elif dominant_bin in {1}:
            color = "orange"
        elif dominant_bin in {2}:
            color = "yellow"
        elif dominant_bin in {3}:
            color = "green"
        elif dominant_bin in {4, 5}:
            color = "blue"
        else:
            color = "purple"

        return color, round(dominance, 4), hist_avg.astype(np.float32)
