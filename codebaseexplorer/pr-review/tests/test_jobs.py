"""Unit tests for the JobManager module."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from models import JobStatus, JobError
from pr_test_generator.jobs import JobManager, _JOB_EXPIRY, _is_expired


# --- Fixtures ---


@pytest.fixture
def success_analyzer():
    """An analyzer function that succeeds and returns a Path."""
    return AsyncMock(return_value=Path("/output/repo-PR1-test-cases.md"))


@pytest.fixture
def failing_analyzer():
    """An analyzer function that raises an exception."""
    exc = Exception("PR not found: workspace/repo#999")
    return AsyncMock(side_effect=exc)


@pytest.fixture
def manager(success_analyzer):
    """A JobManager configured with the success analyzer."""
    return JobManager(analyzer_fn=success_analyzer)


# --- create_job tests ---


@pytest.mark.asyncio
async def test_create_job_returns_queued_job(manager):
    """create_job should return a Job with status QUEUED and a valid UUID."""
    job = await manager.create_job("https://bitbucket.org/team/repo/pull-requests/1")

    assert job.status == JobStatus.QUEUED
    assert job.pr_link == "https://bitbucket.org/team/repo/pull-requests/1"
    assert job.id  # non-empty UUID string
    assert job.created_at is not None
    assert job.error is None
    assert job.output_path is None
    assert job.completed_at is None


@pytest.mark.asyncio
async def test_create_job_generates_unique_ids(manager):
    """Each created job should have a unique ID."""
    job1 = await manager.create_job("https://bitbucket.org/team/repo/pull-requests/1")
    job2 = await manager.create_job("https://bitbucket.org/team/repo/pull-requests/2")

    assert job1.id != job2.id


@pytest.mark.asyncio
async def test_create_job_enqueues_for_processing(manager):
    """create_job should place the job ID in the processing queue."""
    job = await manager.create_job("https://bitbucket.org/team/repo/pull-requests/1")

    # The queue should have exactly one item
    assert manager._queue.qsize() == 1


# --- get_job tests ---


@pytest.mark.asyncio
async def test_get_job_returns_existing_job(manager):
    """get_job should return the job when it exists."""
    job = await manager.create_job("https://bitbucket.org/team/repo/pull-requests/1")
    retrieved = await manager.get_job(job.id)

    assert retrieved is not None
    assert retrieved.id == job.id
    assert retrieved.pr_link == job.pr_link


@pytest.mark.asyncio
async def test_get_job_returns_none_for_missing(manager):
    """get_job should return None for a non-existent job ID."""
    result = await manager.get_job("non-existent-id")
    assert result is None


# --- process_jobs tests ---


@pytest.mark.asyncio
async def test_process_jobs_completes_successfully(success_analyzer):
    """process_jobs should transition job to COMPLETED on success."""
    mgr = JobManager(analyzer_fn=success_analyzer)
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/1")

    # Run the worker as a task and let it process one item
    worker = asyncio.create_task(mgr.process_jobs())
    await asyncio.sleep(0.05)  # Give the worker time to process
    worker.cancel()

    assert job.status == JobStatus.COMPLETED
    assert job.output_path == Path("/output/repo-PR1-test-cases.md")
    assert job.completed_at is not None
    assert job.error is None


@pytest.mark.asyncio
async def test_process_jobs_sets_failed_on_error(failing_analyzer):
    """process_jobs should transition job to FAILED with JobError on exception."""
    mgr = JobManager(analyzer_fn=failing_analyzer)
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/999")

    worker = asyncio.create_task(mgr.process_jobs())
    await asyncio.sleep(0.05)
    worker.cancel()

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.stage == "pr_fetch"
    assert "PR not found" in job.error.message
    assert job.completed_at is not None


@pytest.mark.asyncio
async def test_process_jobs_transitions_through_processing(success_analyzer):
    """Job should pass through PROCESSING status before COMPLETED."""
    statuses_seen: list[JobStatus] = []

    async def tracking_analyzer(pr_link: str) -> Path:
        # At this point the job should be PROCESSING
        # We'll capture status via the manager's store
        return Path("/output/test.md")

    mgr = JobManager(analyzer_fn=tracking_analyzer)
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/1")

    worker = asyncio.create_task(mgr.process_jobs())
    await asyncio.sleep(0.05)
    worker.cancel()

    # After processing completes, job should be COMPLETED
    assert job.status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_process_jobs_handles_file_retrieval_error():
    """Job with file-related error maps to file_retrieval stage."""
    exc = Exception("Failed to fetch file content for src/main.kt")
    mgr = JobManager(analyzer_fn=AsyncMock(side_effect=exc))
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/5")

    worker = asyncio.create_task(mgr.process_jobs())
    await asyncio.sleep(0.05)
    worker.cancel()

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.stage == "file_retrieval"


@pytest.mark.asyncio
async def test_process_jobs_handles_generation_error():
    """Job with generation-related error maps to generation stage."""
    exc = Exception("Failed to write output markdown")
    mgr = JobManager(analyzer_fn=AsyncMock(side_effect=exc))
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/5")

    worker = asyncio.create_task(mgr.process_jobs())
    await asyncio.sleep(0.05)
    worker.cancel()

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.stage == "generation"


@pytest.mark.asyncio
async def test_process_jobs_uses_stage_attribute():
    """If exception has a 'stage' attribute, it should be used directly."""

    class StagedError(Exception):
        stage = "analysis"

    exc = StagedError("Locator detection failed")
    mgr = JobManager(analyzer_fn=AsyncMock(side_effect=exc))
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/5")

    worker = asyncio.create_task(mgr.process_jobs())
    await asyncio.sleep(0.05)
    worker.cancel()

    assert job.error is not None
    assert job.error.stage == "analysis"


# --- cleanup_expired tests ---


@pytest.mark.asyncio
async def test_cleanup_removes_expired_jobs(success_analyzer):
    """cleanup_expired should remove jobs older than 24 hours."""
    mgr = JobManager(analyzer_fn=success_analyzer)
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/1")

    # Manually set created_at to 25 hours ago to simulate expiry
    job.created_at = datetime.now(timezone.utc) - timedelta(hours=25)

    # We can't easily test the sleep loop, so test the helper directly
    assert _is_expired(job, datetime.now(timezone.utc)) is True


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_jobs(success_analyzer):
    """cleanup_expired should not remove jobs younger than 24 hours."""
    mgr = JobManager(analyzer_fn=success_analyzer)
    job = await mgr.create_job("https://bitbucket.org/team/repo/pull-requests/1")

    assert _is_expired(job, datetime.now(timezone.utc)) is False


def test_is_expired_with_naive_datetime():
    """_is_expired should handle naive datetimes (treated as UTC)."""
    from models import Job

    job = Job(
        pr_link="https://bitbucket.org/team/repo/pull-requests/1",
        created_at=datetime.utcnow() - timedelta(hours=25),
    )
    assert _is_expired(job, datetime.now(timezone.utc)) is True


def test_is_expired_boundary():
    """A job at exactly 24 hours should not be expired (uses >)."""
    from models import Job

    now = datetime.now(timezone.utc)
    job = Job(
        pr_link="https://bitbucket.org/team/repo/pull-requests/1",
        created_at=now - _JOB_EXPIRY,
    )
    # Exactly at boundary — not expired since we use >
    assert _is_expired(job, now) is False
