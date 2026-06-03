# QA Copilot - Complete System Flow

## 🎯 Phase 2: Test Plan Execution with Locator Collection

---

## 📊 Visual Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER (in IntelliJ)                          │
│  Types: "explore the ui based on the test plan and get locators"  │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    IntelliJ Plugin UI                               │
│  • Detects [TEST_PLAN: /path/to/file.md] in metadata              │
│  • Adds hidden config: device, app_package, workspace_path         │
│  • Sends to: POST /api/navigate-ui                                 │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    API Server (api_server.py)                       │
│  @app.post("/api/navigate-ui")                                      │
│  • Receives command + metadata                                      │
│  • Detects keywords: "test plan", "test case"                      │
│  • Routes to: ui_explorer.navigate_based_on_intent()               │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│               UI Explorer Agent (ui_explorer_agent.py)              │
│  navigate_based_on_intent() method:                                 │
│  • Detects test plan keywords                                       │
│  • Extracts test plan path from metadata                           │
│  • Calls: execute_test_plan()                                       │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      execute_test_plan()                            │
│  1. Parse test plan markdown                                        │
│  2. Connect to device via Appium                                    │
│  3. Initialize SINGLE locator collection                            │
│  4. Loop through all test cases                                     │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────┴──────────────────────┐
        │   FOR EACH TEST CASE (TC1 to TC10)        │
        └────────────────────┬──────────────────────┘
                             │
                    ┌────────┴────────┐
                    │  Parse test case │
                    │  Extract steps   │
                    └────────┬─────────┘
                             │
        ┌────────────────────┴──────────────────────┐
        │   FOR EACH STEP in current test case      │
        └────────────────────┬──────────────────────┘
                             │
                    ┌────────┴─────────┐
                    │ Explore screen    │
                    │ Get ALL elements  │
                    │ (50-100 elements) │
                    └────────┬──────────┘
                             │
        ┌────────────────────┴────────────────────────────────┐
        │  FOR EACH ELEMENT on screen:                        │
        │  • Create unique ID (resource_id > text > content)  │
        │  • Check if ID in self.locator_ids set             │
        │  • If NEW: Add to collection + add ID to set        │
        │  • If DUPLICATE: Skip silently                      │
        └────────────────────┬────────────────────────────────┘
                             │
                    ┌────────┴─────────┐
                    │ Execute step      │
                    │ (click, enter)    │
                    └────────┬──────────┘
                             │
                             ▼
        ┌─────────────────────────────────────────┐
        │   Continue to next step/test case       │
        │   Accumulated locators: 0→81→86→...→150│
        └─────────────────────┬───────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 _save_locators_to_workspace()                       │
│  • Create: {workspace}/locators/                                    │
│  • Generate ONE file: TestPlan_{name}_{timestamp}_locators.txt     │
│  • Write all 150 unique locators with full metadata                │
│  • Include test case source for each locator                        │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Return Response                              │
│  {                                                                  │
│    "success": true,                                                 │
│    "steps_executed": 10,                                            │
│    "locators_collected": 150,                                       │
│    "locators_file": "/path/to/file.txt"                            │
│  }                                                                  │
└────────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    IntelliJ Plugin Display                          │
│  ✅ Navigation Complete!                                            │
│    Steps Executed: 10                                               │
│    Locators Collected: 150                                          │
│    Saved to: /Users/anjana.mohan/KMMAuto_demo/locators/...txt     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Implementation Details

### 1. Test Plan Parsing (`_parse_test_plan()`)

**Input**: Markdown file with format:
```markdown
#### TC8508: Verify agent appears in the PJP list
**Priority**: P1
**Preconditions**:
- User is logged in
**Steps**:
1. Open Bizom application
2. Navigate to PJP screen
3. View agent list
**Expected Results**:
- Agent appears in list
```

**Output**: Structured dict:
```python
{
    'test_cases': [
        {
            'id': 'TC8508',
            'title': 'Verify agent appears...',
            'priority': 'P1',
            'preconditions': [...],
            'steps': ['Open Bizom...', 'Navigate to...'],
            'expected_results': [...]
        },
        # ... 9 more test cases
    ]
}
```

### 2. Screen Exploration (`explore_current_screen()`)

**What it does**:
- Uses Appium's `driver.find_elements("xpath", "//*")` to get ALL elements
- Extracts 10+ attributes per element:
  - resource_id
  - class/type
  - text
  - content_desc
  - clickable
  - enabled
  - focusable
  - bounds
  - xpath
  - accessibility_id

**Example output** (one element):
```python
{
    'id': 'login_button',
    'type': 'Button',
    'text': 'Login',
    'resource_id': 'co.bizom.apps:id/login_button',
    'xpath': "//*[@resource-id='co.bizom.apps:id/login_button']",
    'accessibility_id': 'Login Button',
    'content_desc': 'Login to account',
    'bounds': '[100,200][300,250]',
    'clickable': True,
    'enabled': True,
    'focusable': True
}
```

### 3. Deduplication Logic (`_add_locator()`)

**Deduplication Strategy**:
```python
# Create unique ID (priority order)
locator_id = (
    element.get('resource_id') or    # Most reliable
    element.get('text') or           # Second choice
    element.get('accessibility_id')  # Fallback
)

# Check if already collected
if locator_id in self.locator_ids:
    return False  # Skip duplicate
    
# Add to set for future deduplication
self.locator_ids.add(locator_id)

# Store in collection
self.collected_locators[locator_id] = {
    # ... all element attributes ...
    'test_case': 'TC8508',  # Which TC found this
    'step': 2,              # Which step
    'action': 'clicked'     # How it was used
}
```

**Example Deduplication**:
```
TC8508 Step 1: Found 81 elements → Add 81 locators (total: 81)
TC8508 Step 2: Found 79 elements → Add 5 new, skip 74 duplicates (total: 86)
TC8509 Step 1: Found 81 elements → Add 2 new, skip 79 duplicates (total: 88)
...
TC8517 Step 5: Found 45 elements → Add 1 new, skip 44 duplicates (total: 150)
```

### 4. Locator File Output (`_save_locators_to_workspace()`)

**File Structure**:
```
# UI Element Locators
# Source: TestPlan_test_plan_TestCases_27-05-26-14_09_48
# Generated: 2026-06-03 12:00:00
# Total Unique Elements: 150
# Deduplication: Applied across all test cases

================================================================================

1. login_button
   Element Type: Button
   Resource ID: co.bizom.apps:id/login_button
   XPath: //*[@resource-id='co.bizom.apps:id/login_button']
   Accessibility ID: Login Button
   Content Description: Login to account
   Text: Login
   Bounds: [100,200][300,250]
   Clickable: True
   Enabled: True
   Focusable: True
   Found in Test Case: TC8508
   Step: 1
   Usage: clicked

--------------------------------------------------------------------------------

2. hamburger_menu
   Element Type: ImageButton
   Resource ID: co.bizom.apps:id/hamburger_icon
   XPath: //*[@resource-id='co.bizom.apps:id/hamburger_icon']
   Clickable: True
   Enabled: True
   Focusable: False
   Found in Test Case: TC8508
   Step: 2
   Usage: available

... [148 more unique locators]
```

---

## 📈 Execution Statistics

### Expected Numbers:

| Metric | Old Value | New Value | Improvement |
|--------|-----------|-----------|-------------|
| Files Generated | 10 | 1 | 90% reduction |
| Locators Collected | 1-2 | 50-150 | 50-75x increase |
| Element Coverage | Clicked only | All visible | 100% coverage |
| Duplicates | Many | Zero | 100% deduplication |
| Metadata | Minimal | Comprehensive | Full context |

### Execution Time:
```
Test Plan Parsing:     2 seconds
Device Connection:     3 seconds
TC Execution (10):     4 minutes (24 sec/TC avg)
Locator Generation:    1 second
──────────────────────────────────
Total:                 ~5 minutes
```

### Locator Distribution (Expected):
```
TC8508 (8 steps):    81 new + 5 new = 86 total
TC8509 (6 steps):    2 new (84 duplicates skipped)
TC8510 (7 steps):    8 new (73 duplicates skipped)
TC8511 (5 steps):    12 new (69 duplicates skipped)
TC8512 (9 steps):    5 new (76 duplicates skipped)
TC8513 (4 steps):    15 new (66 duplicates skipped)
TC8514 (6 steps):    7 new (74 duplicates skipped)
TC8515 (8 steps):    3 new (78 duplicates skipped)
TC8516 (5 steps):    6 new (75 duplicates skipped)
TC8517 (7 steps):    5 new (76 duplicates skipped)
──────────────────────────────────────────────────
Total Unique:        150 locators
Total Duplicates:    671 skipped
Total Elements:      821 scanned
```

---

## 🎯 Success Validation Checklist

After execution, verify:

✅ **ONE file created**
```bash
ls -l /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt
# Should show exactly 1 file with recent timestamp
```

✅ **50-150 locators collected**
```bash
grep -c "^[0-9]\+\. " /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt
# Should output: 150 (or similar range)
```

✅ **Full metadata per locator**
```bash
head -30 /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt
# Should show:
# - Element Type
# - Resource ID
# - XPath
# - Accessibility ID
# - Text
# - Bounds
# - Clickable/Enabled/Focusable
# - Found in Test Case
# - Step
# - Usage
```

✅ **Test case context preserved**
```bash
grep "Found in Test Case:" /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt | head -5
# Should show different TC IDs (TC8508, TC8509, etc.)
```

✅ **No duplicate resource IDs**
```bash
grep "Resource ID:" /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt | sort | uniq -d
# Should output nothing (no duplicates)
```

---

## 🔧 Configuration Reference

### Hardcoded in Plugin (QACopilotPanel.java):
```java
DEVICE_NAME = "127.0.0.1:6555"
APP_PACKAGE = "co.bizom.apps"
APP_ACTIVITY = ".android.MainActivity"
WORKSPACE_PATH = "/Users/anjana.mohan/KMMAuto_demo"
```

### API Server Endpoint:
```
URL: http://localhost:8000/api/navigate-ui
Method: POST
Timeout: 300 seconds (5 minutes)
```

### Request Body:
```json
{
  "command": "explore the ui based on the test plan and get locators\n[TEST_PLAN: /path/to/test_plan.md]",
  "device_name": "127.0.0.1:6555",
  "app_package": "co.bizom.apps",
  "app_activity": ".android.MainActivity",
  "workspace_path": "/Users/anjana.mohan/KMMAuto_demo"
}
```

### Response Body:
```json
{
  "success": true,
  "steps_executed": 10,
  "locators_collected": 150,
  "locators_file": "/Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_test_plan_TestCases_27-05-26-14_09_48_20260603_120000_locators.txt",
  "test_cases_executed": 10,
  "total_test_cases": 10
}
```

---

## 🚀 Next Phase (After Successful Test)

### Phase 3: Test Code Generation

**Input**: Locator file with 150 elements

**Process**:
1. Load locators from file
2. Generate Page Object Model classes
3. Generate test methods for each test case
4. Support multiple languages (Java, Python, JavaScript)
5. Generate complete Appium test suite

**Output**: Ready-to-run test code
```java
@Test
public void testTC8508_VerifyAgentAppearsInPJPList() {
    // Auto-generated from locators
    driver.findElement(By.id("login_button")).click();
    driver.findElement(By.id("hamburger_menu")).click();
    // ... complete test implementation
}
```

---

## 📊 System Architecture Summary

```
Technology Stack:
├── Backend
│   ├── Python 3.10+
│   ├── FastAPI (API server)
│   ├── Appium Python Client (device automation)
│   └── Ollama (local AI for navigation)
├── Frontend
│   ├── Java 11+ (IntelliJ plugin)
│   ├── Swing UI (plugin interface)
│   └── OkHttp (API communication)
├── Automation
│   ├── Appium Server (device bridge)
│   ├── ADB (Android Debug Bridge)
│   └── UiAutomator2 (Android automation)
└── AI
    ├── Ollama (primary, local)
    └── Anthropic Claude (fallback, cloud)
```

---

## ✅ Current Status

- **Phase 1**: ✅ Complete (Infrastructure)
- **Phase 2**: ✅ Complete (Locator Collection) - **TESTING NOW**
- **Phase 3**: ⏳ Pending (Code Generation)
- **Phase 4**: ⏳ Pending (Finalization & Commit)

---

**Last Updated**: June 3, 2026 - 1:30 PM  
**Status**: Ready for Phase 2 Testing ✅  
**API Server**: Running (PID: 23040) ✅  
**Plugin**: Built ✅  
**Next Action**: Execute test from IntelliJ 🚀
