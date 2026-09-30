"""Compose entrypoint for the deployed Mall and Exam Hall inference services."""

from __future__ import annotations

import os
from typing import Any

from .camera_registry import CameraConfig, CameraRegistry
from .routing_engine import RoutingEngine
from .stream_manager import StreamManager

registry = CameraRegistry()
routing_engine = RoutingEngine(
    registry,
    routes={
        "mall": os.getenv("ROUTE_MALL_URL", "http://inference:8001/infer"),
        "exam_hall": os.getenv("ROUTE_EXAM_URL", "http://exam_inference:8002/infer"),
    },
)
stream_manager = StreamManager()


def create_app():
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("The router API requires fastapi and uvicorn") from exc

    app = FastAPI(title="VisionSense AI Camera Router")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "camera-router",
            "active_environments": sorted(routing_engine.routes),
        }

    @app.get("/cameras")
    def cameras() -> list[dict[str, Any]]:
        return [camera.to_dict() for camera in registry.list()]

    @app.post("/cameras")
    def register_camera(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return registry.register(CameraConfig(**payload)).to_dict()
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/route")
    def route_video(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            decision = routing_engine.route(
                camera_id=payload.get("camera_id"),
                source=payload.get("source"),
                environment=payload.get("environment"),
            )
            job = stream_manager.create_job(decision, metadata=payload.get("metadata"))
            if payload.get("dispatch", True):
                job = stream_manager.dispatch(job, extra=payload.get("metadata"))
            return {"route": decision.to_dict(), "job": job.to_dict()}
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/streams")
    def streams() -> list[dict[str, Any]]:
        return [job.to_dict() for job in stream_manager.list()]

    return app


app = create_app()
