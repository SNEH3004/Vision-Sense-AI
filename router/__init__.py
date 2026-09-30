"""Camera and video routing layer for environment-specific inference services."""

from .camera_registry import CameraConfig, CameraRegistry
from .routing_engine import RouteDecision, RoutingEngine

__all__ = ["CameraConfig", "CameraRegistry", "RouteDecision", "RoutingEngine"]
