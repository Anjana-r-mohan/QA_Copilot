/**
 * Returns the HTML for the chat sidebar webview.
 */
function getChatHtml(webview, extensionUri) {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--vscode-font-family, system-ui, sans-serif);
    font-size: var(--vscode-font-size, 13px);
    color: var(--vscode-foreground);
    background: var(--vscode-sideBar-background);
    height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* Header */
  .header {
    padding: 10px 14px;
    border-bottom: 1px solid var(--vscode-panel-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }
  .header h2 { font-size: 14px; font-weight: 600; }
  .header .status {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
  }
  .header .status.connected { color: #4ec9b0; }
  .header .status.error { color: #f44747; }
  .header button {
    background: none;
    border: 1px solid var(--vscode-button-border, var(--vscode-panel-border));
    color: var(--vscode-foreground);
    padding: 2px 8px;
    border-radius: 3px;
    cursor: pointer;
    font-size: 11px;
  }
  .header button:hover {
    background: var(--vscode-toolbar-hoverBackground);
  }

  /* Messages area */
  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 10px 14px;
  }
  .message {
    margin-bottom: 12px;
    line-height: 1.5;
  }
  .message.user {
    background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, var(--vscode-panel-border));
    border-radius: 8px;
    padding: 8px 12px;
  }
  .message.user::before {
    content: "You";
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: var(--vscode-descriptionForeground);
    margin-bottom: 4px;
  }
  .message.assistant {
    background: var(--vscode-editor-background);
    border-radius: 8px;
    padding: 8px 12px;
  }
  .message.assistant::before {
    content: "🤖 QA Agent";
    display: block;
    font-size: 11px;
    font-weight: 600;
    color: #4ec9b0;
    margin-bottom: 4px;
  }
  .message.status {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
    padding: 2px 0;
    margin-bottom: 4px;
  }
  .message.action {
    font-size: 12px;
    color: var(--vscode-descriptionForeground);
    padding: 2px 12px;
    border-left: 2px solid var(--vscode-focusBorder);
    margin-bottom: 4px;
  }
  .message.error {
    color: #f44747;
    padding: 8px 12px;
    background: rgba(244,71,71,0.1);
    border-radius: 4px;
  }

  /* Code blocks */
  .message pre {
    background: var(--vscode-textCodeBlock-background);
    padding: 8px 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-family: var(--vscode-editor-font-family, monospace);
    font-size: 12px;
    margin: 6px 0;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .message code {
    font-family: var(--vscode-editor-font-family, monospace);
    font-size: 12px;
    background: var(--vscode-textCodeBlock-background);
    padding: 1px 4px;
    border-radius: 3px;
  }

  /* Images */
  .message img {
    max-width: 100%;
    border-radius: 4px;
    margin: 6px 0;
  }

  /* Input area */
  .input-area {
    padding: 10px 14px;
    border-top: 1px solid var(--vscode-panel-border);
    flex-shrink: 0;
  }
  .input-row {
    display: flex;
    gap: 6px;
  }
  .input-area textarea {
    flex: 1;
    resize: none;
    border: 1px solid var(--vscode-input-border, var(--vscode-panel-border));
    background: var(--vscode-input-background);
    color: var(--vscode-input-foreground);
    padding: 8px 10px;
    border-radius: 4px;
    font-family: inherit;
    font-size: 13px;
    outline: none;
    min-height: 38px;
    max-height: 120px;
  }
  .input-area textarea:focus {
    border-color: var(--vscode-focusBorder);
  }
  .input-area button.send {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    border-radius: 4px;
    padding: 0 14px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
  }
  .input-area button.send:hover {
    background: var(--vscode-button-hoverBackground);
  }
  .input-area button.send:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .quick-actions {
    display: flex;
    gap: 4px;
    margin-top: 6px;
    flex-wrap: wrap;
  }
  .quick-actions button {
    background: var(--vscode-badge-background);
    color: var(--vscode-badge-foreground);
    border: none;
    border-radius: 10px;
    padding: 2px 10px;
    font-size: 11px;
    cursor: pointer;
  }
  .quick-actions button:hover {
    opacity: 0.8;
  }

  /* Loading */
  .loading {
    display: inline-block;
    width: 16px; height: 16px;
    border: 2px solid var(--vscode-descriptionForeground);
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 6px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <div class="header">
    <div>
      <h2>QA Agent</h2>
      <div class="status" id="status">Not connected</div>
    </div>
    <button onclick="clearChat()">Clear</button>
  </div>

  <div class="messages" id="messages">
    <div class="message assistant">
      <strong>Welcome!</strong> I'm your QA automation agent for mobile apps.<br><br>
      <strong>Quick start:</strong><br>
      1. Make sure Appium is running (<code>npx appium</code>)<br>
      2. Connect a device/emulator<br>
      3. Tell me what to do!<br><br>
      Type <strong>"help"</strong> for all commands.
    </div>
  </div>

  <div class="input-area">
    <div class="input-row">
      <textarea id="input" placeholder="Tell me what to test..." rows="1"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMessage();}"></textarea>
      <button class="send" id="sendBtn" onclick="sendMessage()">Send</button>
    </div>
    <div class="quick-actions">
      <button onclick="quickSend('Connect to my device')">🔌 Connect</button>
      <button onclick="quickSend('Show me what\\'s on screen')">🔍 Explore</button>
      <button onclick="quickSend('Take a screenshot')">📸 Screenshot</button>
      <button onclick="quickSend('Scroll down')">⬇️ Scroll</button>
      <button onclick="quickSend('Press back')">◀️ Back</button>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();
    const messagesDiv = document.getElementById('messages');
    const inputEl = document.getElementById('input');
    const sendBtn = document.getElementById('sendBtn');
    const statusEl = document.getElementById('status');
    let busy = false;

    function sendMessage() {
      const text = inputEl.value.trim();
      if (!text || busy) return;
      addMessage('user', text);
      inputEl.value = '';
      inputEl.style.height = 'auto';
      setBusy(true);
      vscode.postMessage({ type: 'message', text });
    }

    function quickSend(text) {
      if (busy) return;
      inputEl.value = text;
      sendMessage();
    }

    function clearChat() {
      messagesDiv.innerHTML = '';
      vscode.postMessage({ type: 'clear' });
    }

    function setBusy(b) {
      busy = b;
      sendBtn.disabled = b;
      if (b) {
        statusEl.innerHTML = '<span class="loading"></span> Processing...';
        statusEl.className = 'status';
      }
    }

    function addMessage(role, content, extra) {
      const div = document.createElement('div');
      div.className = 'message ' + role;

      if (role === 'assistant' || role === 'user') {
        div.innerHTML = renderMarkdown(content);
      } else {
        div.textContent = content;
      }

      // Add image if present
      if (extra && extra.image) {
        const img = document.createElement('img');
        img.src = 'data:' + (extra.image.mimeType || 'image/png') + ';base64,' + extra.image.data;
        div.appendChild(img);
      }

      messagesDiv.appendChild(div);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function renderMarkdown(text) {
      // Simple markdown: code blocks, inline code, bold, newlines
      return text
        .replace(/\`\`\`([\\s\\S]*?)\`\`\`/g, '<pre>$1</pre>')
        .replace(/\`([^\`]+)\`/g, '<code>$1</code>')
        .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
        .replace(/\\n/g, '<br>');
    }

    // Handle messages from extension
    window.addEventListener('message', event => {
      const msg = event.data;
      switch (msg.type) {
        case 'response':
          addMessage('assistant', msg.message, msg);
          setBusy(false);
          break;
        case 'status':
          statusEl.textContent = msg.message;
          statusEl.className = 'status';
          addMessage('status', msg.message);
          break;
        case 'action':
          addMessage('action', msg.message);
          break;
        case 'error':
          addMessage('error', msg.message);
          setBusy(false);
          break;
        case 'connected':
          statusEl.textContent = '🟢 Connected';
          statusEl.className = 'status connected';
          break;
        case 'disconnected':
          statusEl.textContent = '🔴 Disconnected';
          statusEl.className = 'status error';
          break;
      }
    });

    // Auto-resize textarea
    inputEl.addEventListener('input', () => {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
    });

    inputEl.focus();
  </script>
</body>
</html>`;
}

module.exports = { getChatHtml };
