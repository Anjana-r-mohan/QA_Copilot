const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const EventEmitter = require('events');

/**
 * MCP Client - spawns the Appium MCP server JAR and communicates via JSON-RPC 2.0 over stdio.
 * Equivalent to the IntelliJ McpClientBridge from the old project.
 */
class McpClient extends EventEmitter {
    constructor() {
        super();
        this.process = null;
        this.requestId = 0;
        this.pendingRequests = new Map();
        this.initialized = false;
        this.buffer = '';
        this.tools = [];
    }

    /**
     * Find the server JAR in common locations.
     */
    findServerJar(configuredPath) {
        if (configuredPath && fs.existsSync(configuredPath)) {
            return configuredPath;
        }

        const candidates = [
            // QaCoPilot repo: vscode-extension/src/ → appium-mcp-server/target/
            path.join(__dirname, '..', '..', 'appium-mcp-server', 'target', 'appium-mcp-server-1.0.0.jar'),
            // Sibling repo
            path.join(__dirname, '..', '..', '..', 'appium-mcp-server', 'target', 'appium-mcp-server-1.0.0.jar'),
            // Same repo target
            path.join(__dirname, '..', '..', 'target', 'appium-mcp-server-1.0.0.jar'),
            // Extension bundled
            path.join(__dirname, '..', 'server', 'appium-mcp-server-1.0.0.jar'),
        ];

        // Home directory
        const homeDir = require('os').homedir();
        candidates.push(path.join(homeDir, 'appium-mcp', 'appium-mcp-server-1.0.0.jar'));
        candidates.push(path.join(homeDir, 'appium-mcp-server', 'target', 'appium-mcp-server-1.0.0.jar'));

        // VS Code workspace folders
        try {
            const vscode = require('vscode');
            if (vscode.workspace.workspaceFolders) {
                for (const folder of vscode.workspace.workspaceFolders) {
                    candidates.push(path.join(folder.uri.fsPath, 'target', 'appium-mcp-server-1.0.0.jar'));
                }
            }
        } catch (_) { /* not in vscode context */ }

        for (const candidate of candidates) {
            if (fs.existsSync(candidate)) {
                return candidate;
            }
        }
        return null;
    }

    /**
     * Start the MCP server and perform handshake.
     */
    async start(javaPath, jarPath) {
        if (this.process) {
            return { success: true, message: 'Already running' };
        }

        return new Promise((resolve, reject) => {
            try {
                this.process = spawn(javaPath || 'java', ['-jar', jarPath], {
                    stdio: ['pipe', 'pipe', 'pipe']
                });

                this.process.stdout.on('data', (data) => {
                    this.buffer += data.toString();
                    this._processBuffer();
                });

                this.process.stderr.on('data', (data) => {
                    this.emit('log', data.toString().trim());
                });

                this.process.on('close', (code) => {
                    this.emit('log', `MCP server exited with code ${code}`);
                    this.process = null;
                    this.initialized = false;
                    this.emit('disconnected');
                });

                this.process.on('error', (err) => {
                    reject(new Error(`Failed to start MCP server: ${err.message}`));
                });

                // Perform MCP handshake
                setTimeout(async () => {
                    try {
                        const initResult = await this.sendRequest('initialize', {
                            protocolVersion: '2024-11-05',
                            capabilities: {},
                            clientInfo: { name: 'qa-agent', version: '1.0.0' }
                        });

                        // Send initialized notification (no response expected)
                        this._sendNotification('notifications/initialized', {});

                        // List available tools
                        const toolsResult = await this.sendRequest('tools/list', {});
                        this.tools = toolsResult.tools || [];

                        this.initialized = true;
                        this.emit('connected', this.tools);
                        resolve({
                            success: true,
                            serverInfo: initResult.serverInfo,
                            tools: this.tools
                        });
                    } catch (err) {
                        reject(err);
                    }
                }, 500);

            } catch (err) {
                reject(err);
            }
        });
    }

    /**
     * Call an MCP tool by name with arguments.
     */
    async callTool(name, args = {}) {
        if (!this.process) {
            throw new Error('MCP server not running. Start it first.');
        }
        const result = await this.sendRequest('tools/call', { name, arguments: args });
        return result;
    }

    /**
     * Send a JSON-RPC request and wait for the response.
     */
    sendRequest(method, params) {
        return new Promise((resolve, reject) => {
            const id = ++this.requestId;
            const request = {
                jsonrpc: '2.0',
                method,
                params,
                id
            };

            const timeout = setTimeout(() => {
                this.pendingRequests.delete(id);
                reject(new Error(`Request timed out: ${method} (id=${id})`));
            }, 30000);

            this.pendingRequests.set(id, { resolve, reject, timeout });

            const json = JSON.stringify(request);
            this.process.stdin.write(json + '\n');
        });
    }

    /**
     * Send a notification (no response expected).
     */
    _sendNotification(method, params) {
        const notification = { jsonrpc: '2.0', method, params };
        this.process.stdin.write(JSON.stringify(notification) + '\n');
    }

    /**
     * Process the stdout buffer for complete JSON lines.
     */
    _processBuffer() {
        const lines = this.buffer.split('\n');
        this.buffer = lines.pop() || '';

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;

            try {
                const response = JSON.parse(trimmed);
                if (response.id != null) {
                    const pending = this.pendingRequests.get(response.id);
                    if (pending) {
                        clearTimeout(pending.timeout);
                        this.pendingRequests.delete(response.id);
                        if (response.error) {
                            pending.reject(new Error(`${response.error.message} (code ${response.error.code})`));
                        } else {
                            pending.resolve(response.result);
                        }
                    }
                }
            } catch (e) {
                this.emit('log', `Parse error: ${e.message}`);
            }
        }
    }

    /**
     * Stop the MCP server.
     */
    stop() {
        if (this.process) {
            this.process.kill();
            this.process = null;
            this.initialized = false;
            this.tools = [];
            // Reject all pending requests
            for (const [id, pending] of this.pendingRequests) {
                clearTimeout(pending.timeout);
                pending.reject(new Error('Server stopped'));
            }
            this.pendingRequests.clear();
        }
    }

    isRunning() {
        return this.process !== null && this.initialized;
    }

    getTools() {
        return this.tools;
    }
}

module.exports = { McpClient };
