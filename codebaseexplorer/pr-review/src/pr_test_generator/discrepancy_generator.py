"""Discrepancy report generator.

Compares what the developer described in the Bugzilla 'Fix Description'
section against what was actually implemented in the PR code changes.

When discrepancies are found they are written to a dedicated Markdown file:
    {repo}-PR{pr_id}-discrepancyInCommentAndCode.md

The analysis is powered by Google Gemini when GEMINI_API_KEY is available,
with a rule-based fallback that performs keyword / diff-line comparison when
the AI is unavailable.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .input_resolver import BugzillaContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Discrepancy:
    """A single discrepancy between what was described and what was implemented."""

    id: str
    title: str
    fix_description_claim: str  # What the bug comment said would be fixed
    actual_code_observation: str  # What we see (or don't see) in the code
    severity: str  # "High" | "Medium" | "Low"
    recommendation: str  # Suggested test / verification step


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_discrepancy_report(
    file_changes: list,
    locators: list,
    patterns: list,
    metadata,          # PRMetadata
    bugzilla_context: "BugzillaContext",
    output_dir: Path,
) -> Path | None:
    """Compare Bugzilla Fix Description against PR code changes and write a report.

    Args:
        file_changes: List of FileChange objects with diff content.
        locators: List of DetectedLocator objects.
        patterns: List of DetectedPattern objects.
        metadata: PRMetadata for the pull request.
        bugzilla_context: BugzillaContext containing the bug ID, summary, and
            fix_description extracted from Bugzilla comments.
        output_dir: Directory where the report file will be written.

    Returns:
        Path to the written Markdown report, or None if no fix description
        was available (nothing to compare against).
    """
    fix_description = bugzilla_context.fix_description
    if not fix_description:
        logger.info(
            "Bug %d has no 'Fix Description' — skipping discrepancy analysis",
            bugzilla_context.bug_id,
        )
        return None

    logger.info(
        "Generating discrepancy report for bug %d / PR %s-%d",
        bugzilla_context.bug_id,
        metadata.repo_slug,
        metadata.pr_id,
    )

    discrepancies = _analyse(
        fix_description, file_changes, locators, patterns, metadata, bugzilla_context
    )

    return _write_report(
        discrepancies, fix_description, metadata, bugzilla_context, output_dir
    )


# ---------------------------------------------------------------------------
# Analysis — try Gemini first, fall back to rule-based
# ---------------------------------------------------------------------------


def _analyse(
    fix_description: str,
    file_changes: list,
    locators: list,
    patterns: list,
    metadata,
    bugzilla_context: "BugzillaContext",
) -> list[Discrepancy]:
    """Run the discrepancy analysis, returning a list of Discrepancy objects."""

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            return _analyse_with_gemini(
                api_key, fix_description, file_changes, locators, patterns, metadata, bugzilla_context
            )
        except Exception as exc:
            logger.warning("Gemini discrepancy analysis failed (%s) — using rule-based fallback", exc)

    return _analyse_rule_based(fix_description, file_changes, locators, patterns, metadata)


def _analyse_with_gemini(
    api_key: str,
    fix_description: str,
    file_changes: list,
    locators: list,
    patterns: list,
    metadata,
    bugzilla_context: "BugzillaContext",
) -> list[Discrepancy]:
    """Use Google Gemini to identify discrepancies."""
    from google import genai  # type: ignore

    prompt = _build_gemini_prompt(
        fix_description, file_changes, locators, patterns, metadata, bugzilla_context
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-05-20",
        contents=prompt,
    )
    raw_text = response.text or ""
    return _parse_gemini_response(raw_text)


def _build_gemini_prompt(
    fix_description: str,
    file_changes: list,
    locators: list,
    patterns: list,
    metadata,
    bugzilla_context: "BugzillaContext",
) -> str:
    """Build the Gemini prompt for discrepancy analysis."""

    # Summarise changed files with relevant diff lines
    file_summaries: list[str] = []
    for fc in file_changes[:20]:
        short = fc.path.rsplit("/", 1)[-1] if "/" in fc.path else fc.path
        summary = f"- **{short}** ({fc.change_type.value}): `{fc.path}`"

        if fc.head_content and fc.base_content:
            base_set = set(fc.base_content.splitlines())
            added = [
                l.strip()
                for l in fc.head_content.splitlines()
                if l.strip() and l not in base_set
            ][:20]
            if added:
                summary += "\n  Added lines: " + " | ".join(added[:10])
        elif fc.head_content:
            key = [
                l.strip()
                for l in fc.head_content.splitlines()
                if l.strip() and not l.strip().startswith("//")
            ][:10]
            if key:
                summary += "\n  New file key lines: " + " | ".join(key[:5])

        file_summaries.append(summary)

    locator_lines = [
        f"- {loc.status.value}: `{loc.value}` ({loc.locator_type.value})"
        for loc in locators
    ] or ["None detected"]

    pattern_lines = [
        f"- {pat.status.value}: {pat.description}"
        for pat in patterns
    ] or ["None detected"]

    return f"""You are a QA engineer performing discrepancy analysis between a bug fix description and the actual code changes in a pull request.

## Bug Information
- **Bug ID:** {bugzilla_context.bug_id}
- **Bug Summary:** {bugzilla_context.bug_summary}
- **Bug URL:** {bugzilla_context.bug_url}

## Fix Description (from Bugzilla comment)
{fix_description}

## Actual PR Code Changes
**PR:** {metadata.pr_link}
**Branch:** {metadata.source_branch} → {metadata.destination_branch}
**Files changed:** {len(file_changes)}

### Changed Files:
{chr(10).join(file_summaries)}

### UI Locators Changed:
{chr(10).join(locator_lines)}

### Code Patterns Changed:
{chr(10).join(pattern_lines)}

---

## Your Task
Compare the Fix Description against the actual code changes and identify any discrepancies — things the developer claimed to fix or change that are NOT reflected in the code, OR things changed in the code that contradict the fix description.

Respond in this EXACT format (repeat the DISCREPANCY block for each finding, output NONE if there are no discrepancies):

DISCREPANCY_START
TITLE: <short title of the discrepancy>
CLAIM: <what the Fix Description says was done>
OBSERVATION: <what the actual code shows — or lacks>
SEVERITY: <High | Medium | Low>
RECOMMENDATION: <specific test case or verification step for QA>
DISCREPANCY_END

Focus on meaningful discrepancies that matter for QA testing. Ignore minor wording differences.
"""


def _parse_gemini_response(text: str) -> list[Discrepancy]:
    """Parse structured discrepancy blocks from Gemini's response."""
    discrepancies: list[Discrepancy] = []

    if "NONE" in text.upper() and "DISCREPANCY_START" not in text:
        return discrepancies

    blocks = re.findall(
        r"DISCREPANCY_START(.*?)DISCREPANCY_END",
        text,
        re.DOTALL,
    )

    for idx, block in enumerate(blocks, start=1):
        title = _extract_field(block, "TITLE") or f"Discrepancy {idx}"
        claim = _extract_field(block, "CLAIM") or "Not specified"
        observation = _extract_field(block, "OBSERVATION") or "Not specified"
        severity = _extract_field(block, "SEVERITY") or "Medium"
        recommendation = _extract_field(block, "RECOMMENDATION") or "Manual verification required"

        # Normalise severity
        sev_upper = severity.strip().upper()
        if sev_upper in ("HIGH", "MEDIUM", "LOW"):
            severity = sev_upper.capitalize()
        else:
            severity = "Medium"

        discrepancies.append(
            Discrepancy(
                id=f"DISC-{idx}",
                title=title.strip(),
                fix_description_claim=claim.strip(),
                actual_code_observation=observation.strip(),
                severity=severity,
                recommendation=recommendation.strip(),
            )
        )

    return discrepancies


def _extract_field(block: str, field_name: str) -> str | None:
    """Extract a labelled field from a discrepancy block."""
    match = re.search(
        rf"^{field_name}:\s*(.+?)(?=\n[A-Z_]+:|$)",
        block,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

# Keywords we look for inside the Fix Description to understand what was claimed
_CLAIM_PATTERNS = [
    (r"\bfixed?\b", "bug fix"),
    (r"\bupdate[d]?\b", "update"),
    (r"\bremove[d]?\b", "removal"),
    (r"\badd(ed)?\b", "addition"),
    (r"\brefactor(ed)?\b", "refactor"),
    (r"\bchange[d]?\b", "change"),
    (r"\bnavigate[d]?\b", "navigation"),
    (r"\bAPI\b", "api call"),
    (r"\bbutton\b", "ui element"),
    (r"\bscreen\b", "screen"),
    (r"\bcrash\b", "crash fix"),
    (r"\bnull\b", "null handling"),
]


def _analyse_rule_based(
    fix_description: str,
    file_changes: list,
    locators: list,
    patterns: list,
    metadata,
) -> list[Discrepancy]:
    """Simple keyword-based discrepancy detection when Gemini is unavailable."""
    discrepancies: list[Discrepancy] = []
    disc_id = 0

    fix_lower = fix_description.lower()

    # Collect all code tokens from the diff
    all_added_text = ""
    for fc in file_changes:
        if fc.head_content:
            if fc.base_content:
                base_set = set(fc.base_content.splitlines())
                added = [l for l in fc.head_content.splitlines() if l not in base_set]
            else:
                added = fc.head_content.splitlines()
            all_added_text += " ".join(added).lower() + " "

    def _add(title, claim, observation, severity, recommendation):
        nonlocal disc_id
        disc_id += 1
        discrepancies.append(
            Discrepancy(
                id=f"DISC-{disc_id}",
                title=title,
                fix_description_claim=claim,
                actual_code_observation=observation,
                severity=severity,
                recommendation=recommendation,
            )
        )

    # Check: fix description mentions a crash / null-pointer fix
    if re.search(r"\b(crash|npe|null\s*pointer|nullpointer)\b", fix_lower):
        if not re.search(r"\b(null|nullcheck|orEmpty|let\s*\{|checkNotNull|requireNotNull)\b", all_added_text):
            _add(
                title="Null/crash fix not reflected in code",
                claim="Fix Description mentions a crash or null-pointer fix",
                observation="No obvious null-checks or safe-call operators found in the added code",
                severity="High",
                recommendation=(
                    "Reproduce the original crash scenario and verify it no longer occurs. "
                    "Check the changed files for null-safety guards."
                ),
            )

    # Check: fix description mentions UI changes but no UI locators were touched
    if re.search(r"\b(button|screen|text|label|icon|image|ui|layout)\b", fix_lower):
        if not locators:
            _add(
                title="UI change claimed but no UI locators detected",
                claim="Fix Description references UI elements (button/screen/label/etc.)",
                observation="No UI locators were detected as added, modified, or removed in the diff",
                severity="Medium",
                recommendation=(
                    "Manually inspect the affected screens to verify the UI change described "
                    "in the Fix Description is visible and correct."
                ),
            )

    # Check: fix description mentions API/network changes but no API patterns found
    if re.search(r"\b(api|endpoint|request|response|http|retrofit|service)\b", fix_lower):
        api_patterns = [p for p in patterns if p.pattern_type.value == "api_call"]
        if not api_patterns:
            _add(
                title="API change claimed but no API call patterns detected",
                claim="Fix Description references API, endpoint, or network request changes",
                observation="No API call patterns were detected as changed in the diff",
                severity="Medium",
                recommendation=(
                    "Use a network proxy (Charles/Proxyman) to verify the expected API "
                    "request is correctly formed and the response is handled as described."
                ),
            )

    # Check: fix description mentions navigation but no navigation patterns found
    if re.search(r"\b(navigat|route|screen\s+flow|back\s+stack|deep\s*link)\b", fix_lower):
        nav_patterns = [p for p in patterns if p.pattern_type.value == "navigation"]
        if not nav_patterns:
            _add(
                title="Navigation change claimed but not detected in diff",
                claim="Fix Description references navigation or routing changes",
                observation="No navigation patterns were detected as changed in the diff",
                severity="Medium",
                recommendation=(
                    "Manually test the navigation flow described in the Fix Description "
                    "and verify forward and back navigation behave as expected."
                ),
            )

    # Check: fix description mentions removing a feature/element but no removals in code
    if re.search(r"\b(remove[d]?|delet[e|ed]?|hidden?)\b", fix_lower):
        removed_locators = [loc for loc in locators if loc.status.value == "removed"]
        removed_patterns = [pat for pat in patterns if pat.status.value == "removed"]
        if not removed_locators and not removed_patterns:
            _add(
                title="Removal claimed in Fix Description but nothing removed in code",
                claim="Fix Description mentions removing or hiding an element/feature",
                observation="No removed locators or patterns were detected in the diff",
                severity="Low",
                recommendation=(
                    "Verify that the element or feature mentioned in the Fix Description "
                    "is indeed absent from the relevant screens after the change."
                ),
            )

    if not discrepancies:
        # Produce a generic note that manual review is needed
        disc_id += 1
        discrepancies.append(
            Discrepancy(
                id="DISC-1",
                title="Manual review recommended (rule-based analysis only)",
                fix_description_claim=fix_description[:300] + ("..." if len(fix_description) > 300 else ""),
                actual_code_observation=(
                    "Automated keyword analysis did not detect specific discrepancies. "
                    "A manual comparison between the Fix Description and the diff is recommended."
                ),
                severity="Low",
                recommendation=(
                    "Read the Fix Description carefully and trace each claim through the "
                    "changed files to confirm the implementation matches the intention."
                ),
            )
        )

    return discrepancies


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def _write_report(
    discrepancies: list[Discrepancy],
    fix_description: str,
    metadata,
    bugzilla_context: "BugzillaContext",
    output_dir: Path,
) -> Path:
    """Render and write the discrepancy Markdown report."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []

    # ── Header ─────────────────────────────────────────────────────────────
    lines += [
        f"# Discrepancy Report — {metadata.repo_slug} PR#{metadata.pr_id} vs Bugzilla Bug #{bugzilla_context.bug_id}",
        "",
        f"**Generated:** {timestamp} UTC",
        f"**PR Link:** {metadata.pr_link}",
        f"**Bugzilla Bug:** [{bugzilla_context.bug_url}]({bugzilla_context.bug_url})",
        f"**Bug Summary:** {bugzilla_context.bug_summary}",
        f"**Branch:** {metadata.source_branch} → {metadata.destination_branch}",
        "",
        "---",
        "",
    ]

    # ── Fix Description ────────────────────────────────────────────────────
    lines += [
        "## Fix Description (from Bugzilla)",
        "",
        "> " + fix_description.replace("\n", "\n> "),
        "",
        "---",
        "",
    ]

    # ── Summary ───────────────────────────────────────────────────────────
    high = sum(1 for d in discrepancies if d.severity == "High")
    medium = sum(1 for d in discrepancies if d.severity == "Medium")
    low = sum(1 for d in discrepancies if d.severity == "Low")

    lines += [
        "## Summary",
        "",
        f"| Severity | Count |",
        f"|----------|-------|",
        f"| 🔴 High   | {high}     |",
        f"| 🟡 Medium | {medium}   |",
        f"| 🟢 Low    | {low}      |",
        f"| **Total** | **{len(discrepancies)}** |",
        "",
        "---",
        "",
        "## Discrepancies Found",
        "",
    ]

    if not discrepancies:
        lines += [
            "_No discrepancies detected between the Fix Description and the PR code changes._",
            "",
        ]
    else:
        for disc in discrepancies:
            severity_icon = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(disc.severity, "⚪")
            lines += [
                f"### {disc.id}: {disc.title}",
                "",
                f"**Severity:** {severity_icon} {disc.severity}",
                "",
                "**What the Fix Description Claims:**",
                "",
                f"> {disc.fix_description_claim}",
                "",
                "**What the Code Shows:**",
                "",
                f"> {disc.actual_code_observation}",
                "",
                "**Recommended Test / Verification:**",
                "",
                disc.recommendation,
                "",
                "---",
                "",
            ]

    lines.append("**End of Discrepancy Report**")

    report_path = (
        output_dir / f"{metadata.repo_slug}-PR{metadata.pr_id}-discrepancyInCommentAndCode.md"
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Discrepancy report saved to %s", report_path)
    return report_path
