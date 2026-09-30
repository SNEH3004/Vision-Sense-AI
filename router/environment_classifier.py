"""Environment selection for cameras that are not fully registered."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional


SUPPORTED_ENVIRONMENTS = {"mall", "traffic", "railway", "exam_hall"}


class EnvironmentClassifier:
    """Classify a source using metadata first and a simple fallback heuristic.

    A production deployment can pass an image classifier callable. The callable
    should receive a frame and return an environment name.
    """

    def __init__(self, model: Optional[Callable[[Any], str]] = None):
        self.model = model

    def classify(
        self,
        *,
        camera_id: Optional[str] = None,
        source: Optional[str] = None,
        frame: Any = None,
        metadata_environment: Optional[str] = None,
    ) -> str:
        if metadata_environment:
            return self._validate(metadata_environment)

        if self.model is not None and frame is not None:
            return self._validate(self.model(frame))

        text = f"{camera_id or ''} {source or ''}".lower()
        aliases = {
            "exam_hall": ("exam", "classroom", "school", "college"),
            "railway": ("railway", "rail", "station", "train", "metro"),
            "traffic": ("traffic", "road", "highway", "junction", "toll"),
            "mall": ("mall", "shopping", "store", "retail"),
        }
        for environment, keywords in aliases.items():
            if any(keyword in text for keyword in keywords):
                return environment
        raise ValueError("Environment is unknown; register the camera or provide an environment")

    @staticmethod
    def _validate(environment: str) -> str:
        normalized = environment.strip().lower().replace(" ", "_")
        if normalized not in SUPPORTED_ENVIRONMENTS:
            raise ValueError(f"Unsupported environment: {environment}")
        return normalized
