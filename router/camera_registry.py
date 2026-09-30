"""Camera metadata registry used to select an inference environment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional


@dataclass
class CameraConfig:
    camera_id: str
    source: str
    environment: Optional[str] = None
    enabled: bool = True
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CameraRegistry:
    """In-memory camera registry with optional YAML/JSON loading."""

    def __init__(self, cameras: Optional[Iterable[CameraConfig]] = None):
        self._cameras: dict[str, CameraConfig] = {}
        for camera in cameras or []:
            self.register(camera)

    def register(self, camera: CameraConfig) -> CameraConfig:
        if not camera.camera_id.strip():
            raise ValueError("camera_id cannot be empty")
        if not camera.source.strip():
            raise ValueError("camera source cannot be empty")
        self._cameras[camera.camera_id] = camera
        return camera

    def remove(self, camera_id: str) -> None:
        if camera_id not in self._cameras:
            raise KeyError(f"Unknown camera: {camera_id}")
        del self._cameras[camera_id]

    def get(self, camera_id: str) -> CameraConfig:
        try:
            return self._cameras[camera_id]
        except KeyError as exc:
            raise KeyError(f"Unknown camera: {camera_id}") from exc

    def list(self, *, enabled_only: bool = False) -> list[CameraConfig]:
        cameras = list(self._cameras.values())
        return [camera for camera in cameras if camera.enabled] if enabled_only else cameras

    @classmethod
    def from_file(cls, path: str | Path) -> "CameraRegistry":
        """Load a registry from YAML (or JSON-shaped YAML)."""
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("Loading camera files requires PyYAML") from exc

        with Path(path).open("r", encoding="utf-8") as file:
            document = yaml.safe_load(file) or {}
        cameras = document.get("cameras", document)
        if isinstance(cameras, list):
            records = cameras
        elif isinstance(cameras, dict):
            records = [dict(value, camera_id=key) for key, value in cameras.items()]
        else:
            raise ValueError("Camera configuration must contain a cameras mapping or list")
        return cls(CameraConfig(**record) for record in records)

    def to_dict(self) -> dict[str, Any]:
        return {camera.camera_id: camera.to_dict() for camera in self._cameras.values()}
