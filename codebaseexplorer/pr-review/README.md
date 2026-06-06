# PR Review Tool — Bizom KMM

Bitbucket PR review using Claude Code with full KMM codebase context.
Lives inside the KMM repo — no separate project to maintain.
**Zero impact on Android/iOS builds or app size.**

---

## One-time setup (do this once after cloning)

**Prerequisites:** `uv` installed (`brew install uv`), Claude Code installed.

```bash
# 1. Create your personal credentials file (gitignored — never committed)
cp tools/pr-review/.env.example tools/pr-review/.env

# 2. Open tools/pr-review/.env and fill in YOUR two lines:
#    BITBUCKET_EMAIL=your.email@mobisy.com
#    BITBUCKET_API_TOKEN=<your token>
#
#    Get your token at:
#    https://id.atlassian.com/manage-profile/security/api-tokens
#    → "Create API token with scopes" → app = Bitbucket

# 3. Install Python dependencies
cd tools/pr-review && uv sync

# 4. Restart Claude Code — the MCP server connects automatically
```

---

## How to review a PR

Open the KMM project in Claude Code, then type:

```
/review-pr 42
```

Replace `42` with the Bitbucket PR number.

---

## What happens during a review

1. Fetches all file diffs from Bitbucket (per-file, handles large PRs)
2. Checks out the full KMM codebase into a local worktree
3. Finds all **callers** of every changed function/class across the codebase
4. Reads the full content of changed files (not just the diff)
5. Applies KMM-specific checks:
   - Koin DI registration (missing = iOS runtime crash)
   - SQLDelight schema changes without `DATABASE_VERSION` bump
   - `expect`/`actual` completeness across all platforms
   - Public API breaking changes
   - Network contract changes (`@SerialName`, `BizomApi`)
   - Test coverage for new repositories
6. Shows you a summary of findings and **asks for confirmation before posting anything**
7. After your approval: posts a Code Insights report on Bitbucket tied to the exact commit

---

## Important notes

- **Your `.env` is personal and gitignored** — each developer has their own credentials
- Comments posted to Bitbucket appear under your Bitbucket account
- The review shows the commit hash it reviewed — reviewers can verify it matches the latest commit
- Write operations (posting comments/reports) always ask for your confirmation first
- Worktrees are created in `tools/pr-review/.pr-worktrees/` (gitignored, auto-managed)

---

## Files in this directory

```
tools/pr-review/
├── README.md               ← you are here
├── .env.example            ← credential template (copy to .env)
├── .env                    ← YOUR credentials (gitignored, create from .env.example)
├── pyproject.toml          ← Python project config
├── uv.lock                 ← pinned dependencies (committed)
└── src/bitbucket_mcp/      ← MCP server source (do not modify unless updating the tool)
```
