/**
 * Conversational chat UI for QA Agent sidebar.
 * Clean thread, collapsed activity, no static clutter.
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
    font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, sans-serif);
    font-size: 13px;
    color: var(--vscode-foreground);
    background: var(--vscode-sideBar-background);
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* ── Minimal header ── */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-bottom: 1px solid var(--vscode-panel-border);
    flex-shrink: 0;
  }
  .topbar-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .topbar-left span {
    font-weight: 600;
    font-size: 13px;
  }
  .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--vscode-descriptionForeground);
  }
  .dot.on { background: #4ec9b0; }
  .dot.off { background: #f14c4c; }
  .topbar-right {
    display: flex;
    gap: 6px;
  }
  .tb {
    background: none;
    border: 1px solid var(--vscode-panel-border);
    color: var(--vscode-descriptionForeground);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 11px;
    cursor: pointer;
  }
  .tb:hover {
    color: var(--vscode-foreground);
    border-color: var(--vscode-foreground);
  }

  /* ── Thread ── */
  .thread {
    flex: 1;
    overflow-y: auto;
    padding: 16px 12px 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Empty state */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    gap: 8px;
    color: var(--vscode-descriptionForeground);
    text-align: center;
    padding: 40px 20px;
  }
  .empty-state .es-icon { font-size: 28px; opacity: 0.5; }
  .empty-state p { max-width: 260px; line-height: 1.5; }

  /* ── Turn (user or assistant) ── */
  .turn { display: flex; gap: 8px; align-items: flex-start; }
  .turn.user { flex-direction: row-reverse; }

  .av {
    width: 24px; height: 24px;
    border-radius: 8px;
    display: grid;
    place-items: center;
    font-size: 10px;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 2px;
  }
  .av.a {
    background: linear-gradient(135deg, #5cc8ff, #4ec9b0);
    color: #0a0a0a;
  }
  .av.u {
    background: var(--vscode-input-background);
    color: var(--vscode-foreground);
    border: 1px solid var(--vscode-panel-border);
  }

  .msg {
    max-width: 86%;
    min-width: 0;
  }
  .bubble {
    padding: 10px 12px;
    border-radius: 14px;
    line-height: 1.55;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }
  .turn.assistant .bubble {
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
  }
  .turn.user .bubble {
    background: color-mix(in srgb, var(--vscode-button-background) 18%, var(--vscode-input-background));
    border: 1px solid color-mix(in srgb, var(--vscode-button-background) 30%, var(--vscode-panel-border));
  }

  /* ── Thinking indicator ── */
  .thinking {
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }
  .think-body {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .think-dots {
    display: flex;
    gap: 4px;
    padding: 10px 0;
  }
  .think-dots span {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--vscode-descriptionForeground);
    animation: blink 1.2s infinite;
  }
  .think-dots span:nth-child(2) { animation-delay: 0.2s; }
  .think-dots span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes blink {
    0%, 80%, 100% { opacity: 0.25; }
    40% { opacity: 1; }
  }
  .think-status {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
    max-width: 280px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* ── Collapsible activity log ── */
  .activity-wrap {
    margin-left: 32px;
  }
  .activity-toggle {
    background: none;
    border: none;
    color: var(--vscode-descriptionForeground);
    font-size: 11px;
    cursor: pointer;
    padding: 4px 0;
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .activity-toggle:hover { color: var(--vscode-foreground); }
  .activity-toggle .arrow { transition: transform 120ms; }
  .activity-toggle.open .arrow { transform: rotate(90deg); }
  .activity-list {
    display: none;
    flex-direction: column;
    gap: 2px;
    padding: 4px 0 4px 12px;
    border-left: 2px solid var(--vscode-panel-border);
    margin-top: 4px;
  }
  .activity-list.open { display: flex; }
  .activity-list .ev {
    font-size: 11px;
    color: var(--vscode-descriptionForeground);
    line-height: 1.4;
    padding: 1px 0;
  }
  .activity-list .ev.err { color: #f14c4c; }
  .activity-list .ev.ok { color: #4ec9b0; }

  /* ── Code / pre ── */
  .bubble pre {
    background: var(--vscode-textCodeBlock-background);
    padding: 8px 10px;
    border-radius: 8px;
    overflow-x: auto;
    font-family: var(--vscode-editor-font-family, monospace);
    font-size: 12px;
    margin: 6px 0;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .bubble code {
    font-family: var(--vscode-editor-font-family, monospace);
    font-size: 12px;
    background: var(--vscode-textCodeBlock-background);
    padding: 1px 4px;
    border-radius: 3px;
  }
  .bubble img {
    max-width: 100%;
    border-radius: 8px;
    margin-top: 8px;
  }
  .bubble ul, .bubble ol {
    margin: 4px 0 4px 18px;
  }
  .bubble li {
    margin-bottom: 2px;
  }

  /* ── Composer ── */
  .composer {
    border-top: 1px solid var(--vscode-panel-border);
    padding: 10px 12px;
    flex-shrink: 0;
  }
  .composer-box {
    display: flex;
    gap: 6px;
    align-items: flex-end;
    background: var(--vscode-input-background);
    border: 1px solid var(--vscode-input-border, var(--vscode-panel-border));
    border-radius: 12px;
    padding: 6px 8px;
  }
  .composer-box:focus-within {
    border-color: var(--vscode-focusBorder);
  }
  .composer textarea {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--vscode-input-foreground);
    font-family: inherit;
    font-size: 13px;
    resize: none;
    outline: none;
    min-height: 20px;
    max-height: 140px;
    line-height: 1.45;
    padding: 4px 2px;
  }
  .send-btn {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    border: none;
    border-radius: 8px;
    width: 32px; height: 32px;
    cursor: pointer;
    display: grid;
    place-items: center;
    flex-shrink: 0;
    font-size: 14px;
  }
  .send-btn:disabled { opacity: 0.35; cursor: default; }
  .send-btn:hover:not(:disabled) { background: var(--vscode-button-hoverBackground); }

  /* ── Composer toolbar ── */
  .composer-toolbar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 2px 2px;
    flex-wrap: wrap;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 11px;
    border: 1px solid var(--vscode-panel-border);
    background: transparent;
    color: var(--vscode-descriptionForeground);
    cursor: pointer;
    white-space: nowrap;
  }
  .chip:hover { color: var(--vscode-foreground); border-color: var(--vscode-foreground); }
  .chip.active { color: var(--vscode-foreground); border-color: var(--vscode-focusBorder); background: color-mix(in srgb, var(--vscode-focusBorder) 12%, transparent); }
  .chip .x {
    font-size: 9px;
    margin-left: 2px;
    opacity: 0.6;
  }
  .chip .x:hover { opacity: 1; }
  .chip-sep { flex: 1; }
  .file-tag {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 7px;
    border-radius: 5px;
    font-size: 10px;
    background: color-mix(in srgb, var(--vscode-focusBorder) 15%, transparent);
    color: var(--vscode-foreground);
    border: 1px solid color-mix(in srgb, var(--vscode-focusBorder) 30%, transparent);
  }
  .file-tag .x { cursor: pointer; font-size: 9px; opacity: 0.6; }
  .file-tag .x:hover { opacity: 1; }
  .attached-files { display: flex; gap: 4px; flex-wrap: wrap; padding: 4px 2px 0; }

  .composer-hint {
    font-size: 10px;
    color: var(--vscode-descriptionForeground);
    margin-top: 6px;
    text-align: center;
  }

  /* ── Confirm overlay ── */
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.4);
    display: none;
    align-items: center;
    justify-content: center;
    padding: 20px;
    z-index: 10;
  }
  .overlay.vis { display: flex; }
  .confirm-box {
    background: var(--vscode-editor-background);
    border: 1px solid var(--vscode-panel-border);
    border-radius: 12px;
    padding: 16px;
    max-width: 320px;
    width: 100%;
  }
  .confirm-box h4 { font-size: 14px; margin-bottom: 6px; }
  .confirm-box p { color: var(--vscode-descriptionForeground); line-height: 1.5; margin-bottom: 14px; }
  .confirm-btns { display: flex; gap: 8px; justify-content: flex-end; }
  .confirm-btns button {
    border-radius: 8px; padding: 6px 14px; font-size: 12px; cursor: pointer;
  }
  .cbtn-cancel {
    background: transparent; border: 1px solid var(--vscode-panel-border);
    color: var(--vscode-foreground);
  }
  .cbtn-ok {
    background: var(--vscode-button-background); border: none;
    color: var(--vscode-button-foreground);
  }
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-left">
    <div class="dot" id="dot"></div>
    <span>QaCoPilot</span>
  </div>
  <div class="topbar-right">
    <button class="tb" onclick="askClear()">Clear</button>
  </div>
</div>

<div class="thread" id="thread">
  <div class="empty-state" id="empty">
    <div class="es-icon">&#128172;</div>
    <p>Ask me to connect to a device, explore the app, generate tests, or navigate flows.</p>
  </div>
</div>

<div class="composer">
  <div class="attached-files" id="attachedFiles"></div>
  <div class="composer-box">
    <textarea id="input" placeholder="Ask anything..." rows="1"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();send();}"></textarea>
    <button class="send-btn" id="sendBtn" onclick="send()">&#8593;</button>
  </div>
  <div class="composer-toolbar">
    <button class="chip" onclick="attachFile()" title="Attach file (test plan, locators, etc.)">&#128206; Attach</button>
    <button class="chip" id="chipAgent" onclick="cycleAgent()" title="Agent type">&#9881; balanced</button>
    <button class="chip" id="chipModel" onclick="cycleModel()" title="Model">&#9733; gemini-3-flash-preview</button>
  </div>
  <div class="composer-hint">Enter to send &middot; Shift+Enter for new line</div>
</div>

<div class="overlay" id="overlay">
  <div class="confirm-box">
    <h4 id="cfTitle"></h4>
    <p id="cfBody"></p>
    <div class="confirm-btns">
      <button class="cbtn-cancel" onclick="cfClose(false)">Cancel</button>
      <button class="cbtn-ok" onclick="cfClose(true)">Continue</button>
    </div>
  </div>
</div>

<script>
  var vscode = acquireVsCodeApi();
  var thread = document.getElementById('thread');
  var empty = document.getElementById('empty');
  var input = document.getElementById('input');
  var sendBtn = document.getElementById('sendBtn');
  var dotEl = document.getElementById('dot');

  var busy = false;
  var thinkEl = null;
  var thinkStatus = null;
  var activityEvents = [];
  var cfCallback = null;
  var attachedFiles = [];
  var agentTypes = ['balanced', 'planner', 'executor'];
  var agentIdx = 0;
  var models = ['gemini-3-flash-preview', 'gemini-1.5-pro', 'neural-chat:latest'];
  var modelIdx = 0;

  function hide(el) { if (el) el.style.display = 'none'; }
  function show(el, d) { if (el) el.style.display = d || 'flex'; }
  function scrollBottom() { thread.scrollTop = thread.scrollHeight; }

  function esc(t) {
    return String(t || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderMarkdown(text) {
    var s = esc(text);
    // Code blocks
    s = s.replace(/\`\`\`(\\w*)\\n([\\s\\S]*?)\`\`\`/g, function(m, lang, code) {
      return '<pre>' + code.trim() + '</pre>';
    });
    // Inline code
    s = s.replace(/\`([^\`]+)\`/g, '<code>\$1</code>');
    // Bold
    s = s.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>\$1</strong>');
    // Bullet lists (lines starting with - or *)
    s = s.replace(/(^|\\n)[\\-\\*] (.+)/g, '\$1<li>\$2</li>');
    // Numbered lists
    s = s.replace(/(^|\\n)(\\d+)\\. (.+)/g, '\$1<li>\$3</li>');
    // Newlines
    s = s.replace(/\\n/g, '<br>');
    // Wrap consecutive li tags in ul
    s = s.replace(/(<li>.*?<\\/li>(<br>)?)+/g, function(m) {
      return '<ul>' + m.replace(/<br>/g, '') + '</ul>';
    });
    return s;
  }

  function humanize(raw) {
    if (typeof raw !== 'string') return String(raw);
    var obj;
    try { obj = JSON.parse(raw); } catch(e) { return raw; }
    if (!obj || typeof obj !== 'object') return raw;

    var parts = [];

    // Error
    if (obj.error) {
      parts.push('**Error:** ' + (obj.error || ''));
      if (obj.details) {
        var d = String(obj.details);
        parts.push('\\n' + (d.length > 300 ? d.substring(0, 300) + '...' : d));
      }
      return parts.join('');
    }

    // message
    if (obj.message) parts.push(obj.message);

    // response (if no message)
    if (obj.response && !obj.message) parts.push(obj.response);

    // Steps
    if (obj.steps && Array.isArray(obj.steps) && obj.steps.length > 0) {
      parts.push('\\n\\n**Steps executed:**');
      for (var i = 0; i < obj.steps.length; i++) {
        var s = obj.steps[i];
        parts.push('- ' + (s.action || '') + ' ' + (s.xpath || s.selector || '') + (s.reason ? ' — ' + s.reason : ''));
      }
    }

    // Test plan
    if (obj.test_plan || obj.testPlan) {
      parts.push('\\n\\n**Test Plan:**\\n' + (obj.test_plan || obj.testPlan));
    }

    // Generated code
    if (obj.code || obj.generated_code) {
      var code = obj.code || obj.generated_code;
      parts.push('\\n\`\`\`java\\n' + code + '\\n\`\`\`');
    }

    // Locators
    if (obj.locators_collected) {
      parts.push('\\nCollected **' + obj.locators_collected + '** locators.');
    }
    if (obj.locators_file) {
      parts.push('Saved to: \`' + obj.locators_file.split('/').pop() + '\`');
    }

    // Screen elements summary
    if (obj.elements && Array.isArray(obj.elements)) {
      parts.push('\\nFound **' + obj.elements.length + '** elements on screen.');
    }

    // Session / connection info
    if (obj.session_id || obj.sessionId) {
      parts.push('\\nSession: \`' + (obj.session_id || obj.sessionId) + '\`');
    }
    if (obj.device) {
      parts.push('Device: ' + obj.device);
    }

    // status field
    if (obj.status && !obj.message && !obj.response) {
      parts.push(obj.status);
    }

    if (parts.length === 0) {
      return '\`\`\`json\\n' + JSON.stringify(obj, null, 2) + '\\n\`\`\`';
    }

    return parts.join('\\n');
  }

  // ── Send message ──
  function send() {
    var text = input.value.trim();
    if (!text || busy) return;
    hide(empty);
    addTurn('user', text);
    input.value = '';
    input.style.height = 'auto';
    setBusy(true);
    showThinking();
    activityEvents = [];
    vscode.postMessage({ type: 'message', text: text, attachedFiles: attachedFiles, agentType: agentTypes[agentIdx], model: models[modelIdx] });
  }

  // ── File attachment ──
  function attachFile() {
    vscode.postMessage({ type: 'attachFile' });
  }

  function addAttachedFile(filePath) {
    if (attachedFiles.indexOf(filePath) >= 0) return;
    attachedFiles.push(filePath);
    renderAttachedFiles();
  }

  function removeAttachedFile(idx) {
    attachedFiles.splice(idx, 1);
    renderAttachedFiles();
  }

  function renderAttachedFiles() {
    var container = document.getElementById('attachedFiles');
    container.innerHTML = '';
    for (var i = 0; i < attachedFiles.length; i++) {
      var name = attachedFiles[i].split('/').pop();
      var tag = document.createElement('span');
      tag.className = 'file-tag';
      tag.innerHTML = '&#128196; ' + esc(name) + ' <span class="x" onclick="removeAttachedFile(' + i + ')">&#10005;</span>';
      container.appendChild(tag);
    }
  }

  // ── Agent type cycling ──
  function cycleAgent() {
    agentIdx = (agentIdx + 1) % agentTypes.length;
    document.getElementById('chipAgent').innerHTML = '&#9881; ' + agentTypes[agentIdx];
    vscode.postMessage({ type: 'setAgentType', value: agentTypes[agentIdx] });
  }

  // ── Model cycling ──
  function cycleModel() {
    modelIdx = (modelIdx + 1) % models.length;
    document.getElementById('chipModel').innerHTML = '&#9733; ' + models[modelIdx];
    vscode.postMessage({ type: 'setModel', value: models[modelIdx] });
  }

  function setBusy(b) {
    busy = b;
    sendBtn.disabled = b;
  }

  // ── Add a conversation turn ──
  function addTurn(role, content, extra) {
    hide(empty);
    var turn = document.createElement('div');
    turn.className = 'turn ' + role;

    var av = document.createElement('div');
    av.className = role === 'assistant' ? 'av a' : 'av u';
    av.textContent = role === 'assistant' ? 'QA' : 'U';

    var msg = document.createElement('div');
    msg.className = 'msg';

    var bubble = document.createElement('div');
    bubble.className = 'bubble';

    var displayText = content;
    if (role === 'assistant') {
      displayText = humanize(content);
    }
    bubble.innerHTML = renderMarkdown(displayText);

    if (extra && extra.image) {
      var img = document.createElement('img');
      img.src = 'data:' + (extra.image.mimeType || 'image/png') + ';base64,' + extra.image.data;
      bubble.appendChild(img);
    }

    msg.appendChild(bubble);
    turn.appendChild(av);
    turn.appendChild(msg);
    thread.appendChild(turn);
    scrollBottom();
  }

  // ── Thinking indicator ──
  function showThinking() {
    removeThinking();
    var el = document.createElement('div');
    el.className = 'thinking';
    el.innerHTML =
      '<div class="av a">QA</div>' +
      '<div class="think-body">' +
        '<div class="think-dots"><span></span><span></span><span></span></div>' +
        '<div class="think-status" id="thinkText">Working...</div>' +
      '</div>';
    thread.appendChild(el);
    thinkEl = el;
    thinkStatus = el.querySelector('#thinkText');
    scrollBottom();
  }

  function updateThinkingStatus(text) {
    if (thinkStatus) {
      thinkStatus.textContent = text;
    }
  }

  function removeThinking() {
    if (thinkEl) {
      thinkEl.remove();
      thinkEl = null;
      thinkStatus = null;
    }
  }

  // ── Collapsed activity log ──
  function addActivityLog() {
    if (activityEvents.length === 0) return;

    var wrap = document.createElement('div');
    wrap.className = 'activity-wrap';

    var toggle = document.createElement('button');
    toggle.className = 'activity-toggle';
    var label = activityEvents.length + ' step' + (activityEvents.length > 1 ? 's' : '');
    toggle.innerHTML = '<span class="arrow">&#9654;</span> ' + label;

    var list = document.createElement('div');
    list.className = 'activity-list';

    for (var i = 0; i < activityEvents.length; i++) {
      var ev = activityEvents[i];
      var d = document.createElement('div');
      d.className = 'ev';
      if (ev.kind === 'error') d.className += ' err';
      if (ev.kind === 'success') d.className += ' ok';
      d.textContent = ev.text;
      list.appendChild(d);
    }

    toggle.onclick = function() {
      toggle.classList.toggle('open');
      list.classList.toggle('open');
    };

    wrap.appendChild(toggle);
    wrap.appendChild(list);
    thread.appendChild(wrap);
    activityEvents = [];
    scrollBottom();
  }

  // ── Clear chat ──
  function askClear() {
    cfCallback = function() {
      thread.innerHTML = '';
      show(empty, 'flex');
      vscode.postMessage({ type: 'clear' });
    };
    document.getElementById('cfTitle').textContent = 'Clear conversation?';
    document.getElementById('cfBody').textContent = 'This resets the chat thread and the backend session.';
    document.getElementById('overlay').classList.add('vis');
  }

  function cfClose(ok) {
    document.getElementById('overlay').classList.remove('vis');
    if (ok && cfCallback) cfCallback();
    cfCallback = null;
  }

  // ── Handle extension messages ──
  window.addEventListener('message', function(event) {
    var msg = event.data;
    switch (msg.type) {
      case 'response':
        removeThinking();
        addActivityLog();
        addTurn('assistant', msg.message, msg);
        setBusy(false);
        break;

      case 'chat_response':
        // Show conversational messages from the agent inline in the activity log
        updateThinkingStatus(msg.message || 'Processing...');
        activityEvents.push({ kind: 'chat', text: msg.message || '' });
        break;

      case 'status':
      case 'progress':
      case 'understanding':
      case 'intent':
        updateThinkingStatus(msg.message || '');
        activityEvents.push({ kind: msg.type, text: msg.message || '' });
        break;

      case 'warning':
        updateThinkingStatus(msg.message || '');
        activityEvents.push({ kind: 'warning', text: msg.message || '' });
        break;

      case 'success':
        updateThinkingStatus(msg.message || '');
        activityEvents.push({ kind: 'success', text: msg.message || '' });
        break;

      case 'action':
      case 'step':
        activityEvents.push({ kind: 'action', text: msg.message || '' });
        break;

      case 'error':
        removeThinking();
        addActivityLog();
        addTurn('assistant', '**Error:** ' + (msg.message || 'Unknown error'));
        setBusy(false);
        break;

      case 'fileAttached':
        addAttachedFile(msg.filePath);
        break;

      case 'configUpdate':
        if (msg.agentType) {
          var ai = agentTypes.indexOf(msg.agentType);
          if (ai >= 0) { agentIdx = ai; document.getElementById('chipAgent').innerHTML = '&#9881; ' + agentTypes[agentIdx]; }
        }
        if (msg.model) {
          var mi = models.indexOf(msg.model);
          if (mi >= 0) { modelIdx = mi; document.getElementById('chipModel').innerHTML = '&#9733; ' + models[modelIdx]; }
        }
        break;

      case 'connected':
        dotEl.className = 'dot on';
        break;

      case 'disconnected':
        dotEl.className = 'dot off';
        break;

      case 'chatCleared':
        thread.innerHTML = '';
        show(empty, 'flex');
        setBusy(false);
        break;
    }
  });

  // Auto-resize textarea
  input.addEventListener('input', function() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 140) + 'px';
  });

  input.focus();
</script>
</body>
</html>`;
}

module.exports = { getChatHtml };
