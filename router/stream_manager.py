"""Stream job lifecycle and dispatch to inference containers."""

from __future__ import annotations

import json
import threading
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .routing_engine import RouteDecision


@dataclass
class StreamJob:
    job_id: str
    camera_id: str
    source: str
    environment: str
    target_url: str
    status: str = "created"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class StreamManager:
    """Create, dispatch, and stop logical stream jobs.

    The manager sends the source URL and metadata to the target container. It
    does not copy video files between containers; containers read the source
    through the Docker network or a shared volume.
    """

    def __init__(self, *, request_timeout: float = 10.0):
        self.request_timeout = request_timeout
        self._jobs: dict[str, StreamJob] = {}
        self._lock = threading.Lock()

    def create_job(self, decision: RouteDecision, *, metadata: Optional[dict[str, Any]] = None) -> StreamJob:
        job = StreamJob(
            job_id=str(uuid4()),
            camera_id=decision.camera_id,
            source=decision.source,
            environment=decision.environment,
            target_url=decision.target_url,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        if metadata:
            setattr(job, "metadata", metadata)
        return job

    def dispatch(self, job: StreamJob, *, extra: Optional[dict[str, Any]] = None) -> StreamJob:
        payload = {
            "job_id": job.job_id,
            "camera_id": job.camera_id,
            "source": job.source,
            "environment": job.environment,
            **(extra or {}),
        }
        request = urllib.request.Request(
            job.target_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Inference service returned HTTP {response.status}")
            job.status = "running"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
        return job

    def stop(self, job_id: str) -> StreamJob:
        job = self.get(job_id)
        job.status = "stopped"
        return job

    def get(self, job_id: str) -> StreamJob:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Unknown stream job: {job_id}") from exc

    def list(self) -> list[StreamJob]:
        with self._lock:
            return list(self._jobs.values())
