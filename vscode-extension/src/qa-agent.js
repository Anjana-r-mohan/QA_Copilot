const { randomUUID } = require('crypto');
const { McpClient } = require('./mcp-client');
const { GeminiClient } = require('./gemini-client');
const { BackendClient } = require('./backend-client');

/**
 * QA Agent - merged brain combining:
 * - Java Appium MCP Server (18 device interaction tools via stdio)
 * - QaCoPilot Python Backend (test plans, codebase analysis, code generation via HTTP)
 * - Gemini LLM (intent detection, planning, code generation)
 *
 * Flow: User message → Intent detection → Route to MCP or Backend → Response
 */
class QaAgent {
    constructor() {
        this.mcp = new McpClient();
        this.gemini = new GeminiClient(process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || '');
        this.backend = new BackendClient();
        this.history = [];
        this.actionHistory = [];
        this.lastSnapshot = '';
        this.connected = false;
        this.backendAvailable = false;
        this.sessionId = randomUUID();
        this.onLog = null;
    }

    /**
     * Initialize: start Java MCP server + check Python backend.
     */
    async initialize(config) {
        this.gemini.setApiKey(config.geminiApiKey || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || '');
        this.gemini.setBackendUrl(config.backendUrl || 'http://localhost:8000');

        this.backend.setBaseUrl(config.backendUrl || 'http://localhost:8000');

        // Start Java MCP server
        const jarPath = this.mcp.findServerJar(config.serverJar);
        if (!jarPath) {
            throw new Error(
                'Appium MCP server JAR not found. Build with `mvn clean package` or set qaAgent.serverJar in settings.'
            );
        }

        this._log(`Starting MCP server: ${jarPath}`);
        const result = await this.mcp.start(config.javaPath || 'java', jarPath);
        this._log(`MCP server ready. ${result.tools.length} tools available.`);

        this.mcp.on('log', (msg) => this._log(`[MCP] ${msg}`));
        this.mcp.on('disconnected', () => {
            this.connected = false;
            this._log('MCP server disconnected');
        });

        // Check Python backend
        this.backendAvailable = await this.backend.isAvailable();
        if (this.backendAvailable) {
            this._log('Python backend connected (test plans, codebase analysis available)');
        } else {
            this._log('Python backend not running — device tools still available via MCP');
        }

        return result;
    }

    /**
     * Process a user message — main entry point.
     */
    async processMessage(userMessage, config, progressCallback) {
        const progress = (type, message, data) => {
            if (progressCallback) progressCallback(type, message, data);
        };

        this.history.push({ role: 'user', content: userMessage });

        this.backend.setBaseUrl(config.backendUrl || 'http://localhost:8000');
        this.backendAvailable = await this.backend.isAvailable();

        let intent = this._detectIntentHeuristic(userMessage);
        if (this._shouldUseBackendAutonomy(intent, config)) {
            progress('status', '🧠 Using autonomous backend agent...');
            try {
                return await this._handleAutonomousTurn(userMessage, intent, config, progress);
            } catch (err) {
                // If backend returned an actual error (not a connection failure), show it directly
                if (this.backendAvailable) {
                    this._log(`Backend returned error: ${err.message}`);
                    return { type: 'error', message: err.message };
                }
                // Only fall back to local MCP if backend truly unreachable
                this._log(`Backend unreachable, falling back to local MCP flow: ${err.message}`);
                progress('status', '⚠️ Backend unreachable, switching to local agent...');
            }
        }

        // Ensure MCP is running
        if (!this.mcp.isRunning()) {
            try {
                progress('status', '⚡ Starting MCP server...');
                await this.initialize(config);
                progress('status', '✅ MCP server ready');
            } catch (err) {
                return { type: 'error', message: `Failed to start: ${err.message}` };
            }
        }

        // Set Gemini key (config → fallback → error)
        const apiKey = config.geminiApiKey || this.gemini.apiKey || process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || '';
        this.gemini.setApiKey(apiKey);
        this.gemini.setBackendUrl(config.backendUrl || 'http://localhost:8000');
        this.gemini.setModel(config.geminiModel || 'gemini-3-flash-preview');

        // Detect intent
        progress('status', '🧠 Understanding your request...');
        if (intent.intent === 'chat') {
            intent = await this.gemini.detectIntent(userMessage, this.lastSnapshot);
        }
        progress('status', `💡 Intent: ${intent.intent}`);

        try {
            switch (intent.intent) {
                case 'connect':
                    return await this._handleConnect(intent, config, progress);
                case 'explore':
                    return await this._handleExplore(progress);
                case 'screenshot':
                    return await this._handleScreenshot(progress);
                case 'navigate':
                    return await this._handleNavigate(userMessage, intent, config, progress);
                case 'generate_code':
                    return await this._handleGenerateCode(userMessage, progress);
                case 'test_plan':
                    return await this._handleTestPlan(userMessage, config, progress);
                case 'analyze_codebase':
                    return await this._handleAnalyzeCodebase(userMessage, config, progress);
                case 'help':
                    return this._handleHelp();
                case 'chat':
                default:
                    return await this._handleChat(userMessage, config, progress);
            }
        } catch (err) {
            return { type: 'error', message: `❌ Error: ${err.message}` };
        }
    }

    /**
     * Minimal local intent hint — only catches clear-cut fast-path intents.
     * Everything else goes to the backend where Gemini does proper classification.
     */
    _detectIntentHeuristic(userMessage) {
        const text = (userMessage || '').toLowerCase();

        if (/^\s*(help|what can you do)\s*[?]?\s*$/.test(text)) {
            return { intent: 'help' };
        }
        if (/\b(screenshot|screen shot|capture screen)\b/.test(text)) {
            return { intent: 'screenshot' };
        }

        // Let the backend (with Gemini) handle everything else
        return { intent: 'chat' };
    }

    _shouldUseBackendAutonomy(intent, config) {
        if (!this.backendAvailable || config.autonomousMode === false) {
            return false;
        }

        // Always route to backend when available — Gemini handles intent there
        return true;
    }

    _agentTypeForIntent(intent) {
        switch (intent.intent) {
            case 'navigate':
            case 'explore':
                return 'executor';
            case 'test_plan':
            case 'analyze_codebase':
                return 'planner';
            default:
                return 'balanced';
        }
    }

    async _handleAutonomousTurn(userMessage, intent, config, progress) {
        const result = await this.backend.unifiedChat(userMessage, {
            sessionId: this.sessionId,
            deviceName: config.deviceName,
            appPackage: config.appPackage,
            appActivity: config.appActivity,
            workspacePath: config.workspacePath,
            agentType: config.agentType || this._agentTypeForIntent(intent),
            model: config.geminiModel,
            contextMode: config.contextMode || 'workspace',
            attachedFiles: config.attachedFiles || [],
            onProgress: (type, message, data) => progress(type, message, data),
        });

        const response = this._formatBackendResult(result);
        this.history.push({ role: 'assistant', content: response });

        if (result.state?.locators_file) {
            this.actionHistory.push(`locators: ${result.state.locators_file}`);
        }

        return { type: intent.intent, message: response, image: result.image };
    }

    // ── Intent Handlers ────────────────────────────────────────────

    async _handleConnect(intent, config, progress) {
        progress('status', '🔌 Connecting to device...');
        const args = {
            appiumUrl: config.appiumUrl || 'http://127.0.0.1:4723',
        };
        if (intent.device || config.deviceName) args.deviceName = intent.device || config.deviceName;
        if (config.appPackage) args.appPackage = config.appPackage;
        if (config.appActivity) args.appActivity = config.appActivity;

        const result = await this.mcp.callTool('device_connect', args);
        const text = this._extractText(result);
        this.connected = true;

        // Auto-snapshot
        progress('status', '📸 Taking initial snapshot...');
        const snapshot = await this.mcp.callTool('app_snapshot', { compact: true });
        this.lastSnapshot = this._extractText(snapshot);

        const response = `✅ ${text}\n\n**Current Screen:**\n\`\`\`\n${this.lastSnapshot}\n\`\`\``;
        this.history.push({ role: 'assistant', content: response });
        return { type: 'connect', message: response };
    }

    async _handleExplore(progress) {
        progress('status', '🔍 Scanning screen...');
        const snapshot = await this.mcp.callTool('app_snapshot', { compact: true });
        this.lastSnapshot = this._extractText(snapshot);

        const response = `**App Screen Snapshot:**\n\`\`\`\n${this.lastSnapshot}\n\`\`\``;
        this.history.push({ role: 'assistant', content: response });
        return { type: 'explore', message: response };
    }

    async _handleScreenshot(progress) {
        progress('status', '📸 Taking screenshot...');
        const result = await this.mcp.callTool('device_screenshot', {});

        const imageContent = result.content?.find(c => c.type === 'image');
        if (imageContent) {
            return {
                type: 'screenshot',
                message: '📸 Screenshot captured',
                image: { data: imageContent.data, mimeType: imageContent.mimeType }
            };
        }

        const text = this._extractText(result);
        return { type: 'screenshot', message: text };
    }

    async _handleNavigate(userMessage, intent, config, progress) {
        if (intent.action && intent.action !== 'navigate') {
            return await this._executeSingleAction(intent, progress);
        }
        progress('status', '🚀 Starting navigation...');
        return await this._runAgentLoop(userMessage, config, progress, 15);
    }

    async _handleGenerateCode(userMessage, progress) {
        progress('status', '💻 Generating test code...');

        // Get screen context
        if (!this.lastSnapshot) {
            const snapshot = await this.mcp.callTool('app_snapshot', { compact: true });
            this.lastSnapshot = this._extractText(snapshot);
        }

        // Try Python backend first (has richer code generation with templates)
        if (this.backendAvailable) {
            try {
                progress('status', '💻 Using QaCoPilot backend for code generation...');
                const result = await this.backend.generateTestCode({
                    message: userMessage,
                    screen_data: this.lastSnapshot,
                    actions: this.actionHistory,
                });
                if (result && result.success !== false) {
                    const code = result.code || result.response || JSON.stringify(result, null, 2);
                    const response = `💻 **Generated Test Code (via QaCoPilot):**\n\n${code}`;
                    this.history.push({ role: 'assistant', content: response });
                    return { type: 'code', message: response };
                }
            } catch (err) {
                this._log(`Backend code gen failed, falling back to Gemini: ${err.message}`);
            }
        }

        // Fallback: use Gemini directly
        const prompt = `Generate Appium test automation code based on this user request and the actions/screens observed.

User request: ${userMessage}

Actions taken during session:
${this.actionHistory.map((a, i) => `${i + 1}. ${a}`).join('\n') || 'No actions recorded yet'}

Current screen:
${this.lastSnapshot}

Generate clean, working Appium Java test code with proper locators. Use Page Object pattern.
Include Maven dependencies needed.`;

        const code = await this.gemini.chat(
            'You are an expert Appium test code generator. Generate clean, well-structured test code.',
            [{ role: 'user', content: prompt }]
        );

        const response = `💻 **Generated Test Code:**\n\n${code}`;
        this.history.push({ role: 'assistant', content: response });
        return { type: 'code', message: response };
    }

    /**
     * Test plan generation — uses Python backend if available, else Gemini.
     */
    async _handleTestPlan(userMessage, config, progress) {
        progress('status', '📋 Generating test plan...');

        if (this.backendAvailable) {
            try {
                const result = await this.backend.unifiedChat(userMessage, {
                    sessionId: 'vscode-testplan',
                    deviceName: config.deviceName,
                    appPackage: config.appPackage,
                    appActivity: config.appActivity,
                    workspacePath: config.workspacePath,
                    onProgress: (type, msg) => progress('status', msg),
                });
                const response = result.response || result.message || JSON.stringify(result, null, 2);
                this.history.push({ role: 'assistant', content: response });
                return { type: 'test_plan', message: response };
            } catch (err) {
                this._log(`Backend test plan failed: ${err.message}`);
            }
        }

        // Fallback: Gemini
        const prompt = `Generate a comprehensive test plan for a mobile app.

User request: ${userMessage}

Current screen elements:
${this.lastSnapshot || 'No screen data available'}

Actions observed:
${this.actionHistory.map((a, i) => `${i + 1}. ${a}`).join('\n') || 'None'}

Generate a structured test plan with:
1. Test scenarios with IDs
2. Steps and expected results
3. Priority levels
4. Categorized by feature area`;

        const plan = await this.gemini.chat(
            'You are a QA expert. Generate comprehensive, well-structured test plans.',
            [{ role: 'user', content: prompt }]
        );

        this.history.push({ role: 'assistant', content: plan });
        return { type: 'test_plan', message: plan };
    }

    /**
     * Codebase analysis — uses Python backend.
     */
    async _handleAnalyzeCodebase(userMessage, config, progress) {
        if (!this.backendAvailable) {
            return {
                type: 'error',
                message: '⚠️ QaCoPilot backend not running. Start it with `python api_server.py` in the QaCoPilot directory.'
            };
        }

        progress('status', '🔍 Analyzing codebase...');
        const workspacePath = config.workspacePath || '';
        const result = await this.backend.analyzCodebase(workspacePath);
        const response = `📊 **Codebase Analysis:**\n\`\`\`json\n${JSON.stringify(result, null, 2)}\n\`\`\``;
        this.history.push({ role: 'assistant', content: response });
        return { type: 'analysis', message: response };
    }

    _handleHelp() {
        const backendStatus = this.backendAvailable ? '🟢 Connected' : '🔴 Not running';
        const help = `## 🤖 QA Agent - Mobile Test Automation

**Device Commands (via Appium MCP Server):**
- **"Connect to my device"** - Connect to Android via Appium
- **"Show me what's on screen"** - Take accessibility snapshot
- **"Take a screenshot"** - Capture device screen
- **"Tap the Login button"** - Tap on an element
- **"Type 'hello' in the search field"** - Type text
- **"Scroll down"** / **"Swipe left"** - Gestures
- **"Navigate to Settings and enable dark mode"** - Multi-step AI navigation
- **"Press back"** / **"Press home"** - Hardware keys
- **"Long press on item"** - Long press gesture
- **"Get device info"** - Device details

**QA Intelligence (via QaCoPilot Backend ${backendStatus}):**
- **"Generate test code for login flow"** - Appium Java test code
- **"Create a test plan for checkout"** - Structured test plans
- **"Analyze the codebase"** - Screen/locator extraction

**Prerequisites:**
1. Appium server running (\`npx appium\`)
2. Android device/emulator connected
3. Gemini API key in settings
4. *(Optional)* QaCoPilot backend: \`cd QaCoPilot && python api_server.py\``;

        this.history.push({ role: 'assistant', content: help });
        return { type: 'help', message: help };
    }

    async _handleChat(userMessage, config, progress) {
        // Route to Python backend if available (richer context, session memory)
        if (this.backendAvailable) {
            try {
                progress('status', '💬 Asking QaCoPilot...');
                const result = await this.backend.unifiedChat(userMessage, {
                    sessionId: 'vscode-default',
                    deviceName: config.deviceName,
                    appPackage: config.appPackage,
                    appActivity: config.appActivity,
                    workspacePath: config.workspacePath,
                    model: config.geminiModel,
                    onProgress: (type, msg) => progress('status', msg),
                });
                const response = result.response || result.message || JSON.stringify(result, null, 2);
                this.history.push({ role: 'assistant', content: response });
                return { type: 'chat', message: response };
            } catch {
                // Fall through to Gemini
            }
        }

        progress('status', '💬 Thinking...');
        const systemPrompt = `You are QA Agent, an AI-powered mobile test automation assistant.
You help users test Android apps using Appium.
You're connected to a real device and can interact with it.
Be concise, helpful, and action-oriented.
${this.lastSnapshot ? `\nCurrent screen:\n${this.lastSnapshot}` : ''}`;

        const response = await this.gemini.chat(systemPrompt, this.history);
        this.history.push({ role: 'assistant', content: response });
        return { type: 'chat', message: response };
    }

    // ── Agent Loop ─────────────────────────────────────────────────

    async _runAgentLoop(objective, config, progress, maxSteps = 15) {
        this.actionHistory = [];
        let stepsCompleted = 0;

        for (let step = 0; step < maxSteps; step++) {
            progress('status', `🔍 Step ${step + 1}: Reading screen...`);
            const snapshot = await this.mcp.callTool('app_snapshot', { compact: true });
            this.lastSnapshot = this._extractText(snapshot);

            progress('status', `🧠 Step ${step + 1}: Planning next action...`);
            let plan;
            try {
                plan = await this.gemini.planNextAction(objective, this.lastSnapshot, this.actionHistory);
            } catch (err) {
                progress('status', `⚠️ Planning failed: ${err.message}`);
                break;
            }

            if (plan.action === 'done') {
                progress('status', `✅ Objective achieved: ${plan.reason}`);
                this.actionHistory.push(`✅ Done: ${plan.reason}`);
                break;
            }
            if (plan.action === 'stuck') {
                progress('status', `⚠️ Stuck: ${plan.reason}`);
                this.actionHistory.push(`❌ Stuck: ${plan.reason}`);
                break;
            }

            progress('status', `⚡ Step ${step + 1}: ${plan.action} - ${plan.reason || ''}`);
            const actionResult = await this._executeAction(plan);
            const actionDesc = `${plan.action}: ${plan.selector || plan.direction || plan.text || ''} → ${actionResult.success ? '✅' : '❌'} ${actionResult.message || ''}`;
            this.actionHistory.push(actionDesc);
            progress('action', actionDesc);
            stepsCompleted++;

            if (!actionResult.success) {
                progress('status', `⚠️ Action failed: ${actionResult.message}`);
            }

            await this._sleep(500);
        }

        // Final snapshot
        const finalSnapshot = await this.mcp.callTool('app_snapshot', { compact: true });
        this.lastSnapshot = this._extractText(finalSnapshot);

        const summary = `**Navigation Complete** (${stepsCompleted} steps)\n\n` +
            `**Actions:**\n${this.actionHistory.map((a, i) => `${i + 1}. ${a}`).join('\n')}\n\n` +
            `**Final Screen:**\n\`\`\`\n${this.lastSnapshot}\n\`\`\``;

        this.history.push({ role: 'assistant', content: summary });
        return { type: 'navigate', message: summary };
    }

    // ── Action Execution ───────────────────────────────────────────

    async _executeSingleAction(intent, progress) {
        progress('status', `⚡ ${intent.action}...`);
        const result = await this._executeAction(intent);

        const snapshot = await this.mcp.callTool('app_snapshot', { compact: true });
        this.lastSnapshot = this._extractText(snapshot);

        const response = `${result.success ? '✅' : '❌'} ${result.message}\n\n**Screen After:**\n\`\`\`\n${this.lastSnapshot}\n\`\`\``;
        this.history.push({ role: 'assistant', content: response });
        return { type: 'action', message: response };
    }

    async _executeAction(plan) {
        try {
            let result;
            switch (plan.action) {
                case 'tap':
                case 'click':
                    result = await this.mcp.callTool('element_tap', {
                        selector: plan.selector,
                        selectorType: plan.selectorType || 'text'
                    });
                    break;
                case 'type':
                case 'enter_text':
                    result = await this.mcp.callTool('element_type', {
                        selector: plan.selector,
                        text: plan.text,
                        selectorType: plan.selectorType || 'text'
                    });
                    break;
                case 'scroll':
                    result = await this.mcp.callTool('device_scroll', {
                        direction: plan.direction || 'down'
                    });
                    break;
                case 'back':
                    result = await this.mcp.callTool('device_back', {});
                    break;
                case 'press_key':
                    result = await this.mcp.callTool('device_press_key', {
                        key: plan.key || 'home'
                    });
                    break;
                case 'long_press':
                    result = await this.mcp.callTool('element_long_press', {
                        selector: plan.selector,
                        selectorType: plan.selectorType || 'text'
                    });
                    break;
                case 'swipe':
                    result = await this.mcp.callTool('device_swipe', {
                        startX: plan.startX || 0.5, startY: plan.startY || 0.7,
                        endX: plan.endX || 0.5, endY: plan.endY || 0.3
                    });
                    break;
                case 'launch':
                    result = await this.mcp.callTool('app_launch', {
                        appPackage: plan.appPackage || plan.selector
                    });
                    break;
                case 'wait':
                    result = await this.mcp.callTool('element_wait', {
                        selector: plan.selector,
                        selectorType: plan.selectorType || 'text',
                        timeout: plan.timeout || 10
                    });
                    break;
                default:
                    return { success: false, message: `Unknown action: ${plan.action}` };
            }

            const text = this._extractText(result);
            const isError = result.isError || false;
            return { success: !isError, message: text };
        } catch (err) {
            return { success: false, message: err.message };
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────

    _formatBackendResult(result) {
        if (!result || typeof result !== 'object') return String(result);

        // Prefer human-readable fields
        if (result.response) return result.response;
        if (result.message) return result.message;

        // Build readable text from structured data
        const parts = [];

        if (result.error) {
            parts.push(`**Error:** ${result.error}`);
            if (result.details) {
                const d = String(result.details);
                parts.push(d.length > 300 ? d.substring(0, 300) + '...' : d);
            }
            return parts.join('\n');
        }

        if (result.status) parts.push(result.status);
        if (result.steps && Array.isArray(result.steps)) {
            parts.push('**Steps executed:**');
            result.steps.forEach((s, i) => {
                parts.push(`${i + 1}. ${s.action || ''} ${s.xpath || s.selector || ''}${s.reason ? ' — ' + s.reason : ''}`);
            });
        }
        if (result.test_plan || result.testPlan) {
            parts.push(`**Test Plan:**\n${result.test_plan || result.testPlan}`);
        }
        if (result.code || result.generated_code) {
            parts.push('```java\n' + (result.code || result.generated_code) + '\n```');
        }
        if (result.locators_collected) {
            parts.push(`Collected **${result.locators_collected}** locators.`);
        }
        if (result.locators_file) {
            parts.push(`Saved to: \`${result.locators_file.split('/').pop()}\``);
        }
        if (result.elements && Array.isArray(result.elements)) {
            parts.push(`Found **${result.elements.length}** elements on screen.`);
        }

        if (parts.length > 0) return parts.join('\n');

        // Last resort: formatted JSON in code block
        return '```json\n' + JSON.stringify(result, null, 2) + '\n```';
    }

    _extractText(mcpResult) {
        if (!mcpResult || !mcpResult.content) return '';
        const textPart = mcpResult.content.find(c => c.type === 'text');
        return textPart ? textPart.text : '';
    }

    _log(msg) {
        if (this.onLog) this.onLog(msg);
    }

    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async resetConversation(config) {
        const previousSessionId = this.sessionId;
        this.backend.setBaseUrl(config?.backendUrl || 'http://localhost:8000');

        try {
            await this.backend.resetUnifiedChatSession(previousSessionId);
        } catch (err) {
            this._log(`Backend session reset skipped: ${err.message}`);
        }

        this.clearHistory();
    }

    clearHistory() {
        this.history = [];
        this.actionHistory = [];
        this.lastSnapshot = '';
        this.sessionId = randomUUID();
    }

    dispose() {
        this.mcp.stop();
    }
}

module.exports = { QaAgent };
