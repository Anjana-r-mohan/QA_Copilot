# QA Copilot - AI-Powered Mobile Test Automation

Intelligent test automation system that executes test plans, navigates mobile apps, and collects UI locators automatically using AI.

## 🎯 Features

- **Test Plan Execution**: Automatically parse and execute test cases from markdown test plans
- **AI-Powered Navigation**: Uses Ollama (local AI) to understand test steps and navigate apps
- **Locator Collection**: Automatically collects and saves UI element locators during execution
- **Real Device Automation**: Works with real Android devices via Appium
- **IntelliJ Plugin**: Clean, professional IDE integration for easy interaction

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    IntelliJ Plugin                      │
│  (Clean UI: File Pickers + Chat Interface)             │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   FastAPI Server                        │
│              (api_server.py)                            │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │Test Plan │  │UI Explorer│  │Code Gen  │
  │  Agent   │  │   Agent   │  │  Agent   │
  └──────────┘  └──────────┘  └──────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  Appium Server  │
              │   (Port 4723)   │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ Android Device  │
              │ (127.0.0.1:6555)│
              └─────────────────┘
```

## 📋 Prerequisites

- **Python 3.10+**
- **Java 11+** (for IntelliJ plugin)
- **Gradle** (for building IntelliJ plugin)
- **Appium Server** (running on port 4723)
- **Android Device** connected via ADB
- **Ollama** (for local AI - optional, falls back to Anthropic)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```
ANTHROPIC_API_KEY=your_key_here  # Optional
OLLAMA_URL=http://localhost:11434  # Local AI
```

### 3. Start Appium Server

```bash
appium
```

### 4. Connect Android Device

```bash
adb devices
# Should show: 127.0.0.1:6555 device
```

### 5. Start API Server

```bash
python3 api_server.py
```

Server starts at: `http://localhost:8000`

### 6. Install IntelliJ Plugin

1. Build plugin:
   ```bash
   cd intellij-plugin
   gradle clean build
   ```

2. Install in IntelliJ:
   - File → Settings → Plugins → ⚙️ → Install Plugin from Disk
   - Select: `intellij-plugin/build/distributions/qa-copilot-intellij.zip`
   - Restart IntelliJ

### 7. Use the Plugin

1. Open QA Copilot panel in IntelliJ
2. (Optional) Click 📋 to select test plan file
3. Type command: `"explore the ui based on the test plan and get locators"`
4. Press Send
5. Watch execution in real-time

## 📂 Project Structure

```
QaCoPilot/
├── agents/                       # AI agents
│   ├── test_plan_agent.py       # Parses CSV → Markdown test plans
│   ├── ui_explorer_agent.py     # Executes tests & collects locators
│   └── code_generator_agent.py  # Generates test code (future)
├── intellij-plugin/             # IntelliJ IDEA plugin
│   ├── src/main/java/           # Java source code
│   └── build.gradle.kts         # Build configuration
├── api_server.py                # FastAPI backend server
├── config.py                    # Configuration management
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
└── README.md                    # This file
```

## 🎮 Usage Examples

### Execute Test Plan

In IntelliJ plugin:

```
explore the ui based on the test plan and get locators
```

System will:
1. Detect test plan file in workspace
2. Parse all test cases
3. Execute each test case step-by-step
4. Collect locators for every UI element
5. Generate locator files per test case

### Free-Form Navigation

```
explore the current page and do start call and get locators
```

System will:
1. Use AI to understand command
2. Navigate app based on intent
3. Collect locators along the way
4. Save to file

## 🔧 Configuration

### Device Settings

Hardcoded in plugin (`QACopilotPanel.java`):
```java
private static final String DEVICE_NAME = "127.0.0.1:6555";
private static final String APP_PACKAGE = "co.bizom.apps";
private static final String APP_ACTIVITY = ".android.MainActivity";
private static final String WORKSPACE_PATH = "/Users/anjana.mohan/KMMAuto_demo";
```

To change, edit these constants and rebuild plugin.

### AI Backend

The system tries backends in this order:
1. **Ollama** (local, free, unlimited) - Primary
2. **Anthropic Claude** (cloud, paid) - Fallback

## 📊 Output

### Locator Files

Generated in: `{WORKSPACE}/locators/`

Format:
```
# Locators from: TC8508_Verify_that_the_agent_appears...
# Generated: 2026-06-03 12:08:07
# Total unique locators: 2

1. login_button
   Resource ID: login_button
   XPath: //*[@resource-id='login_button']
   Clickable: True
   Step used: 1
   Action: click

2. hamburger_menu
   Resource ID: hamburger_icon
   XPath: //*[@resource-id='hamburger_icon']
   Clickable: True
   Step used: 2
   Action: click
```

### API Response

```json
{
  "success": true,
  "steps_executed": 10,
  "locators_collected": 25,
  "locators_file": "/path/to/locators/TC8508_...txt",
  "test_cases_executed": 10,
  "total_test_cases": 10
}
```

## 🐛 Troubleshooting

### Server Not Starting

```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process
kill -9 <PID>

# Restart server
python3 api_server.py
```

### Device Not Connected

```bash
# Check ADB devices
adb devices

# Reconnect device
adb connect 127.0.0.1:6555
```

### Plugin Not Working

1. Check API server is running: `curl http://localhost:8000/health`
2. Check Appium is running: `lsof -i :4723`
3. Check device connected: `adb devices`
4. View logs: `tail -f /tmp/api_server.log`

### No Locators Collected

- Ensure device screen is visible and not locked
- Check Appium can access UI elements
- Verify app is running on device
- Check logs for errors

## 📝 API Endpoints

### POST `/api/navigate-ui`

Execute navigation or test plan.

**Request:**
```json
{
  "command": "explore the test plan",
  "device_name": "127.0.0.1:6555",
  "app_package": "co.bizom.apps",
  "app_activity": ".android.MainActivity",
  "workspace_path": "/path/to/workspace"
}
```

**Response:**
```json
{
  "success": true,
  "steps_executed": 10,
  "locators_collected": 25,
  "locators_file": "/path/to/file.txt"
}
```

### GET `/health`

Check server health.

**Response:**
```json
{
  "status": "healthy"
}
```

## 🔐 Security Notes

- API key stored in `.env` (not committed to git)
- Local AI (Ollama) preferred for privacy
- Device connection only to localhost
- No data sent to external services

## 📈 Roadmap

- [x] Test plan parsing
- [x] Step-by-step execution
- [x] AI-powered navigation
- [x] Locator collection
- [x] IntelliJ plugin
- [ ] Test code generation
- [ ] Multiple language support (Java, Python, JavaScript)
- [ ] CI/CD integration
- [ ] Report generation

## 🤝 Contributing

This is a private project. For questions, contact the development team.

## 📄 License

Proprietary - All rights reserved

---

**Status**: Production Ready ✅
**Version**: 1.0.0
**Last Updated**: June 3, 2026
