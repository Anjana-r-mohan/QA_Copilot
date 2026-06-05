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
        vscode.commands.registerCommand('qaAgent.clearChat', () => {
            if (agent) agent.clearHistory();
            if (provider.webview) {
                provider.webview.postMessage({ type: 'status', message: 'Chat cleared' });
            }
        }),
        vscode.commands.registerCommand('qaAgent.startBackend', () => {
            const terminal = vscode.window.createTerminal('QaCoPilot Backend');
            const config = vscode.workspace.getConfiguration('qaAgent');
            const backendPath = config.get('backendPath', '');
            if (backendPath) {
                terminal.sendText(`cd "${backendPath}" && python api_server.py`);
            } else {
                terminal.sendText('echo "Set qaAgent.backendPath in settings to your QaCoPilot directory"');
            }
            terminal.show();
        })
    );

    context.subscriptions.push(outputChannel);
    outputChannel.appendLine('QA Agent extension activated');
}

class QaAgentViewProvider {
    constructor(context, agent) {
        this.context = context;
        this.agent = agent;
        this.webview = null;
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
                    await this.handleUserMessage(message.text);
                    break;
                case 'clear':
                    this.agent.clearHistory();
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

    async handleUserMessage(text) {
        const config = this.getConfig();

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
            geminiModel: config.get('geminiModel', 'gemini-2.0-flash'),
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
}

function deactivate() {
    if (agent) {
        agent.dispose();
        agent = null;
    }
}

module.exports = { activate, deactivate };
