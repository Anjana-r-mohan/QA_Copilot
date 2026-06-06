const vscode = require('vscode');
const { QaAgent } = require('./qa-agent');
const { getChatHtml } = require('./chat-view');

let agent = null;

function activate(context) {
    agent = new QaAgent();

    const outputChannel = vscode.window.createOutputChannel('QA Agent');
    agent.onLog = (msg) => outputChannel.appendLine(msg);

    // Register sidebar webview
    const provider = new QaAgentViewProvider(context, agent);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('qaAgent.chatView', provider, {
            webviewOptions: { retainContextWhenHidden: true }
        })
    );

    // Commands
    context.subscriptions.push(
        vscode.commands.registerCommand('qaAgent.focus', () => {
            vscode.commands.executeCommand('qaAgent.chatView.focus');
        }),
        vscode.commands.registerCommand('qaAgent.clearChat', async () => {
            if (agent) {
                await agent.resetConversation(provider.getConfig());
            }
            if (provider.webview) {
                provider.webview.postMessage({ type: 'chatCleared', message: 'Chat cleared' });
            }
        }),
        vscode.commands.registerCommand('qaAgent.startBackend', () => provider.startBackend())
    );

    context.subscriptions.push(outputChannel);
    outputChannel.appendLine('QA Agent extension activated');
}

class QaAgentViewProvider {
    constructor(context, agent) {
        this.context = context;
        this.agent = agent;
        this.webview = null;
        this.overrideAgentType = null;
        this.overrideModel = null;
    }

    resolveWebviewView(webviewView) {
        this.webview = webviewView.webview;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.context.extensionUri]
        };

        webviewView.webview.html = getChatHtml(webviewView.webview, this.context.extensionUri);

        webviewView.webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case 'message':
                    await this.handleUserMessage(message.text, message.attachedFiles, message.agentType, message.model);
                    break;
                case 'clear':
                    await this.agent.resetConversation(this.getConfig());
                    this.webview?.postMessage({ type: 'chatCleared', message: 'Conversation cleared and backend session reset' });
                    break;
                case 'startBackend':
                    await this.startBackend();
                    break;
                case 'attachFile':
                    await this.pickFile();
                    break;
                case 'setAgentType':
                    this.overrideAgentType = message.value;
                    break;
                case 'setModel':
                    this.overrideModel = message.value;
                    break;
            }
        });

        this.agent.mcp.on('connected', () => {
            this.webview?.postMessage({ type: 'connected' });
        });
        this.agent.mcp.on('disconnected', () => {
            this.webview?.postMessage({ type: 'disconnected' });
        });
    }

    async handleUserMessage(text, attachedFiles, agentType, model) {
        const config = this.getConfig();
        if (agentType) config.agentType = agentType;
        if (model) config.geminiModel = model;
        if (attachedFiles && attachedFiles.length > 0) {
            config.attachedFiles = attachedFiles;
        }
        // Also attach the currently open editor file if context mode is workspace
        if (config.contextMode === 'workspace') {
            const editor = vscode.window.activeTextEditor;
            if (editor && editor.document.uri.scheme === 'file') {
                const currentFile = editor.document.uri.fsPath;
                if (!config.attachedFiles) config.attachedFiles = [];
                if (!config.attachedFiles.includes(currentFile)) {
                    config.attachedFiles.push(currentFile);
                }
            }
        }

        try {
            const result = await this.agent.processMessage(text, config, (type, message, data) => {
                this.webview?.postMessage({ type, message, data });
            });

            if (result) {
                this.webview?.postMessage({
                    type: 'response',
                    message: result.message,
                    image: result.image
                });
            }
        } catch (err) {
            this.webview?.postMessage({
                type: 'error',
                message: `Error: ${err.message}`
            });
        }
    }

    getConfig() {
        const config = vscode.workspace.getConfiguration('qaAgent');
        const folders = vscode.workspace.workspaceFolders;
        return {
            geminiApiKey: config.get('geminiApiKey', ''),
            geminiModel: config.get('geminiModel', 'gemini-3-flash-preview'),
            autonomousMode: config.get('autonomousMode', true),
            agentType: config.get('agentType', 'balanced'),
            contextMode: config.get('contextMode', 'workspace'),
            javaPath: config.get('javaPath', 'java'),
            serverJar: config.get('serverJar', ''),
            appiumUrl: config.get('appiumUrl', 'http://127.0.0.1:4723'),
            deviceName: config.get('deviceName', ''),
            appPackage: config.get('appPackage', ''),
            appActivity: config.get('appActivity', ''),
            backendUrl: config.get('backendUrl', 'http://localhost:8000'),
            backendPath: config.get('backendPath', ''),
            workspacePath: folders && folders.length > 0 ? folders[0].uri.fsPath : '',
        };
    }

    async startBackend() {
        const config = vscode.workspace.getConfiguration('qaAgent');
        const backendPath = config.get('backendPath', '');
        const terminal = vscode.window.createTerminal('QaCoPilot Backend');

        if (backendPath) {
            terminal.sendText(`cd "${backendPath}" && if command -v python >/dev/null 2>&1; then python api_server.py; else python3 api_server.py; fi`);
            this.webview?.postMessage({ type: 'action', message: `Starting backend in terminal from ${backendPath}` });
        } else {
            terminal.sendText('echo "Set qaAgent.backendPath in settings to your QaCoPilot directory"');
            this.webview?.postMessage({ type: 'warning', message: 'qaAgent.backendPath is not set. Configure it before starting the backend.' });
        }

        terminal.show();
    }

    async pickFile() {
        const result = await vscode.window.showOpenDialog({
            canSelectFiles: true,
            canSelectFolders: false,
            canSelectMany: true,
            openLabel: 'Attach',
            filters: {
                'All Files': ['*'],
                'Test Plans': ['md', 'txt', 'json', 'jsonl', 'csv'],
                'Code': ['java', 'py', 'js', 'ts'],
            }
        });
        if (result && result.length > 0) {
            for (const uri of result) {
                this.webview?.postMessage({ type: 'fileAttached', filePath: uri.fsPath });
            }
        }
    }
}

function deactivate() {
    if (agent) {
        agent.dispose();
        agent = null;
    }
}

module.exports = { activate, deactivate };
