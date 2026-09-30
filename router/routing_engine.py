"""Resolve environments to Docker inference service endpoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from .camera_registry import CameraConfig, CameraRegistry
from .environment_classifier import EnvironmentClassifier


DEFAULT_ROUTES = {
    "mall": "http://mall_detection:8001/infer",
    "traffic": "http://traffic_detection:8002/infer",
    "railway": "http://railway_detection:8003/infer",
    "exam_hall": "http://exam_detection:8004/infer",
}


@dataclass
class RouteDecision:
    camera_id: str
    source: str
    environment: str
    target_url: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RoutingEngine:
    def __init__(
        self,
        registry: CameraRegistry,
        *,
        routes: Optional[dict[str, str]] = None,
        classifier: Optional[EnvironmentClassifier] = None,
    ):
        self.registry = registry
        self.routes = routes or DEFAULT_ROUTES.copy()
        self.classifier = classifier or EnvironmentClassifier()

    def route(
        self,
        *,
        camera_id: Optional[str] = None,
        source: Optional[str] = None,
        environment: Optional[str] = None,
        frame: Any = None,
    ) -> RouteDecision:
        registered: Optional[CameraConfig] = None
        if camera_id:
            try:
                registered = self.registry.get(camera_id)
            except KeyError:
                if source is None:
                    raise

        actual_source = source or (registered.source if registered else None)
        if not actual_source:
            raise ValueError("A source or registered camera_id is required")

        if environment:
            selected_environment = self.classifier._validate(environment)
            reason = "request metadata"
        elif registered and registered.environment:
            selected_environment = self.classifier._validate(registered.environment)
            reason = "camera registry"
        else:
            selected_environment = self.classifier.classify(
                camera_id=camera_id,
                source=actual_source,
                frame=frame,
            )
            reason = "environment classifier"

        target_url = self.routes.get(selected_environment)
        if not target_url:
            raise ValueError(f"No inference route configured for {selected_environment}")
        return RouteDecision(
            camera_id=camera_id or "unregistered-camera",
            source=actual_source,
            environment=selected_environment,
            target_url=target_url,
            reason=reason,
        )
