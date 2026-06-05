const http = require('http');
const https = require('https');

/**
 * Client for QaCoPilot Python FastAPI backend.
 * Provides access to test plan generation, codebase analysis, code generation, etc.
 * The Java MCP server handles device interaction; this handles everything else.
 */
class BackendClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
    }

    setBaseUrl(url) {
        this.baseUrl = url || 'http://localhost:8000';
    }

    /**
     * Check if the Python backend is running.
     */
    async isAvailable() {
        try {
            const result = await this._request('GET', '/health');
            return result && result.status === 'healthy';
        } catch {
            return false;
        }
    }

    /**
     * Call the unified chat endpoint (streaming).
     * Returns the complete result after streaming finishes.
     */
    async unifiedChat(message, options = {}) {
        const body = {
            message,
            session_id: options.sessionId || 'vscode-default',
            device_name: options.deviceName || '127.0.0.1:6555',
            app_package: options.appPackage || undefined,
            app_activity: options.appActivity || undefined,
            workspace_path: options.workspacePath || undefined,
            agent_type: options.agentType || 'balanced',
            model: options.model || undefined,
            context_mode: options.contextMode || 'workspace',
        };

        return new Promise((resolve, reject) => {
            const url = new URL(this.baseUrl + '/api/unified-chat');
            const isHttps = url.protocol === 'https:';
            const client = isHttps ? https : http;

            const reqOptions = {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname,
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            };

            const req = client.request(reqOptions, (res) => {
                let buffer = '';
                let lastResult = null;
                const progressEvents = [];

                res.on('data', (chunk) => {
                    buffer += chunk.toString();
                    // Parse SSE events
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const event = JSON.parse(line.slice(6));
                                if (event.type === 'complete') {
                                    lastResult = event.result;
                                } else if (event.type === 'error') {
                                    reject(new Error(event.message));
                                    return;
                                } else {
                                    progressEvents.push(event);
                                    if (options.onProgress) {
                                        options.onProgress(event.type, event.message, event.data);
                                    }
                                }
                            } catch { /* skip non-JSON */ }
                        }
                    }
                });

                res.on('end', () => {
                    resolve(lastResult || { response: 'No result from backend' });
                });

                res.on('error', reject);
            });

            req.on('error', reject);
            req.write(JSON.stringify(body));
            req.end();
        });
    }

    /**
     * Analyze a codebase for screens and locators.
     */
    async analyzCodebase(repoPath) {
        return this._request('POST', '/api/analyze', { repo_path: repoPath });
    }

    /**
     * Get extracted locators.
     */
    async getLocators(platform = 'both') {
        return this._request('GET', `/api/locators?platform=${platform}`);
    }

    /**
     * Generate test code from the Python backend.
     */
    async generateTestCode(request) {
        return this._request('POST', '/api/generate-test-code', request);
    }

    /**
     * Call the Python MCP endpoint directly.
     */
    async callMcpTool(toolName, params = {}) {
        return this._request('POST', '/mcp', {
            id: `vscode-${Date.now()}`,
            method: 'callTool',
            params: { tool_name: toolName, arguments: params },
        });
    }

    /**
     * Take a screenshot via the Python backend.
     */
    async screenshot(filename) {
        return this._request('POST', '/api/screenshot', { filename });
    }

    // ── Internal ──────────────────────────────────────────────────

    _request(method, path, body) {
        return new Promise((resolve, reject) => {
            const url = new URL(this.baseUrl + path);
            const isHttps = url.protocol === 'https:';
            const client = isHttps ? https : http;

            const options = {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname + url.search,
                method,
                headers: { 'Content-Type': 'application/json' },
                timeout: 30000,
            };

            const req = client.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => (data += chunk));
                res.on('end', () => {
                    try {
                        resolve(JSON.parse(data));
                    } catch {
                        resolve({ raw: data });
                    }
                });
            });

            req.on('error', reject);
            req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')); });

            if (body) req.write(JSON.stringify(body));
            req.end();
        });
    }
}

module.exports = { BackendClient };
