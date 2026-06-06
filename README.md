# QA Copilot - AI-Powered Mobile Test Automation

AI-driven test automation using MCP (Model Context Protocol) for intelligent mobile app testing.

## Quick Start

1. **Start Appium**: `appium` (port 4723)
2. **Start Server**: `./restart_server.sh` 
3. **Connect Device**: `adb connect 127.0.0.1:6555`
4. **Use Plugin**: Open IntelliJ → ScriptSherpa tool window

## Usage

In the plugin chat:
- "Explore app based on test plan and generate Appium tests"
- "Generate Playwright tests in TypeScript"

## Architecture

- **MCP Server** (`mcp/`) - 5 Appium tools with AI orchestration
- **Unified Chat** (`agents/unified_chat_agent.py`) - Intelligent agent
- **API Server** (`api_server.py`) - REST API on port 8000

## Test Plan Format

Create `.md` files in workspace `test_plans/` with **atomic UI actions**:

```markdown
# Login Test

## Test Steps
1. Click the login button
2. Enter text in username field
3. Tap the submit button
```

**Critical**: Use specific actions (click, enter, tap), NOT business logic.

## MCP Tools

- `connect_device` - Connect to device
- `get_screen_state` - Get screen elements
- `tap_element` - Tap element
- `input_text` - Input text
- `scroll` - Scroll screen

## Configuration

`.env` file:
```
GEMINI_API_KEY=your_key
# or GOOGLE_API_KEY=your_key

# Optional precondition setup profile
COMPANY_URL=
ADMIN_USERNAME=
ADMIN_PASSWORD=
TEST_USER_USERNAME=
TEST_USER_PASSWORD=

# Optional precondition backend (choose one)
PRECONDITION_API_URL=
DATABASE_URL=

# Optional SQL templates when using DATABASE_URL
PRECONDITION_SQL_ENABLE_TEMPLATE=UPDATE feature_flags SET enabled=1 WHERE key='{setting}';
PRECONDITION_SQL_DISABLE_TEMPLATE=UPDATE feature_flags SET enabled=0 WHERE key='{setting}';
```

Or use Ollama locally.

## Preconditions From Test Plan

If your test plan has a `Preconditions` section, the unified agent will:
1. Read company/admin/user/db config from `.env`
2. Apply enable/disable settings from preconditions
3. Relaunch app before step execution so changes are synced

Supported precondition phrases include examples like:
- `Insights should be enabled`
- `Disable call_recording`
- `menu_feature is disabled`

## Status

✅ MCP architecture active
✅ Real device execution working
✅ AI-driven decisions operational
