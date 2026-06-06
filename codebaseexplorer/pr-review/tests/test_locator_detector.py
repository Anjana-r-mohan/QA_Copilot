"""Unit tests for the LocatorDetector module."""

import pytest

from models import (
    DetectedLocator,
    FileChange,
    FileChangeType,
    LocatorStatus,
    LocatorType,
)
from pr_test_generator.locator_detector import LocatorDetector


@pytest.fixture
def detector() -> LocatorDetector:
    """Create a fresh LocatorDetector instance."""
    return LocatorDetector()


class TestDetectAndroidResourceIds:
    """Tests for Android R.id.<identifier> detection."""

    def test_detects_single_resource_id(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content="val btn = R.id.submit_button",
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].locator_type == LocatorType.ANDROID_RESOURCE_ID
        assert results[0].value == "submit_button"
        assert results[0].status == LocatorStatus.ADDED
        assert results[0].line_number == 1

    def test_detects_multiple_resource_ids(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content="R.id.foo\nR.id.bar\nR.id.baz",
        )
        results = detector.detect(fc)
        assert len(results) == 3
        values = {r.value for r in results}
        assert values == {"foo", "bar", "baz"}


class TestDetectComposeTestTags:
    """Tests for Jetpack Compose Modifier.testTag() detection."""

    def test_detects_test_tag(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Screen.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='Modifier.testTag("login_button")',
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].locator_type == LocatorType.COMPOSE_TEST_TAG
        assert results[0].value == "login_button"

    def test_detects_test_tag_with_special_chars(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Screen.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='Modifier.testTag("btn-submit_1")',
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].value == "btn-submit_1"


class TestDetectIOSAccessibilityIdentifiers:
    """Tests for iOS .accessibilityIdentifier() detection."""

    def test_detects_accessibility_identifier(self, detector: LocatorDetector):
        fc = FileChange(
            path="ios/LoginView.swift",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='.accessibilityIdentifier("email_field")',
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].locator_type == LocatorType.IOS_ACCESSIBILITY_ID
        assert results[0].value == "email_field"


class TestDetectContentDescription:
    """Tests for contentDescription = "..." detection."""

    def test_detects_content_description(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Comp.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='contentDescription = "Close dialog"',
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].locator_type == LocatorType.CONTENT_DESCRIPTION
        assert results[0].value == "Close dialog"

    def test_detects_content_description_with_extra_spaces(
        self, detector: LocatorDetector
    ):
        fc = FileChange(
            path="app/Comp.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='contentDescription   =   "Submit form"',
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].value == "Submit form"


class TestClassification:
    """Tests for locator classification (added/removed/modified)."""

    def test_added_locator(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.MODIFIED,
            base_content="val x = 1",
            head_content="val btn = R.id.new_button",
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].status == LocatorStatus.ADDED

    def test_removed_locator(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.MODIFIED,
            base_content="val btn = R.id.old_button",
            head_content="val x = 1",
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].status == LocatorStatus.REMOVED

    def test_modified_locator_line_change(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.MODIFIED,
            base_content="R.id.my_button\nother code",
            head_content="new line\nR.id.my_button\nother code",
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].status == LocatorStatus.MODIFIED
        assert results[0].line_number == 2  # Head line number

    def test_unchanged_locator_not_reported(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Activity.kt",
            change_type=FileChangeType.MODIFIED,
            base_content="R.id.my_button",
            head_content="R.id.my_button",
        )
        results = detector.detect(fc)
        assert len(results) == 0


class TestEdgeCases:
    """Tests for edge cases and graceful handling."""

    def test_none_contents_returns_empty(self, detector: LocatorDetector):
        fc = FileChange(
            path="binary.dat",
            change_type=FileChangeType.MODIFIED,
            base_content=None,
            head_content=None,
        )
        results = detector.detect(fc)
        assert results == []

    def test_empty_contents_returns_empty(self, detector: LocatorDetector):
        fc = FileChange(
            path="empty.kt",
            change_type=FileChangeType.MODIFIED,
            base_content="",
            head_content="",
        )
        results = detector.detect(fc)
        assert results == []

    def test_no_locators_returns_empty(self, detector: LocatorDetector):
        fc = FileChange(
            path="util.kt",
            change_type=FileChangeType.MODIFIED,
            base_content="val x = 1",
            head_content="val y = 2",
        )
        results = detector.detect(fc)
        assert results == []

    def test_removed_file_classifies_as_removed(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Deleted.kt",
            change_type=FileChangeType.REMOVED,
            base_content="R.id.old_element",
            head_content=None,
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].status == LocatorStatus.REMOVED

    def test_added_file_classifies_as_added(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/New.kt",
            change_type=FileChangeType.ADDED,
            base_content=None,
            head_content='Modifier.testTag("new_tag")',
        )
        results = detector.detect(fc)
        assert len(results) == 1
        assert results[0].status == LocatorStatus.ADDED

    def test_multiple_locator_types_in_same_file(self, detector: LocatorDetector):
        fc = FileChange(
            path="app/Mixed.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='R.id.btn\nModifier.testTag("tag")\ncontentDescription = "desc"',
        )
        results = detector.detect(fc)
        assert len(results) == 3
        types = {r.locator_type for r in results}
        assert types == {
            LocatorType.ANDROID_RESOURCE_ID,
            LocatorType.COMPOSE_TEST_TAG,
            LocatorType.CONTENT_DESCRIPTION,
        }

    def test_data_completeness(self, detector: LocatorDetector):
        """Every detected locator has non-empty fields and valid line number."""
        fc = FileChange(
            path="app/Screen.kt",
            change_type=FileChangeType.ADDED,
            base_content="",
            head_content='R.id.element\nModifier.testTag("tag")\n.accessibilityIdentifier("aid")\ncontentDescription = "cd"',
        )
        results = detector.detect(fc)
        assert len(results) == 4
        for r in results:
            assert r.file_path == "app/Screen.kt"
            assert r.line_number > 0
            assert r.value != ""
            assert r.locator_type is not None
            assert r.status is not None
