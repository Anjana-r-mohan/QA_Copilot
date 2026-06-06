"""Test Generator module.

Produces structured test cases from detected UI locators and code patterns.
Each locator or pattern generates one or more TestCase objects with unique IDs,
descriptive titles, preconditions, numbered steps, and expected results.

Test cases are grouped contiguously by source file path in the output.

Also handles rendering test cases to Markdown format and writing the output
file to the configured output directory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from models import (
    DetectedLocator,
    DetectedPattern,
    LocatorStatus,
    LocatorType,
    PatternType,
    TestCase,
)

logger = logging.getLogger(__name__)


class TestGenerator:
    """Generates structured test cases from detected locators and patterns.

    For each detected locator or pattern, produces one or more TestCase objects
    with unique sequential IDs (TC-1, TC-2, ...), descriptive titles (≤120 chars),
    preconditions, numbered steps, and expected results.

    Test cases are grouped contiguously by source file path.
    """

    def __init__(self) -> None:
        """Initialize TestGenerator with a sequential counter."""
        self._counter: int = 0

    def _next_id(self) -> str:
        """Generate the next unique test case ID."""
        self._counter += 1
        return f"TC-{self._counter}"

    def generate(
        self,
        locators: list[DetectedLocator],
        patterns: list[DetectedPattern],
        pr_metadata: dict,
    ) -> list[TestCase]:
        """Generate test cases from locators and patterns.

        Produces test cases for each locator and pattern, then groups them
        contiguously by source_file path.

        Args:
            locators: List of detected UI locators from changed files.
            patterns: List of detected code patterns from changed files.
            pr_metadata: Dictionary with PR metadata (title, author, etc.).

        Returns:
            A list of TestCase objects grouped by source_file.
        """
        self._counter = 0
        test_cases: list[TestCase] = []

        # Generate tests from locators
        for locator in locators:
            test_cases.extend(self._generate_locator_tests(locator))

        # Generate tests from patterns based on type
        for pattern in patterns:
            if pattern.pattern_type == PatternType.NAVIGATION:
                test_cases.extend(self._generate_navigation_tests(pattern))
            elif pattern.pattern_type == PatternType.API_CALL:
                test_cases.extend(self._generate_api_tests(pattern))
            elif pattern.pattern_type == PatternType.STATE_MANAGEMENT:
                test_cases.extend(self._generate_state_tests(pattern))
            elif pattern.pattern_type == PatternType.USER_INPUT:
                test_cases.extend(self._generate_input_tests(pattern))

        # Group test cases contiguously by source file
        return self._group_by_source_file(test_cases)

    def _generate_locator_tests(self, locator: DetectedLocator) -> list[TestCase]:
        """Generate test cases for a detected UI locator.

        - Added locators: 3 tests (visibility, interaction, accessibility)
        - Modified locators: 1 verification test
        - Removed locators: 1 absence test

        Args:
            locator: A detected UI locator with its status.

        Returns:
            A list of TestCase objects for the locator.
        """
        locator_label = self._locator_type_label(locator.locator_type)
        file_path = locator.file_path
        value = locator.value
        trigger = f"{locator_label}: {value}"

        if locator.status == LocatorStatus.ADDED:
            return self._generate_added_locator_tests(
                locator_label, value, file_path, trigger
            )
        elif locator.status == LocatorStatus.MODIFIED:
            return self._generate_modified_locator_tests(
                locator_label, value, file_path, trigger
            )
        elif locator.status == LocatorStatus.REMOVED:
            return self._generate_removed_locator_tests(
                locator_label, value, file_path, trigger
            )
        return []

    def _generate_added_locator_tests(
        self, locator_label: str, value: str, file_path: str, trigger: str
    ) -> list[TestCase]:
        """Generate 3 tests for an added locator: visibility, interaction, accessibility."""
        tests: list[TestCase] = []

        # 1. Visibility test
        title = self._truncate_title(
            f"Verify {locator_label} '{value}' is visible on screen load"
        )
        tests.append(
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    f"Screen containing {locator_label} '{value}' is accessible",
                ],
                steps=[
                    "1. Launch the application",
                    f"2. Navigate to the screen containing {locator_label} '{value}'",
                    f"3. Verify the element identified by '{value}' is displayed",
                ],
                expected_results=[
                    f"The element '{value}' is visible on the screen",
                    "The element renders without visual defects",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        )

        # 2. Interaction test
        title = self._truncate_title(
            f"Verify user interaction with {locator_label} '{value}'"
        )
        tests.append(
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    f"Element '{value}' is visible on the screen",
                ],
                steps=[
                    f"1. Locate the element identified by '{value}'",
                    "2. Perform a tap/click action on the element",
                    "3. Observe the application response",
                ],
                expected_results=[
                    "The element responds to user interaction",
                    "The expected action or state change occurs",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        )

        # 3. Accessibility test
        title = self._truncate_title(
            f"Verify accessibility label for {locator_label} '{value}'"
        )
        tests.append(
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    "Accessibility services are enabled on the device",
                ],
                steps=[
                    f"1. Navigate to the screen containing {locator_label} '{value}'",
                    "2. Enable accessibility inspection mode",
                    f"3. Inspect the element identified by '{value}'",
                    "4. Verify accessibility label is present and descriptive",
                ],
                expected_results=[
                    f"The element '{value}' has an accessibility label",
                    "The accessibility label is descriptive and meaningful",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        )

        return tests

    def _generate_modified_locator_tests(
        self, locator_label: str, value: str, file_path: str, trigger: str
    ) -> list[TestCase]:
        """Generate 1 verification test for a modified locator."""
        title = self._truncate_title(
            f"Verify {locator_label} '{value}' functions correctly after modification"
        )
        return [
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    f"The {locator_label} '{value}' was previously functional",
                    "The locator has been modified in the current changes",
                ],
                steps=[
                    f"1. Navigate to the screen containing {locator_label} '{value}'",
                    f"2. Verify the element identified by '{value}' is displayed",
                    "3. Perform the primary interaction with the element",
                    "4. Verify the element still responds correctly",
                ],
                expected_results=[
                    f"The element '{value}' is visible after modification",
                    "The element functions correctly with the updated locator",
                    "No regression in element behavior",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        ]

    def _generate_removed_locator_tests(
        self, locator_label: str, value: str, file_path: str, trigger: str
    ) -> list[TestCase]:
        """Generate 1 absence test for a removed locator."""
        title = self._truncate_title(
            f"Verify {locator_label} '{value}' is no longer present in UI"
        )
        return [
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    f"The {locator_label} '{value}' was previously present",
                    "The locator has been removed in the current changes",
                ],
                steps=[
                    "1. Navigate to the screen where the element was previously located",
                    f"2. Attempt to locate the element identified by '{value}'",
                    "3. Verify the element is not found in the view hierarchy",
                ],
                expected_results=[
                    f"The element '{value}' is no longer present on the screen",
                    "No remnants of the removed element are visible",
                    "The screen layout adjusts appropriately without the element",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        ]

    def _generate_navigation_tests(self, pattern: DetectedPattern) -> list[TestCase]:
        """Generate forward and back navigation tests for a navigation pattern.

        Args:
            pattern: A detected navigation pattern.

        Returns:
            A list of TestCase objects (at least 1 forward + 1 back navigation).
        """
        tests: list[TestCase] = []
        description = pattern.description
        file_path = pattern.file_path
        trigger = description

        if pattern.status == LocatorStatus.REMOVED:
            # For removed navigation, verify it no longer works
            title = self._truncate_title(
                f"Verify removed navigation no longer triggers: {description}"
            )
            tests.append(
                TestCase(
                    id=self._next_id(),
                    title=title,
                    preconditions=[
                        "Application is installed and launched",
                        "The navigation path was previously available",
                    ],
                    steps=[
                        "1. Navigate to the source screen",
                        "2. Attempt to trigger the removed navigation action",
                        "3. Verify navigation does not occur",
                    ],
                    expected_results=[
                        "The navigation action is no longer available",
                        "The user remains on the current screen",
                    ],
                    source_file=file_path,
                    trigger=trigger,
                )
            )
            return tests

        # Forward navigation test
        title = self._truncate_title(
            f"Verify forward navigation: {description}"
        )
        tests.append(
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    "User is on the source screen",
                ],
                steps=[
                    "1. Identify the navigation trigger on the source screen",
                    "2. Perform the action that triggers navigation",
                    "3. Wait for the destination screen to load",
                    "4. Verify the correct destination screen is displayed",
                ],
                expected_results=[
                    "Navigation to the target destination completes successfully",
                    "The destination screen is displayed with correct content",
                    "No navigation errors or blank screens appear",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        )

        # Back navigation test
        title = self._truncate_title(
            f"Verify back navigation returns to origin: {description}"
        )
        tests.append(
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    "User has navigated to the destination screen",
                ],
                steps=[
                    "1. Verify the user is on the destination screen",
                    "2. Press the back button or perform back gesture",
                    "3. Wait for the transition to complete",
                    "4. Verify the origin screen is displayed",
                ],
                expected_results=[
                    "Back navigation returns to the origin screen",
                    "The origin screen state is preserved",
                    "No navigation stack corruption occurs",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        )

        return tests

    def _generate_api_tests(self, pattern: DetectedPattern) -> list[TestCase]:
        """Generate API call validation tests for an API pattern.

        Args:
            pattern: A detected API call pattern.

        Returns:
            A list of TestCase objects for API validation.
        """
        description = pattern.description
        file_path = pattern.file_path
        trigger = description

        if pattern.status == LocatorStatus.REMOVED:
            title = self._truncate_title(
                f"Verify removed API call is no longer invoked: {description}"
            )
            return [
                TestCase(
                    id=self._next_id(),
                    title=title,
                    preconditions=[
                        "Application is installed and launched",
                        "Network monitoring is enabled",
                        "The API endpoint was previously called",
                    ],
                    steps=[
                        "1. Navigate to the screen that previously triggered the API call",
                        "2. Perform the actions that previously triggered the API call",
                        "3. Monitor network traffic for the removed endpoint",
                    ],
                    expected_results=[
                        "The removed API call is not triggered",
                        "No network request is made to the removed endpoint",
                    ],
                    source_file=file_path,
                    trigger=trigger,
                )
            ]

        title = self._truncate_title(
            f"Verify API call executes correctly: {description}"
        )
        return [
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    "Network connectivity is available",
                    "Valid authentication credentials are configured",
                ],
                steps=[
                    "1. Navigate to the screen that triggers the API call",
                    "2. Perform the action that initiates the API request",
                    "3. Wait for the API response",
                    "4. Verify the response is handled correctly in the UI",
                ],
                expected_results=[
                    "The API request is sent with correct parameters",
                    "The response is received and processed successfully",
                    "The UI updates to reflect the API response data",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        ]

    def _generate_state_tests(self, pattern: DetectedPattern) -> list[TestCase]:
        """Generate state management tests for a state pattern.

        Args:
            pattern: A detected state management pattern.

        Returns:
            A list of TestCase objects for state verification.
        """
        description = pattern.description
        file_path = pattern.file_path
        trigger = description

        if pattern.status == LocatorStatus.REMOVED:
            title = self._truncate_title(
                f"Verify removed state management has no side effects: {description}"
            )
            return [
                TestCase(
                    id=self._next_id(),
                    title=title,
                    preconditions=[
                        "Application is installed and launched",
                        "The state variable was previously used in the screen",
                    ],
                    steps=[
                        "1. Navigate to the affected screen",
                        "2. Perform actions that previously triggered state changes",
                        "3. Verify no unexpected behavior occurs",
                    ],
                    expected_results=[
                        "The screen functions correctly without the removed state",
                        "No crashes or undefined behavior occur",
                    ],
                    source_file=file_path,
                    trigger=trigger,
                )
            ]

        title = self._truncate_title(
            f"Verify state updates correctly: {description}"
        )
        return [
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    "The screen with state management is accessible",
                ],
                steps=[
                    "1. Navigate to the screen with the state variable",
                    "2. Observe the initial state value in the UI",
                    "3. Perform an action that triggers a state change",
                    "4. Verify the UI updates to reflect the new state",
                ],
                expected_results=[
                    "The state change is reflected in the UI",
                    "The UI updates reactively without manual refresh",
                    "The state value is consistent across the screen",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        ]

    def _generate_input_tests(self, pattern: DetectedPattern) -> list[TestCase]:
        """Generate user input handling tests for an input pattern.

        Args:
            pattern: A detected user input pattern.

        Returns:
            A list of TestCase objects for input handling verification.
        """
        description = pattern.description
        file_path = pattern.file_path
        trigger = description

        if pattern.status == LocatorStatus.REMOVED:
            title = self._truncate_title(
                f"Verify removed input handler no longer responds: {description}"
            )
            return [
                TestCase(
                    id=self._next_id(),
                    title=title,
                    preconditions=[
                        "Application is installed and launched",
                        "The input handler was previously active",
                    ],
                    steps=[
                        "1. Navigate to the screen with the previously interactive element",
                        "2. Attempt the user input that was previously handled",
                        "3. Verify no action is triggered",
                    ],
                    expected_results=[
                        "The input no longer triggers the previously associated action",
                        "The application remains stable",
                    ],
                    source_file=file_path,
                    trigger=trigger,
                )
            ]

        title = self._truncate_title(
            f"Verify user input is handled correctly: {description}"
        )
        return [
            TestCase(
                id=self._next_id(),
                title=title,
                preconditions=[
                    "Application is installed and launched",
                    "The screen with the input handler is displayed",
                ],
                steps=[
                    "1. Locate the interactive element on the screen",
                    "2. Perform the user input action (tap, gesture, or text entry)",
                    "3. Wait for the application to process the input",
                    "4. Verify the expected response occurs",
                ],
                expected_results=[
                    "The input is recognized and processed correctly",
                    "The appropriate action or feedback is triggered",
                    "No unintended side effects occur",
                ],
                source_file=file_path,
                trigger=trigger,
            )
        ]

    def _group_by_source_file(self, test_cases: list[TestCase]) -> list[TestCase]:
        """Group test cases contiguously by source_file path.

        Preserves relative order within each group, orders groups by first
        occurrence of each source_file in the input.

        Args:
            test_cases: Ungrouped list of test cases.

        Returns:
            Test cases reordered so all cases from the same file are contiguous.
        """
        # Maintain insertion order of files
        groups: dict[str, list[TestCase]] = {}
        for tc in test_cases:
            if tc.source_file not in groups:
                groups[tc.source_file] = []
            groups[tc.source_file].append(tc)

        # Flatten groups in order of first occurrence
        result: list[TestCase] = []
        for cases in groups.values():
            result.extend(cases)

        # Re-assign sequential IDs after grouping
        for idx, tc in enumerate(result, start=1):
            tc.id = f"TC-{idx}"

        return result

    @staticmethod
    def _truncate_title(title: str) -> str:
        """Truncate title to a maximum of 120 characters.

        Args:
            title: The full title string.

        Returns:
            The title truncated to 120 characters (with '...' suffix if truncated).
        """
        if len(title) <= 120:
            return title
        return title[:117] + "..."

    @staticmethod
    def _locator_type_label(locator_type: LocatorType) -> str:
        """Get a human-readable label for a locator type.

        Args:
            locator_type: The LocatorType enum value.

        Returns:
            A human-readable label string.
        """
        labels = {
            LocatorType.ANDROID_RESOURCE_ID: "Android Resource ID",
            LocatorType.COMPOSE_TEST_TAG: "Compose Test Tag",
            LocatorType.IOS_ACCESSIBILITY_ID: "iOS Accessibility ID",
            LocatorType.CONTENT_DESCRIPTION: "Content Description",
        }
        return labels.get(locator_type, locator_type.value)

    def render_markdown(
        self,
        test_cases: list[TestCase],
        pr_metadata: dict,
    ) -> str:
        """Render test cases to a complete Markdown document.

        Produces a Markdown file with metadata header, summary section,
        and test cases grouped by source file.

        Args:
            test_cases: List of generated TestCase objects.
            pr_metadata: Dictionary containing:
                - pr_link: Full URL to the pull request
                - source_branch: Name of the source branch
                - destination_branch: Name of the destination branch
                - changed_file_count: Number of changed files
                - repo_slug: Repository slug
                - pr_id: Pull request numeric ID
                - start_tc_id: Optional starting TC ID number (default 1)

        Returns:
            A string containing the full Markdown document.
        """
        repo_slug = pr_metadata.get("repo_slug", "unknown")
        pr_id = pr_metadata.get("pr_id", 0)
        pr_link = pr_metadata.get("pr_link", "")
        source_branch = pr_metadata.get("source_branch", "")
        destination_branch = pr_metadata.get("destination_branch", "")
        changed_file_count = pr_metadata.get("changed_file_count", 0)
        start_tc_id = pr_metadata.get("start_tc_id", 1)

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        lines: list[str] = []

        # Title
        lines.append(f"# Test Plan - Generated from PR {repo_slug}-PR{pr_id}")
        lines.append("")
        lines.append(f"**Generated:** {timestamp}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # No testable changes case
        if not test_cases:
            lines.append("No testable UI changes were found in this pull request.")
            lines.append("")
            lines.append("**End of Test Plan**")
            return "\n".join(lines)

        # Group by source file preserving order
        current_file: str | None = None
        file_index = 0
        tc_number = start_tc_id

        for tc in test_cases:
            if tc.source_file != current_file:
                current_file = tc.source_file
                file_index += 1
                # Extract a short name from the file path for the section header
                short_name = current_file.rsplit("/", 1)[-1] if "/" in current_file else current_file
                lines.append(f"### {file_index}. {short_name}")
                lines.append("")

            # TC ID without dash (e.g., TC8508)
            tc_id = f"TC{tc_number}"

            lines.append(f"#### {tc_id}: {tc.title}")
            lines.append("")

            # Priority
            lines.append("**Priority**: P1 ")
            lines.append("")

            # Preconditions
            lines.append("**Preconditions**:")
            for precondition in tc.preconditions:
                lines.append(precondition)
            lines.append("")

            # Steps
            lines.append("**Steps**:")
            for step in tc.steps:
                lines.append(step)
            lines.append("")

            # Expected Results
            lines.append("**Expected Results**:")
            for result in tc.expected_results:
                lines.append(result)
            lines.append("")

            # DB Validation
            lines.append("**DB Validation**:")
            lines.append("")
            lines.append("```sql")
            lines.append(f"-- Verify {tc.title}")
            lines.append("-- Add specific SQL query for validation")
            lines.append("SELECT * FROM relevant_table WHERE condition;")
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

            tc_number += 1

        lines.append("**End of Test Plan**")

        return "\n".join(lines)

    def write_output(
        self,
        markdown_content: str,
        repo_slug: str,
        pr_id: int,
        output_dir: str | Path | None = None,
    ) -> Path:
        """Write the rendered Markdown content to an output file.

        Creates the output directory if it doesn't exist and writes
        the markdown content to a file named {repo_slug}-PR{pr_id}-test-cases.md.

        Args:
            markdown_content: The rendered Markdown string to write.
            repo_slug: The repository slug for the filename.
            pr_id: The pull request numeric ID for the filename.
            output_dir: Directory to write the file to. Defaults to './output'.

        Returns:
            The Path to the written output file.

        Raises:
            OSError: If the output directory cannot be created or is not writable.
        """
        if output_dir is None:
            output_dir = Path("./output")
        else:
            output_dir = Path(output_dir)

        # Create directory (including intermediate directories)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(
                f"Cannot create output directory '{output_dir}': {e}"
            ) from e

        filename = f"{repo_slug}-PR{pr_id}-test-cases.md"
        output_path = output_dir / filename

        try:
            output_path.write_text(markdown_content, encoding="utf-8")
        except OSError as e:
            raise OSError(
                f"Cannot write output file '{output_path}': {e}"
            ) from e

        logger.info("Output written to %s", output_path)
        return output_path
