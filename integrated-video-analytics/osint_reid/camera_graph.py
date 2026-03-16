from __future__ import annotations

import json
from pathlib import Path

from osint_reid.config import CAMERA_GRAPH_PATH


class CameraGraph:
    def __init__(self, config_path: Path = CAMERA_GRAPH_PATH):
        self.config_path = config_path
        self.edges: dict[tuple[str, str], dict[str, float]] = {}
        self._load()

    def _load(self) -> None:
        if not self.config_path.exists():
            self.edges = {}
            return
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        edges = payload.get("edges", [])
        mapped: dict[tuple[str, str], dict[str, float]] = {}
        for edge in edges:
            key = (str(edge["from"]), str(edge["to"]))
            mapped[key] = {
                "min_seconds": float(edge.get("min_seconds", 0.0)),
                "max_seconds": float(edge.get("max_seconds", 0.0)),
                "grace_seconds": float(edge.get("grace_seconds", 0.0)),
            }
        self.edges = mapped

    def camera_plausibility(self, from_cam: str, to_cam: str, delta_seconds: float) -> float:
        edge = self.edges.get((from_cam, to_cam))
        if edge is None:
            return 0.0
        min_s = edge["min_seconds"]
        max_s = edge["max_seconds"]
        grace = edge["grace_seconds"]

        delta = float(delta_seconds)
        if min_s <= delta <= max_s:
            return 1.0

        lower = min_s - grace
        upper = max_s + grace
        if delta < lower or delta > upper:
            return 0.0

        if delta < min_s:
            denom = max(min_s - lower, 1e-6)
            return max(0.0, min(1.0, (delta - lower) / denom))

        denom = max(upper - max_s, 1e-6)
        return max(0.0, min(1.0, 1.0 - ((delta - max_s) / denom)))
