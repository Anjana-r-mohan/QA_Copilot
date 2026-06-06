"""Job Manager module.

Provides async job management with in-memory storage and background
processing. Jobs flow through the lifecycle: queued → processing →
completed/failed, with periodic cleanup of expired entries.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable, Optional
from uuid import uuid4

from models import Job, JobError, JobStatus

logger = logging.getLogger(__name__)

# How long to retain completed/failed jobs before cleanup removes them.
_JOB_EXPIRY = timedelta(hours=24)

# How often the cleanup task runs (every hour).
_CLEANUP_INTERVAL_SECONDS = 3600


class JobManager:
    """In-memory async job manager with background processing.

    Jobs are stored in a dict for O(1) lookup and enqueued via an
    asyncio.Queue for ordered processing by a background worker.

    Args:
        analyzer_fn: An async callable that accepts a pr_link string and
            returns the output path (pathlib.Path). This is the function
            that performs the actual PR analysis work.
    """

    def __init__(
        self,
        analyzer_fn: Callable[[str], Awaitable],
    ) -> None:
        self._analyzer_fn = analyzer_fn
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def create_job(self, pr_link: str) -> Job:
        """Create a new job, store it, and enqueue it for processing.

        Args:
            pr_link: The Bitbucket PR URL to analyze.

        Returns:
            The newly created Job with status QUEUED.
        """
        job = Job(
            id=str(uuid4()),
            pr_link=pr_link,
            status=JobStatus.QUEUED,
            created_at=datetime.now(timezone.utc),
        )
        self._jobs[job.id] = job
        await self._queue.put(job.id)

        logger.info(
            "[%s] Job created | job_id=%s pr_link=%s",
            datetime.now(timezone.utc).isoformat(),
            job.id,
            pr_link,
        )
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by its ID.

        Args:
            job_id: The UUID string of the job.

        Returns:
            The Job if found, otherwise None.
        """
        return self._jobs.get(job_id)

    async def process_jobs(self) -> None:
        """Background worker loop that dequeues and processes jobs.

        This coroutine runs indefinitely, waiting for job IDs on the
        queue and processing each through the analyzer function. It
        updates job status through the lifecycle and captures errors
        with appropriate stage information.
        """
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)

            if job is None:
                logger.warning(
                    "[%s] Job not found in store, skipping | job_id=%s",
                    datetime.now(timezone.utc).isoformat(),
                    job_id,
                )
                self._queue.task_done()
                continue

            # Transition to processing
            job.status = JobStatus.PROCESSING
            logger.info(
                "[%s] Job processing started | job_id=%s",
                datetime.now(timezone.utc).isoformat(),
                job.id,
            )

            try:
                output_path = await self._analyzer_fn(job.pr_link)
                job.status = JobStatus.COMPLETED
                job.output_path = output_path
                job.completed_at = datetime.now(timezone.utc)
                logger.info(
                    "[%s] Job completed | job_id=%s output=%s",
                    datetime.now(timezone.utc).isoformat(),
                    job.id,
                    output_path,
                )
            except Exception as exc:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)

                # Determine failure stage from exception attributes or message
                stage = _extract_stage(exc)
                job.error = JobError(stage=stage, message=str(exc))
                logger.error(
                    "[%s] Job failed | job_id=%s stage=%s error=%s",
                    datetime.now(timezone.utc).isoformat(),
                    job.id,
                    stage,
                    str(exc),
                )
            finally:
                self._queue.task_done()

    async def cleanup_expired(self) -> None:
        """Periodic task that removes jobs older than 24 hours.

        Runs every hour and removes jobs whose created_at timestamp
        is older than the configured expiry duration.
        """
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
            now = datetime.now(timezone.utc)
            expired_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if _is_expired(job, now)
            ]

            for job_id in expired_ids:
                del self._jobs[job_id]

            if expired_ids:
                logger.info(
                    "[%s] Cleanup removed %d expired job(s)",
                    datetime.now(timezone.utc).isoformat(),
                    len(expired_ids),
                )


def _is_expired(job: Job, now: datetime) -> bool:
    """Check if a job has exceeded the 24-hour retention period."""
    # Ensure created_at is timezone-aware for comparison
    created = job.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created) > _JOB_EXPIRY


def _extract_stage(exc: Exception) -> str:
    """Extract the processing stage from an exception.

    If the exception has a 'stage' attribute (set by pipeline components),
    use it. Otherwise infer from the exception type/message.
    """
    if hasattr(exc, "stage"):
        return exc.stage  # type: ignore[attr-defined]

    msg = str(exc).lower()
    if "parse" in msg or "pr link" in msg or "not found" in msg:
        return "pr_fetch"
    if "file" in msg or "content" in msg or "diff" in msg:
        return "file_retrieval"
    if "locator" in msg or "pattern" in msg:
        return "analysis"
    if "generat" in msg or "output" in msg or "write" in msg or "markdown" in msg:
        return "generation"
    return "analysis"
