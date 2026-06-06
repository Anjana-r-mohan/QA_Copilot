"""Core data models and enums for the Bitbucket PR Test Generator.

Defines all dataclasses and enums used across the processing pipeline:
job management, PR metadata, file changes, locator detection, pattern
analysis, test case generation, and analysis results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4


# --- Job Management ---


class JobStatus(Enum):
    """Status of a PR analysis job through its lifecycle."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class JobError:
    """Error details when a job fails at a specific processing stage."""

    stage: str  # "pr_fetch" | "file_retrieval" | "analysis" | "generation"
    message: str


@dataclass
class Job:
    """Represents a PR analysis job from submission to completion."""

    id: str = field(default_factory=lambda: str(uuid4()))
    pr_link: str = ""
    status: JobStatus = JobStatus.QUEUED
    error: Optional[JobError] = None
    output_path: Optional[Path] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    pr_metadata: Optional[PRMetadata] = None


# --- PR Metadata ---


@dataclass
class PRMetadata:
    """Metadata extracted from a Bitbucket pull request."""

    title: str
    author: str
    source_branch: str
    destination_branch: str
    base_commit: str  # merge-base or destination head
    head_commit: str  # source branch head
    pr_link: str
    workspace: str
    repo_slug: str
    pr_id: int


# --- File Changes ---


class FileChangeType(Enum):
    """Type of change applied to a file in the PR."""

    ADDED = "added"
    MODIFIED = "modified"
    REMOVED = "removed"
    RENAMED = "renamed"


@dataclass
class FileChange:
    """A single file change in the PR with its content at both commits."""

    path: str
    change_type: FileChangeType
    old_path: Optional[str] = None  # For renamed files
    base_content: Optional[str] = None  # None for added files
    head_content: Optional[str] = None  # None for removed files


# --- Locator Detection ---


class LocatorType(Enum):
    """Types of UI locators detectable in mobile code."""

    ANDROID_RESOURCE_ID = "android_resource_id"
    COMPOSE_TEST_TAG = "compose_test_tag"
    IOS_ACCESSIBILITY_ID = "ios_accessibility_id"
    CONTENT_DESCRIPTION = "content_description"


class LocatorStatus(Enum):
    """Whether a locator was added, removed, or modified between commits."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class DetectedLocator:
    """A UI locator detected in a changed file."""

    locator_type: LocatorType
    value: str
    file_path: str
    line_number: int
    status: LocatorStatus


# --- Pattern Analysis ---


class PatternType(Enum):
    """Categories of code patterns relevant to mobile testing."""

    NAVIGATION = "navigation"
    API_CALL = "api_call"
    STATE_MANAGEMENT = "state_management"
    USER_INPUT = "user_input"


@dataclass
class DetectedPattern:
    """A code pattern detected in a changed file."""

    pattern_type: PatternType
    description: str
    file_path: str
    line_number: int
    status: LocatorStatus  # Reuses added/removed/modified classification


# --- Test Case Generation ---


@dataclass
class TestCase:
    """A structured test case generated from detected locators or patterns."""

    id: str  # TC-{sequential_number}
    title: str  # max 120 characters
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)  # numbered steps
    expected_results: list[str] = field(default_factory=list)
    source_file: str = ""
    trigger: str = ""  # locator value or pattern description


# --- Analysis Result ---


@dataclass
class AnalysisResult:
    """Aggregated result of analyzing all changed files in a PR."""

    files: list[FileChange] = field(default_factory=list)
    locators: list[DetectedLocator] = field(default_factory=list)
    patterns: list[DetectedPattern] = field(default_factory=list)
    file_counts: dict[FileChangeType, int] = field(default_factory=dict)
