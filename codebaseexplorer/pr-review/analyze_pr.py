"""Simple CLI to analyze a Bitbucket PR directly (no server needed).

Accepts either a Bitbucket PR link or a Bugzilla bug URL.

Usage:
    cd tools/pr-review

    # Direct Bitbucket PR link
    .venv/bin/python analyze_pr.py https://bitbucket.org/bizom/bizom-kmm/pull-requests/6796

    # Bugzilla bug URL (must be FIXED and have a PR link in comments)
    .venv/bin/python analyze_pr.py https://bugzilla.bizom.in/show_bug.cgi?id=153576

When passing a Bugzilla URL, set the BUGZILLA_API_KEY environment variable
(or add it to your .env file) before running.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Ensure src is on the import path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pr_test_generator.settings import load_settings
from pr_test_generator.bitbucket_client import BitbucketClient
from pr_test_generator.analyzer import PRAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


async def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_pr.py <PR_LINK_OR_BUGZILLA_URL>")
        print()
        print("Examples:")
        print("  python analyze_pr.py https://bitbucket.org/bizom/bizom-kmm/pull-requests/6796")
        print("  python analyze_pr.py https://bugzilla.bizom.in/show_bug.cgi?id=153576")
        print()
        print("For Bugzilla URLs, set BUGZILLA_API_KEY in your environment or .env file.")
        sys.exit(1)

    raw_input = sys.argv[1]
    print(f"\nInput: {raw_input}\n")

    # Load settings (reads .env for credentials)
    settings = load_settings()

    # Initialize client and analyzer
    async with BitbucketClient(settings) as client:
        analyzer = PRAnalyzer(client, settings)

        try:
            output_path = await analyzer.analyze(raw_input)
            print(f"\n✅ Done! Test cases written to:\n   {output_path}\n")
        except ValueError as e:
            print(f"\n❌ Error: {e}\n")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Failed: {e}\n")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
