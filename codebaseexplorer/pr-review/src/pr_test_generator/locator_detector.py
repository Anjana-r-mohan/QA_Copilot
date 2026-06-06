"""UI Locator Detector module.

Scans file content for UI locators using regex patterns, comparing base
and head commit content to classify locators as added, removed, or modified.

Supports detection of:
- Android resource IDs: R.id.<identifier>
- Jetpack Compose test tags: Modifier.testTag("<value>")
- iOS accessibility identifiers: .accessibilityIdentifier("<value>")
- Content descriptions: contentDescription = "<value>"
"""

from __future__ import annotations

import re
from typing import Optional

from models import (
    DetectedLocator,
    FileChange,
    FileChangeType,
    LocatorStatus,
    LocatorType,
)


class LocatorDetector:
    """Detects UI locators in changed files and classifies them by status.

    Compares locators found in base content vs head content to determine
    which locators were added, removed, or modified in the PR.
    """

    PATTERNS: dict[LocatorType, re.Pattern[str]] = {
        LocatorType.ANDROID_RESOURCE_ID: re.compile(r"R\.id\.(\w+)"),
        LocatorType.COMPOSE_TEST_TAG: re.compile(r'Modifier\.testTag\("([^"]+)"\)'),
        LocatorType.IOS_ACCESSIBILITY_ID: re.compile(
            r'\.accessibilityIdentifier\("([^"]+)"\)'
        ),
        LocatorType.CONTENT_DESCRIPTION: re.compile(
            r'contentDescription\s*=\s*"([^"]+)"'
        ),
    }

    def detect(self, file_change: FileChange) -> list[DetectedLocator]:
        """Detect UI locators in a file change and classify their status.

        Scans both base and head content for locator patterns, then
        classifies each locator as added, removed, or modified based on
        set-difference comparison.

        Args:
            file_change: A FileChange object containing base and head content.

        Returns:
            A list of DetectedLocator objects with their classification.
            Returns an empty list if the file is binary, empty, or contains
            no locators.
        """
        base_content = file_change.base_content
        head_content = file_change.head_content

        # Skip if both contents are None/empty (binary or unavailable)
        if not base_content and not head_content:
            return []

        # Scan base content for locators
        base_locators = self._scan_content(
            base_content or "", file_change.path
        )

        # Scan head content for locators
        head_locators = self._scan_content(
            head_content or "", file_change.path
        )

        # Classify locators by comparing base vs head
        return self._classify_locators(
            base_locators, head_locators, file_change.path
        )

    def _scan_content(
        self, content: str, file_path: str
    ) -> dict[tuple[LocatorType, str], list[tuple[int, str]]]:
        """Scan content for all locator pattern matches with line numbers.

        Args:
            content: The file content to scan.
            file_path: The path of the file being scanned (for context).

        Returns:
            A dictionary mapping (locator_type, value) keys to a list of
            (line_number, value) tuples for each occurrence found.
        """
        if not content:
            return {}

        results: dict[tuple[LocatorType, str], list[tuple[int, str]]] = {}
        lines = content.splitlines()

        for line_number, line in enumerate(lines, start=1):
            for locator_type, pattern in self.PATTERNS.items():
                for match in pattern.finditer(line):
                    value = match.group(1)
                    key = (locator_type, value)
                    if key not in results:
                        results[key] = []
                    results[key].append((line_number, value))

        return results

    def _classify_locators(
        self,
        base_locators: dict[tuple[LocatorType, str], list[tuple[int, str]]],
        head_locators: dict[tuple[LocatorType, str], list[tuple[int, str]]],
        file_path: str,
    ) -> list[DetectedLocator]:
        """Classify locators by comparing base and head sets.

        Classification rules:
        - Items only in head → "added"
        - Items only in base → "removed"
        - Items in both but with different line numbers → "modified"

        Args:
            base_locators: Locators found in the base commit content.
            head_locators: Locators found in the head commit content.
            file_path: The file path to associate with each locator.

        Returns:
            A list of DetectedLocator objects with classification status.
        """
        detected: list[DetectedLocator] = []

        base_keys = set(base_locators.keys())
        head_keys = set(head_locators.keys())

        # Locators only in head → added
        for key in head_keys - base_keys:
            locator_type, value = key
            # Use the first occurrence's line number in head
            line_number = head_locators[key][0][0]
            detected.append(
                DetectedLocator(
                    locator_type=locator_type,
                    value=value,
                    file_path=file_path,
                    line_number=line_number,
                    status=LocatorStatus.ADDED,
                )
            )

        # Locators only in base → removed
        for key in base_keys - head_keys:
            locator_type, value = key
            # Use the first occurrence's line number in base
            line_number = base_locators[key][0][0]
            detected.append(
                DetectedLocator(
                    locator_type=locator_type,
                    value=value,
                    file_path=file_path,
                    line_number=line_number,
                    status=LocatorStatus.REMOVED,
                )
            )

        # Locators in both → check if line numbers differ (modified)
        for key in base_keys & head_keys:
            locator_type, value = key
            base_lines = sorted(t[0] for t in base_locators[key])
            head_lines = sorted(t[0] for t in head_locators[key])

            if base_lines != head_lines:
                # Line numbers changed → modified
                line_number = head_locators[key][0][0]
                detected.append(
                    DetectedLocator(
                        locator_type=locator_type,
                        value=value,
                        file_path=file_path,
                        line_number=line_number,
                        status=LocatorStatus.MODIFIED,
                    )
                )

        return detected
