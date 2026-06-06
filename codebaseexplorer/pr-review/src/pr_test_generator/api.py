"""FastAPI HTTP API layer for the Bitbucket PR Test Generator.

Exposes REST endpoints for job submission, status polling, and file
download. Uses a factory pattern to accept an external JobManager
instance for testability.

Endpoints:
    POST /analyze        – Submit a PR link for analysis
    GET  /jobs/{job_id}  – Poll job status
    GET  /jobs/{job_id}/download – Download generated Markdown file
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from pr_test_generator.jobs import JobManager
from models import JobStatus

logger = logging.getLogger(__name__)


def create_app(job_manager: JobManager) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        job_manager: The JobManager instance that handles job lifecycle.

    Returns:
        A fully configured FastAPI app with all endpoints registered.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Start background workers on startup, cancel on shutdown."""
        worker_task = asyncio.create_task(job_manager.process_jobs())
        cleanup_task = asyncio.create_task(job_manager.cleanup_expired())
        logger.info("Background job processor and cleanup task started.")
        yield
        worker_task.cancel()
        cleanup_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("Background tasks stopped.")

    app = FastAPI(
        title="Bitbucket PR Test Generator",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.post("/analyze", status_code=202)
    async def analyze(request: Request) -> JSONResponse:
        """Submit a PR link for analysis.

        Validates the JSON body, checks for the pr_link field, enqueues
        the job, and returns 202 with the job_id and status "queued".

        Returns:
            202: Job successfully queued with job_id and status.
            400: Invalid JSON body or missing pr_link field.
        """
        # Parse JSON body
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "Malformed request: invalid JSON body"},
            )

        # Validate pr_link field
        if not isinstance(body, dict) or "pr_link" not in body:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing required field: 'pr_link'"},
            )

        pr_link = body["pr_link"]
        if not isinstance(pr_link, str) or not pr_link.strip():
            return JSONResponse(
                status_code=400,
                content={"error": "Missing required field: 'pr_link' (Bitbucket PR URL or Bugzilla bug URL)"},
            )

        # Create and enqueue the job
        job = await job_manager.create_job(pr_link.strip())

        return JSONResponse(
            status_code=202,
            content={"job_id": job.id, "status": "queued"},
        )

    @app.get("/jobs/{job_id}")
    async def get_job_status(job_id: str) -> JSONResponse:
        """Get the current status of a job.

        Returns:
            200: Job status with optional error details and file_name.
            404: Job not found.
        """
        job = await job_manager.get_job(job_id)

        if job is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"Job not found: {job_id}"},
            )

        response: dict[str, Any] = {
            "job_id": job.id,
            "status": job.status.value,
            "error": None,
            "file_name": None,
            "created_at": job.created_at.isoformat(),
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

        if job.status == JobStatus.FAILED and job.error:
            response["error"] = {
                "stage": job.error.stage,
                "message": job.error.message,
            }

        if job.status == JobStatus.COMPLETED and job.output_path:
            response["file_name"] = job.output_path.name

        return JSONResponse(status_code=200, content=response)

    @app.get("/jobs/{job_id}/download")
    async def download_job_output(job_id: str) -> Response:
        """Download the generated Markdown file for a completed job.

        Returns:
            200: File content as application/octet-stream.
            404: Job not found or not yet completed.
        """
        job = await job_manager.get_job(job_id)

        if job is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"Job not found: {job_id}"},
            )

        if job.status != JobStatus.COMPLETED or job.output_path is None:
            return JSONResponse(
                status_code=404,
                content={"error": "Job output not available: job is not completed"},
            )

        # Read and serve the file
        try:
            file_content = job.output_path.read_bytes()
        except FileNotFoundError:
            return JSONResponse(
                status_code=404,
                content={"error": "Output file not found on disk"},
            )

        return Response(
            content=file_content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{job.output_path.name}"'
            },
        )

    return app
