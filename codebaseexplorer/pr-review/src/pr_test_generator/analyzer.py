"""PR Analyzer module.

Orchestrates the full analysis pipeline: validate PR link → fetch metadata →
fetch files → detect locators → analyze patterns → generate tests.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from models import PRMetadata

from .bitbucket_client import BitbucketClient, BitbucketClientError
from .diff_extractor import DiffExtractor
from .input_resolver import resolve_input_to_pr_link_with_context
from .locator_detector import LocatorDetector
from .pattern_analyzer import PatternAnalyzer
from .test_generator import TestGenerator

if TYPE_CHECKING:
    from .settings import Settings

logger = logging.getLogger(__name__)

# Regex pattern to match Bitbucket PR URLs.
# Captures workspace, repo_slug, and pr_id from:
#   https://bitbucket.org/{workspace}/{repo_slug}/pull-requests/{pr_id}
_PR_LINK_PATTERN = re.compile(
    r"^https://bitbucket\.org/"
    r"(?P<workspace>[A-Za-z0-9_\-]+)/"
    r"(?P<repo_slug>[A-Za-z0-9_\-.]+)/"
    r"pull-requests/"
    r"(?P<pr_id>\d+)$"
)


class PRAnalyzer:
    """Orchestrates PR analysis from link parsing through test generation."""

    def __init__(self, client: BitbucketClient, settings: "Settings") -> None:
        self._client = client
        self._settings = settings

    def parse_pr_link(self, url: str) -> tuple[str, str, int]:
        """Extract (workspace, repo_slug, pr_id) from a Bitbucket PR URL.

        Args:
            url: A Bitbucket Cloud pull request URL.

        Returns:
            A tuple of (workspace, repo_slug, pr_id).

        Raises:
            ValueError: If the URL does not match the expected pattern or
                pr_id is not a positive integer.
        """
        match = _PR_LINK_PATTERN.match(url.strip())
        if match is None:
            raise ValueError(
                "Invalid PR link. Expected format: "
                "https://bitbucket.org/{workspace}/{repo_slug}/pull-requests/{pr_id}\n"
                "Example: https://bitbucket.org/my-team/my-repo/pull-requests/42"
            )

        workspace = match.group("workspace")
        repo_slug = match.group("repo_slug")
        pr_id_str = match.group("pr_id")

        pr_id = int(pr_id_str)
        if pr_id <= 0:
            raise ValueError(
                "Invalid PR ID: pull request ID must be a positive integer. "
                "Example: https://bitbucket.org/my-team/my-repo/pull-requests/42"
            )

        return workspace, repo_slug, pr_id

    async def fetch_pr_metadata(
        self, workspace: str, repo_slug: str, pr_id: int
    ) -> PRMetadata:
        """Fetch PR metadata from the Bitbucket API.

        Args:
            workspace: The Bitbucket workspace slug.
            repo_slug: The repository slug.
            pr_id: The pull request numeric ID.

        Returns:
            A PRMetadata dataclass populated from the API response.

        Raises:
            ValueError: If the pull request is not found (404).
            BitbucketClientError: For other API errors (auth, rate-limit, etc.).
        """
        url = f"/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}"

        try:
            response = await self._client.request("GET", url)
        except BitbucketClientError as exc:
            if exc.status_code == 404:
                raise ValueError(
                    f"Pull request not found: {workspace}/{repo_slug}#{pr_id}"
                ) from exc
            raise

        data = response.json()

        return PRMetadata(
            title=data["title"],
            author=data["author"]["display_name"],
            source_branch=data["source"]["branch"]["name"],
            destination_branch=data["destination"]["branch"]["name"],
            head_commit=data["source"]["commit"]["hash"],
            base_commit=data["destination"]["commit"]["hash"],
            pr_link=f"https://bitbucket.org/{workspace}/{repo_slug}/pull-requests/{pr_id}",
            workspace=workspace,
            repo_slug=repo_slug,
            pr_id=pr_id,
        )

    async def analyze(self, pr_link: str) -> Path:
        """Full analysis pipeline. Returns path to generated Markdown file.

        Orchestrates: parse_pr_link → fetch PR metadata → extract diff →
        detect locators → analyze patterns → generate tests → write output.

        Graceful degradation: if locator detection or pattern analysis fails
        for a single file, that file is skipped and processing continues.
        If no testable changes are found, a summary-only output is produced.

        Args:
            pr_link: A Bitbucket Cloud pull request URL.

        Returns:
            The Path to the generated Markdown output file.

        Raises:
            ValueError: If the PR link is invalid or the PR is not found.
            BitbucketClientError: For authentication or API errors.
        """
        # 0. Resolve input: Bugzilla URL → Bitbucket PR link (or pass-through)
        pr_link, bugzilla_context = resolve_input_to_pr_link_with_context(pr_link)

        # 1. Parse the PR link
        workspace, repo_slug, pr_id = self.parse_pr_link(pr_link)

        # 2. Fetch PR metadata
        metadata = await self.fetch_pr_metadata(workspace, repo_slug, pr_id)

        # 3. Extract diff (fetch diffstat + file contents)
        extractor = DiffExtractor(self._client)
        file_changes = await extractor.fetch_diffstat(workspace, repo_slug, pr_id)
        file_changes = await extractor.fetch_file_contents(
            workspace, repo_slug, file_changes, metadata.base_commit, metadata.head_commit
        )

        # 4. Detect locators (graceful degradation per file)
        detector = LocatorDetector()
        all_locators = []
        for fc in file_changes:
            try:
                locators = detector.detect(fc)
                all_locators.extend(locators)
            except Exception as e:
                logger.warning("Locator detection failed for %s: %s", fc.path, e)

        # 5. Analyze patterns (graceful degradation per file)
        pattern_analyzer = PatternAnalyzer()
        all_patterns = []
        for fc in file_changes:
            try:
                patterns = pattern_analyzer.analyze(fc)
                all_patterns.extend(patterns)
            except Exception as e:
                logger.warning("Pattern analysis failed for %s: %s", fc.path, e)

        # 6. Build PR metadata dict for test generator
        pr_metadata_dict = {
            "pr_link": metadata.pr_link,
            "source_branch": metadata.source_branch,
            "destination_branch": metadata.destination_branch,
            "changed_file_count": len(file_changes),
            "repo_slug": metadata.repo_slug,
            "pr_id": metadata.pr_id,
        }

        # 7. Generate change summary FIRST — used as context for test enhancement
        from .summary_generator import generate_readable_summary
        summary_path = generate_readable_summary(
            file_changes, all_locators, all_patterns, metadata, self._settings.output_dir
        )
        # Read the summary text so we can pass it to the test enhancer
        change_summary_text = ""
        try:
            if summary_path and summary_path.exists():
                change_summary_text = summary_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Could not read change summary: %s", e)

        # 8. Generate base test cases from locators and patterns
        generator = TestGenerator()
        test_cases = generator.generate(all_locators, all_patterns, pr_metadata_dict)

        # 8.5. Enhance test cases with AI — pass the change summary for richer context
        from .ai_test_enhancer import enhance_test_cases_with_ai
        test_cases = enhance_test_cases_with_ai(
            test_cases, file_changes, all_locators, all_patterns, metadata,
            change_summary=change_summary_text,
        )

        # 9. Render Markdown and write output
        markdown = generator.render_markdown(test_cases, pr_metadata_dict)
        output_path = generator.write_output(
            markdown, metadata.repo_slug, metadata.pr_id, self._settings.output_dir
        )

        # 10. Save locators and patterns to JSON file
        self._save_locators_json(
            all_locators, all_patterns, metadata, self._settings.output_dir
        )

        # 11. Generate Bugzilla Fix Description discrepancy report (only for Bugzilla inputs)
        if bugzilla_context is not None:
            from .discrepancy_generator import generate_discrepancy_report
            disc_path = generate_discrepancy_report(
                file_changes,
                all_locators,
                all_patterns,
                metadata,
                bugzilla_context,
                self._settings.output_dir,
            )
            if disc_path:
                logger.info("Discrepancy report written to %s", disc_path)

        return output_path

    def _save_locators_json(
        self,
        locators: list,
        patterns: list,
        metadata: "PRMetadata",
        output_dir: Path,
    ) -> None:
        """Save detected locators and patterns to a JSON file for persistence.

        Written alongside the Markdown output as {repo}-PR{id}-locators.json.
        """
        import json
        from datetime import datetime, timezone

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "pr_link": metadata.pr_link,
            "repo_slug": metadata.repo_slug,
            "pr_id": metadata.pr_id,
            "source_branch": metadata.source_branch,
            "destination_branch": metadata.destination_branch,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "locators": [
                {
                    "type": loc.locator_type.value,
                    "value": loc.value,
                    "file_path": loc.file_path,
                    "line_number": loc.line_number,
                    "status": loc.status.value,
                }
                for loc in locators
            ],
            "patterns": [
                {
                    "type": pat.pattern_type.value,
                    "description": pat.description,
                    "file_path": pat.file_path,
                    "line_number": pat.line_number,
                    "status": pat.status.value,
                }
                for pat in patterns
            ],
        }

        json_path = output_dir / f"{metadata.repo_slug}-PR{metadata.pr_id}-locators.json"
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Locators saved to %s", json_path)

    def _save_change_summary(
        self,
        file_changes: list,
        locators: list,
        patterns: list,
        metadata: "PRMetadata",
        output_dir: Path,
    ) -> None:
        """Save a detailed code change summary as a Markdown file.

        Describes what changed in each file: which functions were modified,
        what UI elements were added/removed, what API calls changed, etc.
        Written as {repo}-PR{id}-change-summary.md.
        """
        from datetime import datetime, timezone
        from models import FileChangeType

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []

        # Header
        lines.append(f"# Code Change Summary — PR #{metadata.pr_id}")
        lines.append("")
        lines.append(f"**PR Title:** {metadata.title}")
        lines.append(f"**Author:** {metadata.author}")
        lines.append(f"**Source Branch:** {metadata.source_branch}")
        lines.append(f"**Destination Branch:** {metadata.destination_branch}")
        lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
        lines.append(f"**PR Link:** {metadata.pr_link}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Overall stats
        change_type_counts: dict[str, int] = {}
        for fc in file_changes:
            key = fc.change_type.value
            change_type_counts[key] = change_type_counts.get(key, 0) + 1

        lines.append("## Overview")
        lines.append("")
        lines.append(f"- **Total files changed:** {len(file_changes)}")
        for ct, count in sorted(change_type_counts.items()):
            lines.append(f"  - {ct.capitalize()}: {count}")
        lines.append(f"- **UI locators affected:** {len(locators)}")
        lines.append(f"- **Code patterns detected:** {len(patterns)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Per-file detail
        lines.append("## File-by-File Changes")
        lines.append("")

        for idx, fc in enumerate(file_changes, start=1):
            short_name = fc.path.rsplit("/", 1)[-1] if "/" in fc.path else fc.path
            lines.append(f"### {idx}. {short_name}")
            lines.append(f"**Full Path:** `{fc.path}`")
            lines.append(f"**Change Type:** {fc.change_type.value.upper()}")
            if fc.old_path:
                lines.append(f"**Renamed From:** `{fc.old_path}`")
            lines.append("")

            # Locators in this file
            file_locators = [loc for loc in locators if loc.file_path == fc.path]
            if file_locators:
                lines.append("**UI Locators Changed:**")
                lines.append("")
                lines.append("| Locator Type | Value | Line | Status |")
                lines.append("|---|---|---|---|")
                for loc in file_locators:
                    lines.append(
                        f"| {loc.locator_type.value} | `{loc.value}` | {loc.line_number} | {loc.status.value} |"
                    )
                lines.append("")

            # Patterns in this file
            file_patterns = [pat for pat in patterns if pat.file_path == fc.path]
            if file_patterns:
                lines.append("**Code Patterns Changed:**")
                lines.append("")
                lines.append("| Pattern Type | Description | Line | Status |")
                lines.append("|---|---|---|---|")
                for pat in file_patterns:
                    desc = pat.description[:80]
                    lines.append(
                        f"| {pat.pattern_type.value} | {desc} | {pat.line_number} | {pat.status.value} |"
                    )
                lines.append("")

            # Diff summary (lines added/removed)
            if fc.base_content is not None and fc.head_content is not None:
                base_lines = fc.base_content.splitlines()
                head_lines = fc.head_content.splitlines()
                added_lines = max(0, len(head_lines) - len(base_lines))
                removed_lines = max(0, len(base_lines) - len(head_lines))
                lines.append(f"**Lines:** {len(head_lines)} total (+{added_lines} / -{removed_lines} net)")
            elif fc.head_content is not None:
                lines.append(f"**Lines:** {len(fc.head_content.splitlines())} (new file)")
            elif fc.base_content is not None:
                lines.append(f"**Lines:** {len(fc.base_content.splitlines())} removed (file deleted)")
            lines.append("")

            # If no locators or patterns, note it
            if not file_locators and not file_patterns:
                lines.append("_No UI locators or behavioral patterns detected in this file._")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Impact summary
        lines.append("## Impact Summary")
        lines.append("")

        locator_added = sum(1 for loc in locators if loc.status.value == "added")
        locator_modified = sum(1 for loc in locators if loc.status.value == "modified")
        locator_removed = sum(1 for loc in locators if loc.status.value == "removed")

        if locator_added:
            lines.append(f"- **{locator_added} new UI elements** added — need visibility, interaction, and accessibility testing")
        if locator_modified:
            lines.append(f"- **{locator_modified} UI elements modified** — need regression verification")
        if locator_removed:
            lines.append(f"- **{locator_removed} UI elements removed** — need absence verification")

        nav_patterns = [p for p in patterns if p.pattern_type.value == "navigation"]
        api_patterns = [p for p in patterns if p.pattern_type.value == "api_call"]
        state_patterns = [p for p in patterns if p.pattern_type.value == "state_management"]
        input_patterns = [p for p in patterns if p.pattern_type.value == "user_input"]

        if nav_patterns:
            lines.append(f"- **{len(nav_patterns)} navigation changes** — need forward/back navigation testing")
        if api_patterns:
            lines.append(f"- **{len(api_patterns)} API call changes** — need network response validation")
        if state_patterns:
            lines.append(f"- **{len(state_patterns)} state management changes** — need state update verification")
        if input_patterns:
            lines.append(f"- **{len(input_patterns)} user input handler changes** — need interaction testing")

        lines.append("")
        lines.append("---")
        lines.append("**End of Change Summary**")

        summary_path = output_dir / f"{metadata.repo_slug}-PR{metadata.pr_id}-change-summary.md"
        summary_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Change summary saved to %s", summary_path)
