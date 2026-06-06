"""Pattern Analyzer module.

Detects code patterns (navigation, API calls, state management, user input)
in changed files by comparing base and head content. Only patterns that
differ between the two versions are reported.

Each detected pattern includes the pattern type, a human-readable description,
the source file path, the line number, and a status (added, removed, or modified).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

from models import DetectedPattern, FileChange, FileChangeType, LocatorStatus, PatternType


class _PatternMatch(NamedTuple):
    """A single pattern match found during content scanning."""

    pattern_type: PatternType
    description: str
    line_number: int
    # A key for deduplication/comparison (e.g., the matched text)
    match_key: str


@dataclass(frozen=True)
class _PatternDef:
    """Definition of a regex pattern to detect."""

    pattern_type: PatternType
    regex: re.Pattern[str]
    description_template: str  # Use {match} placeholder for the matched text


class PatternAnalyzer:
    """Detects code patterns in changed files by comparing base and head content.

    Scans for navigation actions, API calls, state management constructs,
    and user input handlers. Reports only patterns that differ between the
    base commit and head commit versions of a file.
    """

    # --- Navigation patterns ---
    NAVIGATION_PATTERNS: list[_PatternDef] = [
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'\bnavigate\s*\('),
            "Navigation call: {match}",
        ),
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'\bpushViewController\s*\('),
            "Push view controller: {match}",
        ),
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'\bNavHost\s*\('),
            "NavHost composable: {match}",
        ),
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'\bNavController\b'),
            "NavController usage: {match}",
        ),
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'\bpopBackStack\s*\('),
            "Pop back stack: {match}",
        ),
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'\bpresentViewController\s*\('),
            "Present view controller: {match}",
        ),
        _PatternDef(
            PatternType.NAVIGATION,
            re.compile(r'["\']\/[a-zA-Z][a-zA-Z0-9_/\-]*["\']'),
            "Route string literal: {match}",
        ),
    ]

    # --- API call patterns ---
    API_PATTERNS: list[_PatternDef] = [
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'\b(?:httpClient|client)\s*\.\s*(?:get|post|put|delete|patch|request)\s*\(', re.IGNORECASE),
            "HTTP client call: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'@GET\s*\('),
            "Retrofit @GET annotation: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'@POST\s*\('),
            "Retrofit @POST annotation: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'@PUT\s*\('),
            "Retrofit @PUT annotation: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'@DELETE\s*\('),
            "Retrofit @DELETE annotation: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'@PATCH\s*\('),
            "Retrofit @PATCH annotation: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'\bURLSession\b.*\b(?:dataTask|downloadTask|uploadTask)\s*\('),
            "URLSession request: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'\bHttpClient\s*\('),
            "Ktor HttpClient instantiation: {match}",
        ),
        _PatternDef(
            PatternType.API_CALL,
            re.compile(r'\bURLRequest\s*\('),
            "URLRequest creation: {match}",
        ),
    ]

    # --- State management patterns ---
    STATE_PATTERNS: list[_PatternDef] = [
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\bStateFlow\b'),
            "StateFlow usage: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\bMutableStateFlow\b'),
            "MutableStateFlow usage: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\bMutableState\b'),
            "MutableState usage: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'@Published\b'),
            "@Published property: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\bLiveData\b'),
            "LiveData usage: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\bMutableLiveData\b'),
            "MutableLiveData usage: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\bremember\s*\{'),
            "Compose remember block: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\brememberSaveable\s*\{'),
            "Compose rememberSaveable block: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\b@ObservedObject\b'),
            "@ObservedObject property: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\b@StateObject\b'),
            "@StateObject property: {match}",
        ),
        _PatternDef(
            PatternType.STATE_MANAGEMENT,
            re.compile(r'\b@State\b'),
            "@State property: {match}",
        ),
    ]

    # --- User input patterns ---
    INPUT_PATTERNS: list[_PatternDef] = [
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bonClick\s*[\({]'),
            "onClick handler: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bonValueChange\s*[\({=]'),
            "onValueChange handler: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\baddTarget\s*\('),
            "addTarget action: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bUITapGestureRecognizer\s*\('),
            "Tap gesture recognizer: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bUISwipeGestureRecognizer\s*\('),
            "Swipe gesture recognizer: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bUILongPressGestureRecognizer\s*\('),
            "Long press gesture recognizer: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bonLongClick\s*[\({]'),
            "onLongClick handler: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bsetOnClickListener\s*[\({]'),
            "setOnClickListener: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\.gesture\s*\('),
            "SwiftUI gesture modifier: {match}",
        ),
        _PatternDef(
            PatternType.USER_INPUT,
            re.compile(r'\bonTapGesture\s*[\({]'),
            "onTapGesture handler: {match}",
        ),
    ]

    def __init__(self) -> None:
        """Initialize PatternAnalyzer with all pattern definitions."""
        self._all_patterns: list[_PatternDef] = (
            self.NAVIGATION_PATTERNS
            + self.API_PATTERNS
            + self.STATE_PATTERNS
            + self.INPUT_PATTERNS
        )

    def analyze(self, file_change: FileChange) -> list[DetectedPattern]:
        """Analyze a file change for code patterns.

        Compares patterns found in base_content vs head_content and reports
        only patterns that differ (added, removed, or modified).

        Args:
            file_change: A FileChange object with base_content and
                head_content populated.

        Returns:
            A list of DetectedPattern objects for patterns that differ
            between base and head.
        """
        # Skip files with no content to analyze
        if file_change.base_content is None and file_change.head_content is None:
            return []

        base_content = file_change.base_content or ""
        head_content = file_change.head_content or ""

        # Scan both versions
        base_matches = self._scan_content(base_content)
        head_matches = self._scan_content(head_content)

        # Classify differences
        return self._classify_patterns(
            base_matches, head_matches, file_change.path
        )

    def _scan_content(self, content: str) -> list[_PatternMatch]:
        """Scan content for all pattern matches.

        Args:
            content: The file content to scan.

        Returns:
            A list of _PatternMatch objects for each match found.
        """
        matches: list[_PatternMatch] = []

        if not content:
            return matches

        lines = content.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            for pattern_def in self._all_patterns:
                for regex_match in pattern_def.regex.finditer(line):
                    matched_text = regex_match.group(0).strip()
                    description = pattern_def.description_template.format(
                        match=matched_text
                    )
                    # match_key combines type + matched text for comparison
                    match_key = f"{pattern_def.pattern_type.value}:{matched_text}"
                    matches.append(
                        _PatternMatch(
                            pattern_type=pattern_def.pattern_type,
                            description=description,
                            line_number=line_idx,
                            match_key=match_key,
                        )
                    )

        return matches

    def _classify_patterns(
        self,
        base_matches: list[_PatternMatch],
        head_matches: list[_PatternMatch],
        file_path: str,
    ) -> list[DetectedPattern]:
        """Classify patterns by comparing base and head matches.

        A pattern is:
        - "added" if its match_key appears in head but not in base
        - "removed" if its match_key appears in base but not in head
        - "modified" if its match_key appears in both but at different line numbers

        Args:
            base_matches: Pattern matches from base content.
            head_matches: Pattern matches from head content.
            file_path: The source file path for attribution.

        Returns:
            A list of DetectedPattern objects for differing patterns.
        """
        detected: list[DetectedPattern] = []

        # Build lookup dicts: match_key -> list of (line_number, description, pattern_type)
        base_by_key: dict[str, list[_PatternMatch]] = {}
        for m in base_matches:
            base_by_key.setdefault(m.match_key, []).append(m)

        head_by_key: dict[str, list[_PatternMatch]] = {}
        for m in head_matches:
            head_by_key.setdefault(m.match_key, []).append(m)

        # All unique keys across both versions
        all_keys = set(base_by_key.keys()) | set(head_by_key.keys())

        for key in all_keys:
            base_items = base_by_key.get(key, [])
            head_items = head_by_key.get(key, [])

            base_lines = {m.line_number for m in base_items}
            head_lines = {m.line_number for m in head_items}

            if not base_items and head_items:
                # Pattern only in head → added
                for m in head_items:
                    detected.append(
                        DetectedPattern(
                            pattern_type=m.pattern_type,
                            description=m.description,
                            file_path=file_path,
                            line_number=m.line_number,
                            status=LocatorStatus.ADDED,
                        )
                    )
            elif base_items and not head_items:
                # Pattern only in base → removed
                for m in base_items:
                    detected.append(
                        DetectedPattern(
                            pattern_type=m.pattern_type,
                            description=m.description,
                            file_path=file_path,
                            line_number=m.line_number,
                            status=LocatorStatus.REMOVED,
                        )
                    )
            elif base_lines != head_lines:
                # Pattern in both but at different lines → modified
                # Report from the head version (current state)
                for m in head_items:
                    detected.append(
                        DetectedPattern(
                            pattern_type=m.pattern_type,
                            description=m.description,
                            file_path=file_path,
                            line_number=m.line_number,
                            status=LocatorStatus.MODIFIED,
                        )
                    )
            # If same keys AND same lines → no change, skip

        # Sort by line number for consistent output
        detected.sort(key=lambda d: d.line_number)

        return detected
