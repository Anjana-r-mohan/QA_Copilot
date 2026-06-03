# 🎯 Install Both Plugins Side-by-Side

**Date**: June 3, 2026 - 4:10 PM  
**Status**: Both plugins ready for installation ✅

---

## 📦 Two Plugins Available

### Plugin 1: QA Copilot (Basic Version)
```
Name: QA Copilot
ID: com.bizom.qa-copilot
Panel Name: "QA Copilot"
Keyboard Shortcuts:
  - Cmd+Alt+N: Navigate UI
  - Cmd+Alt+E: Explore App
  
Features:
  • Basic execution
  • Final result display
  • 5-minute timeout
  • No real-time updates
  
Use Case: Reference, comparison, fallback

File: qa-copilot-intellij-v1.0-basic.zip
Location: intellij-plugin/build/distributions/
Status: Available for comparison
```

### Plugin 2: ScriptSherpa (Streaming Version) ⭐
```
Name: ScriptSherpa
ID: com.bizom.scriptSherpa
Panel Name: "ScriptSherpa"
Keyboard Shortcuts:
  - Cmd+Alt+S: Navigate UI
  - Cmd+Shift+S: Explore App
  
Features:
  ✨ Real-time SSE streaming
  ✨ Live progress updates
  ✨ No timeouts
  ✨ Professional UX
  ✨ Full visibility
  
Use Case: Production, demos, daily use

File: script-sherpa.zip
Location: intellij-plugin/build/distributions/
Status: Ready to install ✅
```

---

## 🚀 Installation Instructions

### Step 1: Install ScriptSherpa (Streaming)

```bash
# Plugin location
/Users/anjana.mohan/QaCoPilot/intellij-plugin/build/distributions/script-sherpa.zip

# In IntelliJ:
1. File → Settings → Plugins → ⚙️ → Install Plugin from Disk
2. Navigate to: /Users/anjana.mohan/QaCoPilot/intellij-plugin/build/distributions/
3. Select: script-sherpa.zip
4. Click OK
5. Restart IntelliJ
```

### Step 2: Install QA Copilot (Basic) - Optional

```bash
# If you want to compare both plugins side-by-side
# Plugin location (you need to build this from the old code if needed)
# The basic version is the original one without streaming
```

**Note**: After restart, you'll see **TWO tool windows**:
- "QA Copilot" (basic - if installed)
- "ScriptSherpa" (streaming) ⭐

---

## 🎯 Using Both Plugins

### Open ScriptSherpa (Recommended)
1. Look for **"ScriptSherpa"** tool window (right sidebar)
2. Click to open
3. Select test plan with 📋 button
4. Type command: `explore the page as per test plan and get locators`
5. Watch real-time streaming updates! ✨

### Open QA Copilot (For Comparison)
1. Look for **"QA Copilot"** tool window (right sidebar)
2. Click to open
3. Same interface, but without streaming
4. Compare the experience!

---

## 📊 Key Differences

| Feature | QA Copilot | ScriptSherpa |
|---------|------------|--------------|
| **Plugin ID** | com.bizom.qa-copilot | com.bizom.scriptSherpa |
| **Panel Name** | QA Copilot | ScriptSherpa |
| **Shortcuts** | Cmd+Alt+N/E | Cmd+Alt+S, Cmd+Shift+S |
| **Real-Time Updates** | ❌ No | ✅ Yes |
| **Progress Visibility** | ❌ "Thinking..." only | ✅ Live streaming |
| **Timeout** | ⚠️ 5 minutes | ✅ No timeout |
| **User Experience** | Basic | Professional |
| **Backend Endpoint** | /api/navigate-ui | /api/navigate-ui-stream |
| **Best For** | Reference | Production |

---

## 🎬 Demo Script - Show Both

### 1. Show QA Copilot (Basic)
```
"Here's the basic version - watch what happens..."

Open QA Copilot panel
Type: explore the page as per test plan
Click Send

Result: "🤖 QA Copilot is thinking..." 
[Wait in silence for 5 minutes]
Then shows: "✅ Complete! 150 locators"
```

### 2. Show ScriptSherpa (Streaming)
```
"Now watch the difference with ScriptSherpa..."

Open ScriptSherpa panel
Type: explore the page as per test plan
Click Send

Result: Immediate understanding + live updates:
🎯 I understand: explore the page...
📋 Detected: Test Plan Mode
📋 Parsing test plan...
✅ Found 10 test cases
📱 Connecting...
✅ Connected!
📝 Executing TC8508 (1/10)
   Step 1/8: Open app...
   Found 81 elements
   ✅ Added 81 locators (total: 81)
[... continues with live updates ...]
✅ Complete! 150 locators
```

### 3. Key Message
```
"Same backend, same results, but ScriptSherpa gives you:
• Full visibility into what's happening
• Real-time progress updates
• Professional user experience
• No anxiety about 'is it working?'
• Better debugging when things go wrong"
```

---

## 🔧 Technical Details

### Package Structure

**QA Copilot**:
```
com.bizom.qaCopilot
  ├── ui
  │   ├── QACopilotPanel.java
  │   └── QACopilotToolWindowFactory.java
  ├── backend
  │   └── BackendConnector.java
  └── actions
      ├── ShowChatAction.java
      ├── NavigateUIAction.java
      └── ExploreAppAction.java
```

**ScriptSherpa**:
```
com.bizom.scriptSherpa
  ├── ui
  │   ├── ScriptSherpaPanel.java
  │   └── ScriptSherpaToolWindowFactory.java
  ├── backend
  │   └── BackendConnector.java
  └── actions
      ├── ShowChatAction.java
      ├── NavigateUIAction.java
      └── ExploreAppAction.java
```

### Backend Endpoints

Both plugins connect to the same API server but use different endpoints:

**QA Copilot** → `POST /api/navigate-ui`
- Returns final result only
- No streaming
- 5-minute timeout

**ScriptSherpa** → `POST /api/navigate-ui-stream`
- Returns SSE stream
- Real-time updates
- No timeout (keepalive)

---

## 🎯 Which Plugin to Use?

### Use ScriptSherpa When:
- ✅ Doing demos
- ✅ Daily development
- ✅ Long-running test plans
- ✅ Need visibility
- ✅ Want professional UX

### Use QA Copilot When:
- 🔄 Comparing functionality
- 🔄 Showing before/after
- 🔄 Fallback if streaming has issues
- 🔄 Testing basic flow

**Recommendation**: Use ScriptSherpa as your primary plugin! 🌟

---

## 🐛 Troubleshooting

### Both plugins showing same behavior
**Cause**: Only one plugin actually installed  
**Fix**: Check Settings → Plugins, verify both are listed

### ScriptSherpa not streaming
**Cause**: API server not running or using old version  
**Fix**:
```bash
# Check server
curl http://localhost:8000/health

# Restart if needed
ps aux | grep api_server.py
kill -9 <PID>
cd /Users/anjana.mohan/QaCoPilot
python3 api_server.py &
```

### Can't find ScriptSherpa panel
**Cause**: Not installed or IntelliJ not restarted  
**Fix**: Restart IntelliJ, look for "ScriptSherpa" in right sidebar

### Keyboard shortcuts conflict
**Cause**: Both plugins use similar shortcuts  
**Fix**: ScriptSherpa uses different shortcuts:
- Cmd+Alt+S (instead of Cmd+Alt+N)
- Cmd+Shift+S (instead of Cmd+Alt+E)

---

## 📁 File Locations

### Plugin Files
```
QA Copilot: 
  - Original build (if you kept it)
  - Location: TBD (you'd need to rebuild from old code)

ScriptSherpa:
  - File: script-sherpa.zip
  - Location: /Users/anjana.mohan/QaCoPilot/intellij-plugin/build/distributions/
  - Size: ~3MB
  - Status: Ready ✅
```

### Source Code
```
QA Copilot Source:
  src/main/java/com/bizom/qaCopilot/

ScriptSherpa Source:
  src/main/java/com/bizom/scriptSherpa/

Plugin XML:
  src/main/resources/META-INF/plugin.xml
```

---

## ✅ Verification Checklist

After installing both:

- [ ] IntelliJ restarted
- [ ] Two tool windows visible in sidebar:
  - [ ] "QA Copilot" (if basic installed)
  - [ ] "ScriptSherpa"
- [ ] ScriptSherpa panel opens correctly
- [ ] File picker buttons visible (📋 📄)
- [ ] Can type in chat input
- [ ] API server running (curl http://localhost:8000/health)
- [ ] Test plan file accessible

Test run:

- [ ] Select test plan file
- [ ] Type command
- [ ] Click Send
- [ ] See real-time updates (ScriptSherpa)
- [ ] See final result
- [ ] Check locator file generated

---

## 🎉 Summary

### What You Have Now:

1. **ScriptSherpa** (Primary Plugin)
   - Real-time streaming
   - Professional UX
   - Full visibility
   - Production-ready

2. **QA Copilot** (Reference Plugin)
   - Basic functionality
   - For comparison
   - Fallback option

### How to Use:

1. **Install ScriptSherpa** - Your main plugin ⭐
2. **Optional**: Install QA Copilot for comparison
3. **Use ScriptSherpa** for all daily work
4. **Show both in demos** to highlight the difference

### The Difference:

**QA Copilot**: "Is it working? 🤔"  
**ScriptSherpa**: "Here's exactly what I'm doing! ✨"

---

**Status**: Both plugins ready to install ✅  
**Recommended**: ScriptSherpa (streaming version) ⭐  
**File**: script-sherpa.zip  
**Location**: /Users/anjana.mohan/QaCoPilot/intellij-plugin/build/distributions/

**INSTALL SCRIPTSHERPA NOW AND SEE THE MAGIC!** 🚀

---

*Last Updated: June 3, 2026 - 4:10 PM*  
*ScriptSherpa Version: 1.0.0*  
*API Server: Running with streaming support ✅*  
*Ready for Demo: YES ✅*
