"""HTTP API for camera registration and routing requests."""

from __future__ import annotations

from typing import Any

from .camera_registry import CameraConfig, CameraRegistry
from .routing_engine import RoutingEngine
from .stream_manager import StreamManager


registry = CameraRegistry()
router = RoutingEngine(registry)
stream_manager = StreamManager()


def create_app():
    """Create the FastAPI application lazily."""
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("The router API requires fastapi and uvicorn") from exc

    app = FastAPI(title="Vision AI Camera Router", version="1.0.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "camera-router"}

    @app.get("/cameras")
    def list_cameras() -> list[dict[str, Any]]:
        return [camera.to_dict() for camera in registry.list()]

    @app.post("/cameras")
    def register_camera(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            camera = registry.register(CameraConfig(**payload))
            return camera.to_dict()
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/route")
    def route_video(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            decision = router.route(
                camera_id=payload.get("camera_id"),
                source=payload.get("source"),
                environment=payload.get("environment"),
            )
            job = stream_manager.create_job(decision, metadata=payload.get("metadata"))
            if payload.get("dispatch", False):
                job = stream_manager.dispatch(job, extra=payload.get("metadata"))
            return {"route": decision.to_dict(), "job": job.to_dict()}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/streams/{job_id}/stop")
    def stop_stream(job_id: str) -> dict[str, Any]:
        try:
            return stream_manager.stop(job_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/streams")
    def list_streams() -> list[dict[str, Any]]:
        return [job.to_dict() for job in stream_manager.list()]

    return app


app = None
try:
    app = create_app()
except RuntimeError:
    # Importing the package should remain possible without web dependencies.
    pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("router.api:app", host="0.0.0.0", port=8000, reload=False)
