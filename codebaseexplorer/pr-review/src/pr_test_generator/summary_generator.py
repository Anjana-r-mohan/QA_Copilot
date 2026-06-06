"""Human-readable code change summary generator using Google Gemini.

Takes the raw diff data (file changes, locators, patterns) and asks Gemini
to produce a plain-English summary that a non-developer can understand.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate_readable_summary(
    file_changes: list,
    locators: list,
    patterns: list,
    metadata,
    output_dir: Path,
) -> Path:
    """Generate a human-readable code change summary using Gemini.

    Args:
        file_changes: List of FileChange objects with content.
        locators: List of DetectedLocator objects.
        patterns: List of DetectedPattern objects.
        metadata: PRMetadata object.
        output_dir: Directory to write the summary file.

    Returns:
        Path to the generated summary file.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.info("GEMINI_API_KEY not set — falling back to basic summary")
        return _write_fallback_summary(file_changes, locators, patterns, metadata, output_dir)

    try:
        from google import genai
    except ImportError:
        logger.warning("google-genai package not installed — falling back to basic summary")
        return _write_fallback_summary(file_changes, locators, patterns, metadata, output_dir)

    try:
        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(file_changes, locators, patterns, metadata)
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )
        summary_text = response.text
    except Exception as e:
        logger.error("Gemini API call failed: %s — falling back to basic summary", e)
        return _write_fallback_summary(file_changes, locators, patterns, metadata, output_dir)

    # Write the summary
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# Code Change Summary — PR #{metadata.pr_id}")
    lines.append("")
    lines.append(f"**PR Title:** {metadata.title}")
    lines.append(f"**Author:** {metadata.author}")
    lines.append(f"**Branch:** {metadata.source_branch} → {metadata.destination_branch}")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(summary_text)

    summary_path = output_dir / f"{metadata.repo_slug}-PR{metadata.pr_id}-change-summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Change summary saved to %s", summary_path)
    return summary_path


def _build_prompt(file_changes, locators, patterns, metadata) -> str:
    """Build the prompt for Gemini with code change context."""

    # File summaries
    file_info = []
    for fc in file_changes:
        short_name = fc.path.rsplit("/", 1)[-1] if "/" in fc.path else fc.path
        info = f"- **{short_name}** ({fc.change_type.value}): `{fc.path}`"
        if fc.old_path:
            info += f" (renamed from `{fc.old_path}`)"

        # Include a snippet of what changed (first 30 lines of diff-like context)
        if fc.head_content and fc.base_content:
            # Show key differences
            base_lines = set(fc.base_content.splitlines())
            head_lines = fc.head_content.splitlines()
            added = [l.strip() for l in head_lines if l not in base_lines and l.strip()][:15]
            if added:
                info += "\n  New code added: " + "; ".join(added[:5])
        elif fc.head_content and not fc.base_content:
            # New file — show key imports/class names
            key_lines = [l.strip() for l in fc.head_content.splitlines()
                        if l.strip() and (l.strip().startswith("class ") or
                                          l.strip().startswith("fun ") or
                                          l.strip().startswith("import ") or
                                          l.strip().startswith("@Composable"))][:10]
            if key_lines:
                info += "\n  Key elements: " + "; ".join(key_lines[:5])

        file_info.append(info)

    # Locator changes
    locator_info = []
    for loc in locators:
        locator_info.append(f"- {loc.status.value}: `{loc.value}` ({loc.locator_type.value}) in {loc.file_path.rsplit('/', 1)[-1]} at line {loc.line_number}")

    # Pattern changes
    pattern_info = []
    for pat in patterns:
        pattern_info.append(f"- {pat.status.value}: {pat.description} in {pat.file_path.rsplit('/', 1)[-1]}")

    prompt = f"""You are a technical writer summarizing code changes for a QA team.

Given this Pull Request information, write a clear, human-readable summary that a non-developer QA tester can understand. Describe WHAT was changed in simple terms, focusing on the user-visible impact.

**PR Title:** {metadata.title}
**Author:** {metadata.author}
**Branch:** {metadata.source_branch} → {metadata.destination_branch}
**Total files changed:** {len(file_changes)}

## Files Changed:
{chr(10).join(file_info[:20])}

## UI Elements Changed:
{chr(10).join(locator_info[:30]) if locator_info else "None detected"}

## Code Behavior Changes:
{chr(10).join(pattern_info[:30]) if pattern_info else "None detected"}

---

Write the summary in this format:

## What Changed (Plain English)
Write 3-5 bullet points describing what the developer did in simple terms. Example:
- "The developer moved the map component from individual screens into a shared reusable module"
- "A back button was added to the attendance screen"
- "The nearby outlet map was refactored to use the new shared map"

## Screens Affected
List which screens/features in the app are affected by these changes.

## What QA Should Test
Based on the changes, list specific areas that need testing in plain language. Example:
- "Verify the map loads correctly on the Attendance screen"
- "Check that the back button navigates to the previous screen"

## Risk Areas
Mention any potential regression risks (e.g., "Since map was moved to a shared module, all screens using it could be affected").
"""
    return prompt


def _write_fallback_summary(file_changes, locators, patterns, metadata, output_dir) -> Path:
    """Write a basic summary when Gemini is unavailable."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"# Code Change Summary — PR #{metadata.pr_id}")
    lines.append("")
    lines.append(f"**PR Title:** {metadata.title}")
    lines.append(f"**Author:** {metadata.author}")
    lines.append(f"**Branch:** {metadata.source_branch} → {metadata.destination_branch}")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Files Changed")
    lines.append("")
    for fc in file_changes:
        short = fc.path.rsplit("/", 1)[-1] if "/" in fc.path else fc.path
        lines.append(f"- **{short}** — {fc.change_type.value}")
    lines.append("")
    lines.append(f"## UI Elements Affected: {len(locators)}")
    lines.append(f"## Code Patterns Changed: {len(patterns)}")
    lines.append("")
    lines.append("_Note: Set GEMINI_API_KEY in .env for AI-powered human-readable summaries._")

    summary_path = output_dir / f"{metadata.repo_slug}-PR{metadata.pr_id}-change-summary.md"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Fallback summary saved to %s", summary_path)
    return summary_path
