const http = require('http');
const https = require('https');

/**
 * Gemini API client for the QA Agent.
 * Routes LLM requests through the QaCoPilot Python backend (same as IntelliJ plugin).
 * Falls back to direct Google API if backend is unavailable.
 */
class GeminiClient {
    constructor(apiKey, model = 'gemini-3-flash-preview') {
        this.apiKey = apiKey;
        this.model = model;
        this.backendUrl = 'http://localhost:8000';
    }

    setApiKey(key) {
        this.apiKey = key;
    }

    setModel(model) {
        this.model = model;
    }

    setBackendUrl(url) {
        this.backendUrl = url || 'http://localhost:8000';
    }

    /**
     * Send a prompt to the LLM via the Python backend's unified-chat endpoint.
     * @param {string} systemPrompt - System instructions
     * @param {Array<{role: string, content: string}>} messages - Conversation history
     * @returns {Promise<string>} The model's response text
     */
    async chat(systemPrompt, messages) {
        if (!this.apiKey) {
            throw new Error('Gemini API key not configured. Set it in QA Agent settings.');
        }

        // Build a combined prompt from system instructions and messages
        const userMessages = messages.filter(m => m.role === 'user');
        const lastUserMessage = userMessages.length > 0 ? userMessages[userMessages.length - 1].content : '';
        const fullPrompt = systemPrompt ? `${systemPrompt}\n\n${lastUserMessage}` : lastUserMessage;

        // Route through Python backend (same as IntelliJ plugin).
        // Only fall back to direct Google API if backend is not reachable (ECONNREFUSED).
        try {
            return await this._chatViaBackend(fullPrompt);
        } catch (backendErr) {
            const isConnectionError = backendErr.message && (
                backendErr.message.includes('ECONNREFUSED') ||
                backendErr.message.includes('ECONNRESET') ||
                backendErr.message.includes('ENOTFOUND')
            );
            if (isConnectionError) {
                // Backend not running — try direct Google API
                return await this._chatDirectGoogle(systemPrompt, messages);
            }
            // Backend returned an error — surface it, don't mask with Google auth failure
            throw backendErr;
        }
    }

    /**
     * Chat via QaCoPilot Python backend (like IntelliJ plugin does).
     */
    async _chatViaBackend(prompt) {
        const body = JSON.stringify({
            message: prompt,
            session_id: 'vscode-gemini',
            agent_type: 'balanced',
            model: this.model,
            context_mode: 'none',
        });

        return new Promise((resolve, reject) => {
            const url = new URL(this.backendUrl + '/api/unified-chat');
            const client = url.protocol === 'https:' ? https : http;

            const options = {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body)
                },
                timeout: 60000,
            };

            const req = client.request(options, (res) => {
                let buffer = '';
                let lastResponse = '';

                res.on('data', (chunk) => {
                    buffer += chunk.toString();
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const event = JSON.parse(line.slice(6));
                                if (event.type === 'complete' && event.result) {
                                    lastResponse = event.result.response || event.result.message || JSON.stringify(event.result);
                                } else if (event.type === 'chat_response' || event.type === 'response') {
                                    lastResponse = event.message || event.data || '';
                                } else if (event.type === 'error') {
                                    reject(new Error(event.message));
                                    return;
                                }
                            } catch { /* skip non-JSON */ }
                        }
                    }
                });

                res.on('end', () => {
                    if (lastResponse) {
                        resolve(lastResponse);
                    } else {
                        reject(new Error('No response from backend'));
                    }
                });

                res.on('error', reject);
            });

            req.on('error', reject);
            req.on('timeout', () => { req.destroy(); reject(new Error('Backend request timed out')); });
            req.write(body);
            req.end();
        });
    }

    /**
     * Direct Google Generative AI API call (fallback).
     */
    async _chatDirectGoogle(systemPrompt, messages) {
        const contents = messages.map(msg => ({
            role: msg.role === 'assistant' ? 'model' : 'user',
            parts: [{ text: msg.content }]
        }));

        const body = JSON.stringify({
            contents,
            systemInstruction: {
                parts: [{ text: systemPrompt }]
            },
            generationConfig: {
                temperature: 0.3,
                maxOutputTokens: 4096,
            }
        });

        const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;

        return new Promise((resolve, reject) => {
            const parsedUrl = new URL(url);
            const options = {
                hostname: parsedUrl.hostname,
                path: parsedUrl.pathname + parsedUrl.search,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Content-Length': Buffer.byteLength(body)
                }
            };

            const req = https.request(options, (res) => {
                let data = '';
                res.on('data', chunk => data += chunk);
                res.on('end', () => {
                    try {
                        const json = JSON.parse(data);
                        if (json.error) {
                            reject(new Error(`Gemini API error: ${json.error.message}`));
                            return;
                        }
                        const text = json.candidates?.[0]?.content?.parts?.[0]?.text;
                        if (!text) {
                            reject(new Error('Empty response from Gemini'));
                            return;
                        }
                        resolve(text);
                    } catch (e) {
                        reject(new Error(`Failed to parse Gemini response: ${e.message}`));
                    }
                });
            });

            req.on('error', (e) => reject(new Error(`Gemini request failed: ${e.message}`)));
            req.setTimeout(60000, () => {
                req.destroy();
                reject(new Error('Gemini request timed out'));
            });

            req.write(body);
            req.end();
        });
    }

    /**
     * Detect intent from user message - what does the user want to do?
     */
    async detectIntent(userMessage, screenContext) {
        const prompt = `You are a QA automation agent for mobile apps. Analyze the user's message and return a JSON object with the intent.

Possible intents:
- "connect": User wants to connect to a device
- "explore": User wants to see what's on screen (take snapshot)
- "navigate": User wants to interact with the app (tap, type, scroll, etc.)
- "screenshot": User wants a screenshot
- "generate_code": User wants to generate test code or locators
- "test_plan": User wants to create a test plan or test cases
- "analyze_codebase": User wants to analyze app source code or extract screens/locators from code
- "help": User wants help
- "chat": General conversation

Also extract any action details:
- "selector": element to interact with
- "text": text to type
- "direction": scroll direction
- "app_package": app to launch

Return ONLY valid JSON like:
{"intent": "navigate", "action": "tap", "selector": "Login", "selectorType": "text"}
{"intent": "explore"}
{"intent": "connect", "device": "emulator-5554"}
{"intent": "chat"}

User message: "${userMessage}"
${screenContext ? `\nCurrent screen:\n${screenContext}` : ''}`;

        try {
            const response = await this.chat(
                'You are a JSON-only intent detector. Return ONLY valid JSON, no markdown.',
                [{ role: 'user', content: prompt }]
            );

            // Extract JSON from response
            const jsonMatch = response.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                return JSON.parse(jsonMatch[0]);
            }
            return { intent: 'chat' };
        } catch (e) {
            return { intent: 'chat', error: e.message };
        }
    }

    /**
     * Given a screen snapshot, decide the next action to take.
     */
    async planNextAction(objective, screenSnapshot, history = []) {
        const prompt = `You are a mobile app QA automation agent. You can see the app's UI tree and must decide the next action.

OBJECTIVE: ${objective}

CURRENT SCREEN:
${screenSnapshot}

ACTIONS TAKEN SO FAR:
${history.length > 0 ? history.map((h, i) => `${i + 1}. ${h}`).join('\n') : 'None yet'}

Available actions (return ONE as JSON):
- {"action": "tap", "selector": "<text or id>", "selectorType": "text|id|contentDesc", "reason": "why"}
- {"action": "type", "selector": "<input field>", "text": "<text to type>", "selectorType": "text|id", "reason": "why"}
- {"action": "scroll", "direction": "down|up|left|right", "reason": "why"}
- {"action": "back", "reason": "why"}
- {"action": "done", "reason": "objective achieved"}
- {"action": "stuck", "reason": "cannot proceed"}

Rules:
- Pick the action most likely to advance toward the objective
- If the target element is visible, interact with it directly
- If not visible, scroll to find it
- If a dialog/popup blocks, dismiss it first
- Return ONLY valid JSON`;

        const response = await this.chat(
            'You are a mobile QA agent. Return ONLY valid JSON for the next action.',
            [{ role: 'user', content: prompt }]
        );

        const jsonMatch = response.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            return JSON.parse(jsonMatch[0]);
        }
        throw new Error('Could not parse action plan from Gemini');
    }
}

module.exports = { GeminiClient };
