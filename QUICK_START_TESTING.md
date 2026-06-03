# 🚀 Quick Start - Test Phase 2 NOW

## ⚡ TL;DR - Do This Now:

### 1. Verify Everything is Ready
```bash
# Check API server is running (should see "healthy")
curl http://localhost:8000/health

# Check device connected (should see 127.0.0.1:6555)
adb devices

# Check Appium running (should see process)
lsof -i :4723
```

**ALL CHECKED? ✅ Continue below!**

---

### 2. Open IntelliJ Plugin

1. **Find** "QA Copilot" in IntelliJ tool windows (right sidebar)
2. **Click** to open the panel

You should see:
```
┌─────────────────────────────────────────┐
│ 📋 Test Plan    📄 CSV                  │
│ 📌 No files selected                    │
├─────────────────────────────────────────┤
│                                         │
│ 👋 Welcome to QA Copilot!              │
│                                         │
│ Click 📋 or 📄 to select context       │
│ files, then type your command.         │
│                                         │
├─────────────────────────────────────────┤
│ [Type your message here...]             │
│                                         │
│                               [Send]    │
└─────────────────────────────────────────┘
```

---

### 3. Select Test Plan File

1. **Click** 📋 Test Plan button
2. **Navigate** to: `/Users/anjana.mohan/KMMAuto_demo/test_plans/`
3. **Select**: `test_plan_TestCases_27-05-26-14_09_48.md`
4. **Verify** label updates to show filename

---

### 4. Execute Test Plan

**Type this EXACT command:**
```
explore the ui based on the test plan and get locators
```

**Click** Send

---

### 5. Monitor Progress

**In IntelliJ:**
- Shows: "🤖 QA Copilot is thinking..."
- Wait 2-5 minutes for execution

**In separate terminal, watch API logs:**
```bash
# Open new terminal and run:
tail -f /dev/tty
```

You should see:
```
📋 Parsing test plan: ...
✅ Found 10 test cases

📱 Connecting to device: 127.0.0.1:6555
✅ Connected to 127.0.0.1:6555

Executing TC8508: Verify agent appears...
   Found 81 UI elements on screen
   ✅ Added 81 new unique locators (total: 81)

... [more progress]

✅ Test Plan Execution Complete!
Total Unique Locators Collected: 150
```

---

### 6. Verify Success

**Expected plugin response:**
```
✅ Navigation Complete!
  Steps Executed: 10
  Locators Collected: 150
  Saved to: /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_...txt
```

**Check file was created:**
```bash
ls -lh /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt
```

**View the file:**
```bash
# Should show 50-150 unique locators with full metadata
head -100 /Users/anjana.mohan/KMMAuto_demo/locators/TestPlan_*.txt
```

---

## ✅ Success Criteria

You'll know it worked if:

- ✅ **ONE file** created (not 10 separate files)
- ✅ **50-150 locators** in file (not 1-2)
- ✅ **No duplicates** across test cases
- ✅ **Metadata included** for each locator
- ✅ **Test case source** tracked

---

## 🆘 Quick Fixes

### Problem: API server not responding
```bash
# Restart server
ps aux | grep api_server.py
kill -9 <PID>
cd /Users/anjana.mohan/QaCoPilot
python3 api_server.py &
```

### Problem: Device not found
```bash
# Reconnect device
adb disconnect
adb connect 127.0.0.1:6555
adb devices
```

### Problem: Plugin shows error
1. Check API server: `curl http://localhost:8000/health`
2. Check device: `adb devices`
3. Check Appium: `lsof -i :4723`
4. Try again with same command

### Problem: Still only 1-2 locators
**This means:**
- ❌ Old code is running (server needs restart)
- ❌ Device screen is locked
- ❌ App is not visible

**Fix:**
```bash
# 1. Restart API server
kill -9 $(lsof -t -i:8000)
cd /Users/anjana.mohan/QaCoPilot
python3 api_server.py &

# 2. Unlock device and open app

# 3. Try again
```

---

## 🎯 What You're Testing

### OLD BEHAVIOR (before updates):
- ❌ Generated 10 separate files (one per test case)
- ❌ Only 1-2 locators (just clicked elements)
- ❌ Duplicates across files
- ❌ No metadata

### NEW BEHAVIOR (after updates):
- ✅ Generates ONE file for entire test plan
- ✅ 50-150 locators (ALL elements on every screen)
- ✅ Deduplication (unique elements only)
- ✅ Full metadata (test case, step, type, xpath, etc.)

---

## 📊 Expected Timeline

- **Step 1-3**: 1 minute (setup)
- **Step 4**: 2-5 minutes (execution)
- **Step 5-6**: 1 minute (verification)

**Total**: ~5-7 minutes end-to-end

---

## 🎉 If It Works

This proves:
1. ✅ Test plan parsing working
2. ✅ Device automation working
3. ✅ AI navigation working
4. ✅ Locator collection working
5. ✅ Deduplication working
6. ✅ Plugin-to-backend communication working

**THEN**: We're 90% done! Next phase is code generation from these locators.

---

## 📞 Need Help?

**Check logs:**
```bash
# API server logs
tail -f /tmp/api_server.log

# System logs
tail -f /var/log/system.log
```

**Check status:**
```bash
# All components
curl http://localhost:8000/health  # API
adb devices                         # Device
lsof -i :4723                       # Appium
```

---

**READY TO TEST?** 🚀

1. Open IntelliJ
2. Open QA Copilot panel
3. Click 📋, select test plan
4. Type: "explore the ui based on the test plan and get locators"
5. Click Send
6. Wait ~5 minutes
7. Check results! 🎯

---

*Last Updated: June 3, 2026*  
*Status: READY FOR TESTING ✅*
