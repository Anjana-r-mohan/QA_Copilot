"""Integration tests for the HTTP API endpoints.

Tests the FastAPI application endpoints using httpx AsyncClient with
ASGITransport. Uses a mocked analyzer function to avoid real Bitbucket
API calls while testing the full HTTP request/response cycle.

Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from pr_test_generator.api import create_app
from pr_test_generator.jobs import JobManager
from models import JobStatus, JobError


# --- Fixtures ---


@pytest.fixture
def tmp_output_file(tmp_path: Path) -> Path:
    """Create a temporary output file simulating a completed analysis."""
    output_file = tmp_path / "test-repo-PR42-test-cases.md"
    output_file.write_text("# Test Cases: test-repo-PR42\n\n## Summary\nGenerated test cases.")
    return output_file


@pytest.fixture
def success_analyzer(tmp_output_file: Path):
    """Analyzer function that completes successfully, returning the output file."""

    async def analyzer(pr_link: str) -> Path:
        return tmp_output_file

    return analyzer


@pytest.fixture
def failing_analyzer():
    """Analyzer function that raises an exception with a stage attribute."""

    async def analyzer(pr_link: str) -> Path:
        exc = RuntimeError("PR not found on Bitbucket")
        exc.stage = "pr_fetch"  # type: ignore[attr-defined]
        raise exc

    return analyzer


@pytest.fixture
def app_and_manager(success_analyzer):
    """Create a FastAPI app and its JobManager for direct manipulation."""
    mgr = JobManager(analyzer_fn=success_analyzer)
    app = create_app(mgr)
    return app, mgr


@pytest.fixture
def failing_app_and_manager(failing_analyzer):
    """Create a FastAPI app with the failing analyzer and its JobManager."""
    mgr = JobManager(analyzer_fn=failing_analyzer)
    app = create_app(mgr)
    return app, mgr


@pytest.fixture
async def client(app_and_manager):
    """Async HTTP client connected to the test app."""
    app, _ = app_and_manager
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def failing_client(failing_app_and_manager):
    """Async HTTP client connected to the failing app."""
    app, _ = failing_app_and_manager
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _wait_for_job_processing(manager: JobManager, job_id: str, timeout: float = 2.0):
    """Process the next job from the queue and wait for it to complete."""
    # Process one item from the queue
    try:
        queued_job_id = manager._queue.get_nowait()
    except asyncio.QueueEmpty:
        return

    job = manager._jobs.get(queued_job_id)
    if job is None:
        return

    job.status = JobStatus.PROCESSING
    try:
        output_path = await asyncio.wait_for(
            manager._analyzer_fn(job.pr_link), timeout=timeout
        )
        job.status = JobStatus.COMPLETED
        job.output_path = output_path
        job.completed_at = datetime.now(timezone.utc)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)
        stage = getattr(exc, "stage", "analysis")
        job.error = JobError(stage=stage, message=str(exc))
    finally:
        manager._queue.task_done()


# --- POST /analyze tests ---


class TestPostAnalyze:
    """Tests for the POST /analyze endpoint."""

    async def test_valid_pr_link_returns_202_with_job_id(self, client: AsyncClient):
        """POST /analyze with a valid pr_link returns 202 with job_id and status queued."""
        response = await client.post(
            "/analyze",
            json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/1"},
        )

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert len(data["job_id"]) > 0

    async def test_missing_pr_link_field_returns_400(self, client: AsyncClient):
        """POST /analyze with missing pr_link field returns 400."""
        response = await client.post("/analyze", json={"other_field": "value"})

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    async def test_empty_pr_link_returns_400(self, client: AsyncClient):
        """POST /analyze with empty pr_link returns 400."""
        response = await client.post("/analyze", json={"pr_link": ""})

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    async def test_whitespace_only_pr_link_returns_400(self, client: AsyncClient):
        """POST /analyze with whitespace-only pr_link returns 400."""
        response = await client.post("/analyze", json={"pr_link": "   "})

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    async def test_invalid_json_body_returns_400(self, client: AsyncClient):
        """POST /analyze with invalid JSON body returns 400."""
        response = await client.post(
            "/analyze",
            content=b"not valid json{{{",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    async def test_empty_body_returns_400(self, client: AsyncClient):
        """POST /analyze with empty body returns 400."""
        response = await client.post(
            "/analyze",
            content=b"",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data


# --- GET /jobs/{job_id} tests ---


class TestGetJobStatus:
    """Tests for the GET /jobs/{job_id} endpoint."""

    async def test_valid_job_returns_queued_status(self, client: AsyncClient):
        """GET /jobs/{id} returns 200 with status 'queued' immediately after submission."""
        submit_response = await client.post(
            "/analyze",
            json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/1"},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(f"/jobs/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "queued"

    async def test_completed_job_has_file_name(self, app_and_manager):
        """GET /jobs/{id} returns file_name when job is completed."""
        app, mgr = app_and_manager
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Submit a job
            submit_response = await c.post(
                "/analyze",
                json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/42"},
            )
            job_id = submit_response.json()["job_id"]

            # Process the job directly
            await _wait_for_job_processing(mgr, job_id)

            # Check status
            response = await c.get(f"/jobs/{job_id}")
            data = response.json()

        assert data["status"] == "completed"
        assert data["file_name"] is not None
        assert data["file_name"].endswith(".md")

    async def test_nonexistent_job_returns_404(self, client: AsyncClient):
        """GET /jobs/{id} with a nonexistent ID returns 404."""
        response = await client.get("/jobs/nonexistent-uuid-12345")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    async def test_job_status_contains_required_fields(self, client: AsyncClient):
        """GET /jobs/{id} response includes job_id, status, created_at, error, file_name."""
        submit_response = await client.post(
            "/analyze",
            json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/1"},
        )
        job_id = submit_response.json()["job_id"]

        response = await client.get(f"/jobs/{job_id}")
        data = response.json()

        assert "job_id" in data
        assert "status" in data
        assert "created_at" in data
        assert "error" in data
        assert "file_name" in data


# --- GET /jobs/{job_id}/download tests ---


class TestDownloadJobOutput:
    """Tests for the GET /jobs/{job_id}/download endpoint."""

    async def test_download_after_completion_returns_file(self, app_and_manager):
        """GET /jobs/{id}/download returns the file content after job completes."""
        app, mgr = app_and_manager
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Submit a job
            submit_response = await c.post(
                "/analyze",
                json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/42"},
            )
            job_id = submit_response.json()["job_id"]

            # Process the job directly
            await _wait_for_job_processing(mgr, job_id)

            # Download the file
            response = await c.get(f"/jobs/{job_id}/download")

        assert response.status_code == 200
        assert "application/octet-stream" in response.headers["content-type"]
        assert b"# Test Cases" in response.content
        # Check content-disposition header (case-insensitive)
        headers_lower = {k.lower(): v for k, v in response.headers.items()}
        assert "content-disposition" in headers_lower

    async def test_download_before_completion_returns_404(self, client: AsyncClient):
        """GET /jobs/{id}/download returns 404 if job is not yet completed."""
        # Submit a job but don't process it
        submit_response = await client.post(
            "/analyze",
            json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/1"},
        )
        job_id = submit_response.json()["job_id"]

        # Try to download immediately (job is still queued)
        response = await client.get(f"/jobs/{job_id}/download")
        assert response.status_code == 404

    async def test_download_nonexistent_job_returns_404(self, client: AsyncClient):
        """GET /jobs/{id}/download with a nonexistent job returns 404."""
        response = await client.get("/jobs/nonexistent-uuid-12345/download")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data


# --- Job failure reporting tests ---


class TestJobFailureReporting:
    """Tests for job failure reporting with correct stage and message."""

    async def test_failed_job_reports_stage_and_message(self, failing_app_and_manager):
        """Failed job status includes error with stage and message."""
        app, mgr = failing_app_and_manager
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as c:
            # Submit a job that will fail
            submit_response = await c.post(
                "/analyze",
                json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/99"},
            )
            job_id = submit_response.json()["job_id"]

            # Process the job (it will fail)
            await _wait_for_job_processing(mgr, job_id)

            # Check status
            response = await c.get(f"/jobs/{job_id}")
            data = response.json()

        assert data["status"] == "failed"
        assert data["error"] is not None
        assert data["error"]["stage"] == "pr_fetch"
        assert "PR not found" in data["error"]["message"]

    async def test_failed_job_has_completed_at(self, failing_app_and_manager):
        """Failed job has completed_at timestamp set."""
        app, mgr = failing_app_and_manager
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as c:
            submit_response = await c.post(
                "/analyze",
                json={"pr_link": "https://bitbucket.org/workspace/repo/pull-requests/99"},
            )
            job_id = submit_response.json()["job_id"]

            # Process the job (it will fail)
            await _wait_for_job_processing(mgr, job_id)

            # Check status
            response = await c.get(f"/jobs/{job_id}")
            data = response.json()

        assert data["status"] == "failed"
        assert data["completed_at"] is not None
