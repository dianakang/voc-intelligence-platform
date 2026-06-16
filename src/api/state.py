"""Shared in-memory job store — importable by both routes and graph nodes."""
from __future__ import annotations

import threading

# job_id -> job dict (status, progress_pct, current_step, agent_statuses, ...)
_jobs: dict[str, dict] = {}

# Per-thread job ID so graph nodes can find the right job without passing job_id
# through LangGraph state. Each pipeline run gets its own thread via BackgroundTasks.
_current_job_id: threading.local = threading.local()


def set_current_job_id(job_id: str) -> None:
    _current_job_id.value = job_id


def push_progress(*, agent_statuses: dict | None = None, current_step: str | None = None, progress_pct: int | None = None) -> None:
    """Called from inside graph nodes to push live updates to the job store."""
    job_id: str | None = getattr(_current_job_id, "value", None)
    if not job_id or job_id not in _jobs:
        return
    job = _jobs[job_id]
    if agent_statuses is not None:
        job["agent_statuses"] = agent_statuses
    if current_step is not None:
        job["current_step"] = current_step
    if progress_pct is not None:
        job["progress_pct"] = progress_pct
