# QA Copilot - System Architecture

## Overview

QA Copilot is an AI-powered test automation assistant integrated directly into VS Code. It connects to real Android emulators via Appium to extract UI elements, parse test cases from CSV files, and prepare data for automated test generation.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     VS Code IDE                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           QA Copilot Extension                        │  │
│  │  ┌─────────────────────────────────────────────┐     │  │
│  │  │  Chat Interface (Webview)                   │     │  │
│  │  │  - Agent Selector                           │     │  │
│  │  │  - Message Input                            │     │  │
│  │  │  - Quick Actions                            │     │  │
│  │  │  - File Attachment                          │     │  │
│  │  └─────────────────────────────────────────────┘     │  │
│  │                                                       │  │
│  │  ┌──────────────┐  ┌──────────────┐                 │  │
│  │  │ Agents Tree  │  │  Tests Tree  │                 │  │
│  │  └──────────────┘  └──────────────┘                 │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP/REST API
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  FastAPI Server (Python)                    │
│                  http://localhost:8000                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  API Endpoints                                       │  │
│  │  - POST /api/parse-csv                               │  │
│  │  - POST /api/explore-ui                              │  │
│  │  - POST /api/analyze                                 │  │
│  │  - POST /api/generate-tests                          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Agent System                                        │  │
│  │  ┌────────────────┐  ┌────────────────┐             │  │
│  │  │ Test Plan      │  │ UI Explorer    │             │  │
│  │  │ Agent          │  │ Agent          │             │  │
│  │  └────────────────┘  └────────────────┘             │  │
│  │  ┌────────────────┐  ┌────────────────┐             │  │
│  │  │ Codebase       │  │ Test Generator │             │  │
│  │  │ Explorer       │  │ Agent          │             │  │
│  │  └────────────────┘  └────────────────┘             │  │
│  └──────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Appium WebDriver Protocol
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Appium Server (Node.js)                        │
│              http://localhost:4723                          │
│              Version: 3.4.2                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ ADB (Android Debug Bridge)
                       │
┌──────────────────────▼──────────────────────────────────────┐
│              Android Emulator                               │
│              Device: 127.0.0.1:6555 (Genymotion)            │
│              App: co.bizom.apps                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. VS Code Extension (Frontend)

**Technology:** TypeScript, VS Code Extension API

**Components:**

#### Chat Interface (Webview)
- **Purpose:** Main user interaction point
- **Features:**
  - Agent selector dropdown (Test Plan, UI Explorer, Codebase Explorer, Test Generator)
  - Natural language message input
  - Quick action buttons (Parse CSV, Analyze Code, Explore UI, Generate Tests)
  - File attachment button for CSV uploads
  - Message history with user/assistant roles
  - Typing indicators

#### Intent Detection System
- **Purpose:** Understand user commands and trigger appropriate actions
- **Logic:**
  ```typescript
  detectIntent(message: string) {
    if (currentAgent === 'ui' && message.includes('explore')) {
      return { action: 'exploreUI' };
    }
    if (currentAgent === 'testplan' && message.includes('parse')) {
      return { action: 'parseCSV' };
    }
    // ... more patterns
  }
  ```

#### Tree Views
- **Agents Tree:** Shows available agents and their capabilities
- **Tests Tree:** Displays generated test files

**Configuration Settings:**
```json
{
  "qaCopilot.apiUrl": "http://localhost:8000",
  "qaCopilot.deviceName": "127.0.0.1:6555",
  "qaCopilot.appPackage": "co.bizom.apps",
  "qaCopilot.appActivity": ".android.MainActivity",
  "qaCopilot.anthropicApiKey": "sk-ant-..."
}
```

---

### 2. FastAPI Server (Backend)

**Technology:** Python 3.14, FastAPI, Uvicorn

**Port:** 8000

**Key Endpoints:**

#### POST /api/parse-csv
- **Purpose:** Parse CSV test cases and generate test plan
- **Input:** 
  - `file`: CSV file (multipart/form-data)
  - `workspace_path`: Current workspace directory
- **Output:** Test plan markdown file
- **Agent:** TestPlanAgent

#### POST /api/explore-ui
- **Purpose:** Connect to emulator and extract UI elements
- **Input:**
  ```json
  {
    "device_name": "127.0.0.1:6555",
    "platform": "android",
    "app_package": "co.bizom.apps",
    "app_activity": ".android.MainActivity"
  }
  ```
- **Output:** UI elements with locators (resource IDs, XPaths, accessibility IDs)
- **Agent:** UIExplorerAgent

#### POST /api/analyze
- **Purpose:** Analyze codebase for screens and locators
- **Input:** `repo_path`
- **Output:** Extracted screens and locators from code
- **Agent:** CodebaseExplorerAgent

#### POST /api/generate-tests
- **Purpose:** Generate test code from test plan and locators
- **Input:** Test cases and platform
- **Output:** Generated test files
- **Agent:** TestGeneratorAgent

---

### 3. Agent System

#### Test Plan Agent
**File:** `agents/test_plan_agent.py`

**Responsibilities:**
- Parse CSV files (QA Touch format)
- Group test cases by feature
- Generate structured test plan in Markdown
- Create files in user's workspace

**CSV Format:**
```csv
Test ID, Feature, Test Case Name, Steps, Expected Result, Priority, Platform
TC001, Login, Valid Login, "1. Enter username\n2. Enter password\n3. Click Login", User logged in, High, Android
```

**Output:** `test_plans/test_plan.md`

---

#### UI Explorer Agent
**File:** `agents/ui_explorer_agent.py`

**Responsibilities:**
- Connect to Android emulator via Appium
- Launch specified app (if app_package provided)
- Extract UI elements from current screen
- Generate multiple locator strategies
- Filter out useless elements (containers with no identifiers)
- Save elements to JSON file

**Connection Flow:**
1. Create Appium session with UiAutomator2Options
2. Set device name, app package, app activity
3. Connect to Appium server (localhost:4723)
4. Extract elements using XPath `//*`
5. Filter elements with useful identifiers
6. Generate locators (resource-id, xpath, accessibility-id, text)

**Element Structure:**
```json
{
  "id": "login_user_name",
  "type": "EditText",
  "text": null,
  "resource_id": "login_user_name",
  "xpath": "//*[@resource-id='login_user_name']",
  "accessibility_id": null,
  "bounds": "[50,429][520,495]",
  "clickable": true,
  "enabled": true
}
```

**Smart Filtering:**
- Skip elements with no resource_id, text, or accessibility_id
- Skip elements with "null" string values
- Skip generic containers (FrameLayout, LinearLayout without identifiers)
- Keep only actionable or identifiable elements

**Output:** `data/ui_elements_android.json`

---

#### Codebase Explorer Agent
**File:** `agents/codebase_explorer_agent.py`

**Responsibilities:**
- Scan repository for screen files
- Extract locators from code (Kotlin, Java, Swift)
- Identify UI patterns
- Map features to screens

**Output:** `data/feature_map.json`, `data/locators.json`

---

#### Test Generator Agent
**File:** `agents/test_generator_agent.py`

**Responsibilities:**
- Load UI elements from UI Explorer
- Map test steps to UI elements
- Generate Appium/Selenium test code
- Create test files in workspace

**Output:** `generated_tests/*.java` or `*.kt`

---

### 4. Appium Server

**Technology:** Node.js, Appium 3.4.2

**Port:** 4723

**Purpose:** WebDriver server for mobile automation

**Capabilities:**
- UiAutomator2 for Android
- Session management
- Element finding strategies
- App launching and control

**Installation:**
```bash
npm install -g appium
appium driver install uiautomator2
```

**Start:**
```bash
appium
```

---

### 5. Android Emulator

**Options:**
- Genymotion (recommended for demo)
- Android Studio AVD
- Physical device

**Connection:**
```bash
adb devices
# Output: 127.0.0.1:6555  device
```

**App Details:**
- Package: `co.bizom.apps`
- Main Activity: `.android.MainActivity`

---

## Data Flow

### Flow 1: UI Exploration

```
User types "explore the login page"
    ↓
Extension detects intent → exploreUI action
    ↓
Extension reads settings:
  - deviceName: 127.0.0.1:6555
  - appPackage: co.bizom.apps
  - appActivity: .android.MainActivity
    ↓
Extension sends POST to /api/explore-ui
    ↓
API calls UIExplorerAgent.explore_app()
    ↓
Agent creates Appium session:
  - Connects to localhost:4723
  - Launches co.bizom.apps
  - Navigates to MainActivity
    ↓
Agent extracts UI elements:
  - Finds all elements with XPath //*
  - Filters useful elements
  - Generates locators
    ↓
Agent saves to data/ui_elements_android.json
    ↓
API returns JSON response with elements
    ↓
Extension formats and displays results
    ↓
Extension opens JSON file in editor
```

### Flow 2: Test Plan Generation

```
User clicks 📎 Attach button
    ↓
Extension opens file picker
    ↓
User selects CSV file
    ↓
Extension reads workspace path
    ↓
Extension sends POST to /api/parse-csv
  - file: CSV content (multipart)
  - workspace_path: /path/to/workspace
    ↓
API saves CSV to workspace/uploads/
    ↓
API calls TestPlanAgent.parse_csv()
    ↓
Agent parses CSV:
  - Reads test cases
  - Groups by feature
  - Validates data
    ↓
Agent generates test plan:
  - Creates workspace/test_plans/test_plan.md
  - Formats as Markdown
  - Includes summary
    ↓
API returns response with file path
    ↓
Extension opens test plan in editor
```

---

## Technology Stack

### Frontend (Extension)
- **Language:** TypeScript 5.9
- **Framework:** VS Code Extension API
- **UI:** Webview (HTML/CSS/JavaScript)
- **HTTP Client:** Axios
- **AI Integration:** Claude API (Anthropic)

### Backend (API Server)
- **Language:** Python 3.14
- **Framework:** FastAPI
- **Server:** Uvicorn (ASGI)
- **Mobile Automation:** Appium Python Client 3.1.0
- **WebDriver:** Selenium 4.44.0

### Mobile Automation
- **Server:** Appium 3.4.2 (Node.js)
- **Driver:** UiAutomator2 (Android)
- **Protocol:** WebDriver W3C

### Infrastructure
- **Emulator:** Genymotion / Android Studio AVD
- **ADB:** Android Debug Bridge
- **Device:** Android (API 28+)

---

## File Structure

```
QaCoPilot/
├── vscode-extension/          # VS Code Extension
│   ├── src/
│   │   ├── extension.ts       # Main extension entry
│   │   ├── chatViewProvider.ts # Chat interface
│   │   ├── agentsTreeProvider.ts
│   │   └── testsTreeProvider.ts
│   ├── package.json           # Extension manifest
│   └── tsconfig.json
│
├── agents/                    # Python Agents
│   ├── test_plan_agent.py
│   ├── ui_explorer_agent.py
│   ├── codebase_explorer_agent.py
│   └── test_generator_agent.py
│
├── api_server.py              # FastAPI Server
├── venv/                      # Python Virtual Environment
├── data/                      # Generated Data
│   ├── ui_elements_android.json
│   ├── locators.json
│   └── feature_map.json
│
├── test_plans/                # Generated Test Plans
├── generated_tests/           # Generated Test Code
├── uploads/                   # Uploaded CSV Files
│
├── DEMO_PRESENTATION.md       # Demo Guide
├── ARCHITECTURE.md            # This File
└── README.md                  # Project Overview
```

---

## Configuration

### VS Code Settings
Location: `~/Library/Application Support/Code/User/settings.json`

```json
{
  "qaCopilot.apiUrl": "http://localhost:8000",
  "qaCopilot.deviceName": "127.0.0.1:6555",
  "qaCopilot.appPackage": "co.bizom.apps",
  "qaCopilot.appActivity": ".android.MainActivity",
  "qaCopilot.anthropicApiKey": "sk-ant-api03-..."
}
```

### Environment Variables
File: `.env`

```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
APPIUM_SERVER_URL=http://localhost:4723
API_SERVER_PORT=8000
```

---

## Deployment

### Development Setup

1. **Install Dependencies:**
   ```bash
   # Python dependencies
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Extension dependencies
   cd vscode-extension
   npm install
   ```

2. **Start Services:**
   ```bash
   # Terminal 1: Appium
   appium
   
   # Terminal 2: API Server
   source venv/bin/activate
   python api_server.py
   
   # Terminal 3: Connect Device
   adb connect 127.0.0.1:6555
   ```

3. **Install Extension:**
   ```bash
   cd vscode-extension
   npm run compile
   npx vsce package
   code --install-extension qa-copilot-1.0.0.vsix --force
   ```

### Production Deployment

**API Server:**
- Deploy to AWS/GCP/Azure
- Use Docker container
- Configure HTTPS
- Set up load balancer

**Appium Server:**
- Deploy on dedicated server
- Use Appium Grid for multiple devices
- Configure cloud device providers (BrowserStack, Sauce Labs)

**Extension:**
- Publish to VS Code Marketplace
- Configure remote API URL
- Handle authentication

---

## Security Considerations

1. **API Key Storage:** Store Anthropic API key in VS Code settings (encrypted)
2. **API Authentication:** Add JWT tokens for API endpoints
3. **Device Access:** Restrict Appium server to localhost or VPN
4. **File Uploads:** Validate CSV files, limit size
5. **Code Injection:** Sanitize user inputs in prompts

---

## Performance Optimization

1. **Session Reuse:** Reuse Appium sessions when possible
2. **Caching:** Cache UI elements for repeated queries
3. **Parallel Processing:** Process multiple test cases concurrently
4. **Lazy Loading:** Load tree views on demand
5. **Debouncing:** Debounce chat input to reduce API calls

---

## Error Handling

### Extension Level
- Connection timeout to API server
- Invalid file uploads
- Missing configuration

### API Level
- Appium connection failures
- Device not found
- App launch failures
- Session expired

### Agent Level
- CSV parsing errors
- Element not found
- Invalid locators
- File write permissions

---

## Monitoring & Logging

### API Server Logs
```python
INFO:     127.0.0.1:63393 - "POST /api/explore-ui HTTP/1.1" 200 OK
✅ UI elements saved: data/ui_elements_android.json
```

### Appium Logs
```
[Appium] Welcome to Appium v3.4.2
[Appium] Appium REST http interface listener started on 0.0.0.0:4723
```

### Extension Logs
- VS Code Developer Console
- Output Channel: "QA Copilot"

---

## Future Enhancements

1. **Action Automation:** Type text, click buttons, navigate screens
2. **Multi-Screen Exploration:** Navigate through app flows
3. **iOS Support:** Add XCUITest driver
4. **Visual Testing:** Screenshot comparison
5. **Test Execution:** Run generated tests
6. **CI/CD Integration:** GitHub Actions, Jenkins
7. **Cloud Devices:** BrowserStack, Sauce Labs integration
8. **Test Reports:** Generate HTML reports with screenshots

---

## Troubleshooting

### Extension Not Visible
- Check: `code --list-extensions | grep qa-copilot`
- Fix: Reinstall extension

### API Connection Failed
- Check: `curl http://localhost:8000/health`
- Fix: Restart API server

### Appium Not Responding
- Check: `curl http://localhost:4723/status`
- Fix: Restart Appium server

### Device Not Found
- Check: `adb devices`
- Fix: Reconnect device: `adb connect 127.0.0.1:6555`

### App Not Launching
- Check: Package name and activity are correct
- Fix: Test manually: `adb shell am start -n co.bizom.apps/.android.MainActivity`

---

## License

MIT License

---

## Contributors

Built for Hackathon Demo
Powered by Claude, Appium, and FastAPI
