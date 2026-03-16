from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image

logger = logging.getLogger("osint_reid.vehicle_classifier")


_STANFORD_MODEL = "nateraw/vit-base-patch16-224-in21k-ft-scar"

_STANFORD_BRAND_MAP = {
    "acura": "Acura",
    "alfa": "Alfa Romeo",
    "aston": "Aston Martin",
    "audi": "Audi",
    "bentley": "Bentley",
    "bmw": "BMW",
    "bugatti": "Bugatti",
    "buick": "Buick",
    "cadillac": "Cadillac",
    "chevrolet": "Chevrolet",
    "chrysler": "Chrysler",
    "daewoo": "Daewoo",
    "dodge": "Dodge",
    "eagle": "Eagle",
    "ferrari": "Ferrari",
    "fiat": "FIAT",
    "fisker": "Fisker",
    "ford": "Ford",
    "geo": "GEO",
    "gmc": "GMC",
    "honda": "Honda",
    "hummer": "Hummer",
    "hyundai": "Hyundai",
    "infiniti": "Infiniti",
    "isuzu": "Isuzu",
    "jaguar": "Jaguar",
    "jeep": "Jeep",
    "kia": "Kia",
    "lamborghini": "Lamborghini",
    "land": "Land Rover",
    "lincoln": "Lincoln",
    "lotus": "Lotus",
    "maserati": "Maserati",
    "maybach": "Maybach",
    "mazda": "Mazda",
    "mclaren": "McLaren",
    "mercedes-benz": "Mercedes-Benz",
    "mercedes": "Mercedes-Benz",
    "mini": "MINI",
    "mitsubishi": "Mitsubishi",
    "nissan": "Nissan",
    "plymouth": "Plymouth",
    "pontiac": "Pontiac",
    "porsche": "Porsche",
    "ram": "RAM",
    "renault": "Renault",
    "rolls-royce": "Rolls-Royce",
    "saturn": "Saturn",
    "scion": "Scion",
    "smart": "Smart",
    "spyker": "Spyker",
    "subaru": "Subaru",
    "suzuki": "Suzuki",
    "tesla": "Tesla",
    "toyota": "Toyota",
    "volkswagen": "Volkswagen",
    "volvo": "Volvo",
}

_BODY_KEYWORDS = {
    "convertible": "convertible",
    "cabriolet": "convertible",
    "coupe": "coupe",
    "hatchback": "hatchback",
    "sedan": "sedan",
    "wagon": "wagon",
    "van": "van",
    "minivan": "van",
    "suv": "suv",
    "pickup": "pickup",
    "truck": "truck",
    "roadster": "sports car",
    "spyder": "sports car",
    "superleggera": "sports car",
    "supercab": "pickup",
    "crew cab": "pickup",
    "club cab": "pickup",
}


class VehicleClassifier:
    def __init__(self):
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model()

    def _load_model(self) -> Any:
        try:
            from transformers import pipeline  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "transformers is required for Stanford Cars classification. Install with: pip install transformers"
            ) from exc

        model = pipeline(
            task="image-classification",
            model=_STANFORD_MODEL,
            device=0 if self.device.type == "cuda" else -1,
        )
        logger.info("Loaded Stanford Cars ViT model", extra={"stage": "vehicle_model", "device": self.device.type})
        return model

    def _canonical_vehicle_label(self, raw_label: str) -> tuple[str, str]:
        normalized = " ".join(str(raw_label).replace("_", " ").split())
        tokens = normalized.split()
        if not tokens:
            return "Unknown", "unknown"

        if tokens and tokens[-1].isdigit() and len(tokens[-1]) == 4:
            tokens = tokens[:-1]
        if not tokens:
            return "Unknown", "unknown"

        lower = [token.lower() for token in tokens]
        brand_key = lower[0]
        if len(lower) >= 2 and f"{lower[0]} {lower[1]}" in {"land rover", "aston martin", "rolls royce"}:
            if lower[0] == "land":
                brand_key = "land"
                tokens = ["Land", "Rover", *tokens[2:]]
            elif lower[0] == "aston":
                brand_key = "aston"
                tokens = ["Aston", "Martin", *tokens[2:]]
            else:
                brand_key = "rolls-royce"
                tokens = ["Rolls-Royce", *tokens[2:]]
        elif len(lower) >= 2 and lower[0] == "mercedes" and lower[1] in {"benz", "benz,"}:
            brand_key = "mercedes-benz"
            tokens = ["Mercedes-Benz", *tokens[2:]]

        brand = _STANFORD_BRAND_MAP.get(brand_key, tokens[0].title())
        model_name = " ".join(tokens[1:]).strip()
        combined = brand if not model_name else f"{brand} {model_name}"

        label_lower = combined.lower()
        body = "unknown"
        for keyword, mapped in _BODY_KEYWORDS.items():
            if keyword in label_lower:
                body = mapped
                break

        return combined, body

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

        images: list[Image.Image] = []
        for crop in crops:
            if crop.size == 0:
                continue
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            images.append(Image.fromarray(rgb))

        if not images:
            return ("Unknown", 0.0)

        predictions = self.model(images, top_k=5)
        if not isinstance(predictions, list):
            return ("Unknown", 0.0)

        score_by_label: dict[str, float] = {}
        for image_predictions in predictions:
            if not isinstance(image_predictions, list):
                image_predictions = [image_predictions]
            for candidate in image_predictions:
                raw_label = str(candidate.get("label", ""))
                score = float(candidate.get("score", 0.0))
                canonical, body = self._canonical_vehicle_label(raw_label)
                pretty = canonical if body == "unknown" else f"{canonical} ({body})"
                score_by_label[pretty] = score_by_label.get(pretty, 0.0) + score

        if not score_by_label:
            return ("Unknown", 0.0)

        best_label, total_score = max(score_by_label.items(), key=lambda item: item[1])
        confidence = min(total_score / max(float(len(images)), 1.0), 1.0)
        return best_label, round(confidence, 4)

    def classify_color(self, crops: list[np.ndarray]) -> tuple[str, float, np.ndarray]:
        if not crops:
            return ("unknown", 0.0, np.zeros((8 * 8 * 8,), dtype=np.float32))

        all_hist: list[np.ndarray] = []
        color_votes: dict[str, int] = {
            "white": 0,
            "black": 0,
            "silver": 0,
            "gray": 0,
            "red": 0,
            "orange": 0,
            "yellow": 0,
            "green": 0,
            "blue": 0,
            "purple": 0,
            "brown": 0,
        }

        for crop in crops:
            if crop.size == 0:
                continue
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
            hist = cv2.normalize(hist, hist).flatten().astype(np.float32)
            all_hist.append(hist)

            mean_h, mean_s, mean_v = [float(x) for x in cv2.mean(hsv)[:3]]
            if mean_s < 28:
                if mean_v >= 185:
                    color_votes["white"] += 1
                elif mean_v <= 55:
                    color_votes["black"] += 1
                elif mean_v >= 130:
                    color_votes["silver"] += 1
                else:
                    color_votes["gray"] += 1
                continue

            hue = mean_h * 2.0
            if 8 <= hue < 25 and mean_v < 165 and mean_s > 60:
                color_votes["brown"] += 1
            elif hue < 10 or hue >= 170:
                color_votes["red"] += 1
            elif hue < 25:
                color_votes["orange"] += 1
            elif hue < 38:
                color_votes["yellow"] += 1
            elif hue < 85:
                color_votes["green"] += 1
            elif hue < 130:
                color_votes["blue"] += 1
            elif hue < 165:
                color_votes["purple"] += 1
            else:
                color_votes["red"] += 1

        if not all_hist:
            return ("unknown", 0.0, np.zeros((8 * 8 * 8,), dtype=np.float32))

        hist_avg = np.mean(np.stack(all_hist), axis=0)
        color, votes = max(color_votes.items(), key=lambda item: item[1])
        confidence = votes / max(float(len(all_hist)), 1.0)
        return color, round(confidence, 4), hist_avg.astype(np.float32)
