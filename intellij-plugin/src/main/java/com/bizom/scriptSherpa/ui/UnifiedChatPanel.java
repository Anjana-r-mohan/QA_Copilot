package com.bizom.scriptSherpa.ui;

import com.bizom.scriptSherpa.backend.BackendConnector;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.fileEditor.FileEditorManager;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.vfs.VirtualFile;
import com.intellij.util.ui.UIUtil;
import com.intellij.ui.JBColor;
import com.intellij.ui.components.JBPanel;
import com.intellij.ui.components.JBScrollPane;
import com.intellij.ui.components.JBTextArea;

import javax.swing.*;
import java.awt.*;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public class UnifiedChatPanel extends JBPanel<UnifiedChatPanel> {
    private static final Logger LOG = Logger.getInstance(UnifiedChatPanel.class);
    private static final DateTimeFormatter TIME_FORMAT = DateTimeFormatter.ofPattern("HH:mm");

    private static final String DEVICE_NAME = "127.0.0.1:6555";
    private static final String APP_PACKAGE = "co.bizom.apps";
    private static final String APP_ACTIVITY = ".android.MainActivity";
    private static final String FALLBACK_WORKSPACE_PATH = ".";

    private final Project project;
    private final BackendConnector backendConnector;

    private final JComboBox<String> contextModeCombo;
    private final JComboBox<String> agentTypeCombo;
    private final JComboBox<String> modelCombo;

    private final JLabel statusLabel;
    private final JLabel sessionLabel;
    private final JLabel attachmentsLabel;
    private final JButton contextChipButton;
    private final JButton agentChipButton;
    private final JButton modelChipButton;

    private final JEditorPane chatPane;
    private final JBTextArea inputArea;

    private final List<String> attachedFiles = new ArrayList<>();
    private final List<ChatEntry> chatHistory = new ArrayList<>();

    private final Gson gson = new GsonBuilder().setPrettyPrinting().create();

    private final String workspacePath;
    private String sessionId;

    public UnifiedChatPanel(Project project) {
        this.project = project;
        this.backendConnector = new BackendConnector();
        this.workspacePath = project != null && project.getBasePath() != null
            ? project.getBasePath()
            : FALLBACK_WORKSPACE_PATH;
        this.sessionId = UUID.randomUUID().toString();

        setLayout(new BorderLayout());
        setBackground(new JBColor(new Color(242, 245, 249), new Color(43, 45, 51)));

        JPanel topContainer = new JPanel(new BorderLayout());
        topContainer.setOpaque(true);
        topContainer.setBackground(new JBColor(new Color(255, 255, 255), new Color(58, 63, 71)));
        topContainer.setBorder(BorderFactory.createEmptyBorder(8, 10, 4, 10));

        JPanel titlePanel = new JPanel(new BorderLayout());
        titlePanel.setOpaque(false);
        JLabel title = new JLabel("ScriptSherpa Copilot");
        title.setFont(title.getFont().deriveFont(Font.BOLD, 15f));
        statusLabel = new JLabel("Ready");
        statusLabel.setOpaque(true);
        statusLabel.setBorder(BorderFactory.createEmptyBorder(4, 10, 4, 10));
        statusLabel.setBackground(new JBColor(new Color(223, 242, 230), new Color(39, 76, 56)));
        statusLabel.setForeground(new JBColor(new Color(24, 95, 50), new Color(141, 232, 175)));
        titlePanel.add(title, BorderLayout.WEST);
        titlePanel.add(statusLabel, BorderLayout.EAST);

        contextModeCombo = new JComboBox<>(new String[]{"workspace", "current_file", "selection"});
        styleCombo(contextModeCombo);
        contextModeCombo.addActionListener(e -> {
            refreshChipLabels();
            persistState();
        });

        agentTypeCombo = new JComboBox<>(new String[]{"balanced", "planner", "executor"});
        styleCombo(agentTypeCombo);
        agentTypeCombo.addActionListener(e -> {
            refreshChipLabels();
            persistState();
        });

        modelCombo = new JComboBox<>(new String[]{
            "auto",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-pro",
            "neural-chat",
            "llama3"
        });
        styleCombo(modelCombo);
        modelCombo.addActionListener(e -> {
            refreshChipLabels();
            persistState();
        });

        sessionLabel = new JLabel();
        attachmentsLabel = new JLabel();
        sessionLabel.setForeground(new JBColor(new Color(64, 74, 90), new Color(165, 173, 189)));
        attachmentsLabel.setForeground(new JBColor(new Color(64, 74, 90), new Color(165, 173, 189)));

        topContainer.add(titlePanel, BorderLayout.NORTH);
        add(topContainer, BorderLayout.NORTH);

        chatPane = new JEditorPane();
        chatPane.setEditable(false);
        chatPane.setContentType("text/html");
        chatPane.setBackground(new JBColor(new Color(242, 245, 249), new Color(43, 45, 51)));
        chatPane.putClientProperty(JEditorPane.HONOR_DISPLAY_PROPERTIES, Boolean.TRUE);

        add(new JBScrollPane(chatPane), BorderLayout.CENTER);

        JPanel bottomPanel = new JPanel(new BorderLayout(8, 8));
        bottomPanel.setOpaque(true);
        bottomPanel.setBackground(new JBColor(new Color(242, 245, 249), new Color(43, 45, 51)));
        bottomPanel.setBorder(BorderFactory.createEmptyBorder(6, 10, 10, 10));

        JPanel composerCard = new JPanel(new BorderLayout(8, 8));
        composerCard.setOpaque(true);
        composerCard.setBackground(new JBColor(new Color(255, 255, 255), new Color(58, 63, 71)));
        composerCard.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(new JBColor(new Color(210, 217, 228), new Color(76, 82, 93))),
            BorderFactory.createEmptyBorder(8, 8, 8, 8)
        ));

        JPanel composerControls = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 2));
        composerControls.setOpaque(false);
        contextChipButton = createChipButton("#", "Context mode");
        contextChipButton.addActionListener(e -> showSelectionMenu(contextChipButton, contextModeCombo));
        composerControls.add(contextChipButton);

        agentChipButton = createChipButton("🤖", "Agent type");
        agentChipButton.addActionListener(e -> showSelectionMenu(agentChipButton, agentTypeCombo));
        composerControls.add(agentChipButton);

        modelChipButton = createChipButton("⚙", "Model");
        modelChipButton.addActionListener(e -> showSelectionMenu(modelChipButton, modelCombo));
        composerControls.add(modelChipButton);

        JButton attachButton = new JButton("📎");
        styleButton(attachButton, false);
        attachButton.setToolTipText("Attach files");
        attachButton.addActionListener(e -> attachFiles());
        composerControls.add(attachButton);

        JButton clearAttachButton = new JButton("✕");
        styleButton(clearAttachButton, false);
        clearAttachButton.setToolTipText("Clear attachments");
        clearAttachButton.addActionListener(e -> {
            attachedFiles.clear();
            refreshAttachmentsLabel();
            persistState();
        });
        composerControls.add(clearAttachButton);

        JButton newSessionButton = new JButton("↻");
        styleButton(newSessionButton, false);
        newSessionButton.setToolTipText("Start new session");
        newSessionButton.addActionListener(e -> startNewSession());
        composerControls.add(newSessionButton);

        inputArea = new JBTextArea();
        inputArea.setRows(4);
        inputArea.setLineWrap(true);
        inputArea.setWrapStyleWord(true);
        inputArea.setText("Ask, attach context, and drive the app flow...");
        inputArea.setForeground(new JBColor(new Color(112, 120, 136), new Color(167, 175, 193)));
        inputArea.setBackground(new JBColor(new Color(255, 255, 255), new Color(58, 63, 71)));
        inputArea.setBorder(BorderFactory.createEmptyBorder(4, 6, 4, 6));
        inputArea.addFocusListener(new java.awt.event.FocusAdapter() {
            @Override
            public void focusGained(java.awt.event.FocusEvent evt) {
                if ("Ask, attach context, and drive the app flow...".equals(inputArea.getText())) {
                    inputArea.setText("");
                    inputArea.setForeground(new JBColor(new Color(30, 36, 48), new Color(231, 236, 247)));
                }
            }

            @Override
            public void focusLost(java.awt.event.FocusEvent evt) {
                if (inputArea.getText().trim().isEmpty()) {
                    inputArea.setText("Ask, attach context, and drive the app flow...");
                    inputArea.setForeground(new JBColor(new Color(112, 120, 136), new Color(141, 151, 171)));
                }
            }
        });

        inputArea.getInputMap().put(KeyStroke.getKeyStroke("ENTER"), "send");
        inputArea.getActionMap().put("send", new AbstractAction() {
            @Override
            public void actionPerformed(java.awt.event.ActionEvent e) {
                sendMessage();
            }
        });
        inputArea.getInputMap().put(KeyStroke.getKeyStroke("shift ENTER"), "insert-break");
        inputArea.getActionMap().put("insert-break", new AbstractAction() {
            @Override
            public void actionPerformed(java.awt.event.ActionEvent e) {
                inputArea.append("\n");
            }
        });

        JButton sendButton = new JButton("Send ->");
        styleButton(sendButton, true);
        sendButton.setPreferredSize(new Dimension(90, 42));
        sendButton.addActionListener(e -> sendMessage());

        JPanel controlsAndSend = new JPanel(new BorderLayout(8, 0));
        controlsAndSend.setOpaque(false);
        controlsAndSend.setBorder(BorderFactory.createEmptyBorder(4, 0, 0, 0));
        controlsAndSend.add(composerControls, BorderLayout.CENTER);
        controlsAndSend.add(sendButton, BorderLayout.EAST);

        JPanel metaRow = new JPanel(new GridLayout(2, 1));
        metaRow.setOpaque(false);
        metaRow.setBorder(BorderFactory.createEmptyBorder(4, 2, 0, 2));
        metaRow.add(sessionLabel);
        metaRow.add(attachmentsLabel);

        JPanel composerFooter = new JPanel(new BorderLayout());
        composerFooter.setOpaque(false);
        composerFooter.add(controlsAndSend, BorderLayout.NORTH);
        composerFooter.add(metaRow, BorderLayout.SOUTH);

        composerCard.add(new JBScrollPane(inputArea), BorderLayout.CENTER);
        composerCard.add(composerFooter, BorderLayout.SOUTH);
        bottomPanel.add(composerCard, BorderLayout.CENTER);

        add(bottomPanel, BorderLayout.SOUTH);

        restoreState();
        removeDefaultStartupNoise();
        refreshSessionLabel();
        refreshAttachmentsLabel();
        refreshChipLabels();
        renderChat();

        LOG.info("UnifiedChatPanel initialized with persisted session support");
    }

    private void startNewSession() {
        sessionId = UUID.randomUUID().toString();
        chatHistory.clear();
        addTimeline("system", "Started a new session.");
        refreshSessionLabel();
        persistState();
    }

    private void attachFiles() {
        JFileChooser chooser = new JFileChooser();
        chooser.setMultiSelectionEnabled(true);
        chooser.setDialogTitle("Attach context files");
        int result = chooser.showOpenDialog(this);
        if (result == JFileChooser.APPROVE_OPTION) {
            for (File file : chooser.getSelectedFiles()) {
                if (file != null && file.exists()) {
                    String absolutePath = file.getAbsolutePath();
                    if (!attachedFiles.contains(absolutePath)) {
                        attachedFiles.add(absolutePath);
                    }
                }
            }
            addTimeline("context", "Attached " + chooser.getSelectedFiles().length + " file(s)");
            refreshAttachmentsLabel();
            persistState();
        }
    }

    private void sendMessage() {
        try {
            String userMessage = inputArea.getText().trim();
            if (userMessage.isEmpty() || "Ask, attach context, and drive the app flow...".equals(userMessage)) {
                return;
            }

            String contextMode = (String) contextModeCombo.getSelectedItem();
            String contextInjection = buildContextInjection(contextMode);
            String finalMessage = userMessage + (contextInjection.isEmpty() ? "" : "\n\n" + contextInjection);

            addBubble("user", userMessage);
            addTimeline("progress", "Processing your request...");
            if (!contextInjection.isEmpty()) {
                if (contextInjection.startsWith("[CONTEXT selection")) {
                    addTimeline("context", "Using selected editor context for planning and generation.");
                } else if (contextInjection.startsWith("[CONTEXT current_file=")) {
                    String currentFilePath = contextInjection
                        .replace("[CONTEXT current_file=", "")
                        .replace("]", "")
                        .trim();
                    String currentFileName = new File(currentFilePath).getName();
                    addTimeline("context", "Using current file context for planning and generation: " + currentFileName);
                }
            } else if ("selection".equals(contextMode)) {
                addTimeline("warning", "Selection mode is on, but no editor context was available. Highlight text or keep the target file focused.");
            }

            statusLabel.setText("Working...");
            statusLabel.setBackground(new JBColor(new Color(230, 238, 255), new Color(54, 72, 105)));
            statusLabel.setForeground(new JBColor(new Color(28, 65, 133), new Color(188, 212, 255)));
            inputArea.setText("");
            inputArea.setForeground(new JBColor(new Color(30, 36, 48), new Color(231, 236, 247)));

            BackendConnector.ChatOptions options = new BackendConnector.ChatOptions(
                (String) agentTypeCombo.getSelectedItem(),
                normalizeModel((String) modelCombo.getSelectedItem()),
                contextMode,
                new ArrayList<>(attachedFiles)
            );

            persistState();

            new Thread(() -> {
                try {
                    backendConnector.sendUnifiedChatMessage(
                        finalMessage,
                        DEVICE_NAME,
                        APP_PACKAGE,
                        APP_ACTIVITY,
                        workspacePath,
                        sessionId,
                        options,
                        progress -> SwingUtilities.invokeLater(() -> handleProgress(progress))
                    );
                } catch (Exception exc) {
                    LOG.error("Unified chat call failed", exc);
                    SwingUtilities.invokeLater(() -> {
                        addTimeline("error", "Request failed: " + exc.getMessage());
                        statusLabel.setText("Error");
                        statusLabel.setBackground(new JBColor(new Color(255, 233, 232), new Color(95, 45, 45)));
                        statusLabel.setForeground(new JBColor(new Color(150, 27, 27), new Color(255, 194, 194)));
                        persistState();
                    });
                }
            }, "script-sherpa-send").start();
        } catch (Exception exc) {
            LOG.error("Send action failed", exc);
            addTimeline("error", "Could not send message: " + exc.getMessage());
            statusLabel.setText("Error");
            statusLabel.setBackground(new JBColor(new Color(255, 233, 232), new Color(95, 45, 45)));
            statusLabel.setForeground(new JBColor(new Color(150, 27, 27), new Color(255, 194, 194)));
        }
    }

    private String normalizeModel(String model) {
        if (model == null || "auto".equalsIgnoreCase(model)) {
            return null;
        }
        return model;
    }

    private String buildContextInjection(String contextMode) {
        if (project == null) {
            return "";
        }

        if ("current_file".equals(contextMode)) {
            VirtualFile[] selectedFiles = FileEditorManager.getInstance(project).getSelectedFiles();
            if (selectedFiles.length > 0) {
                return "[CONTEXT current_file=" + selectedFiles[0].getPath() + "]";
            }
            return "";
        }

        if ("selection".equals(contextMode)) {
            Editor editor = FileEditorManager.getInstance(project).getSelectedTextEditor();
            if (editor != null) {
                String selectedText = editor.getSelectionModel().getSelectedText();
                if (selectedText != null && !selectedText.trim().isEmpty()) {
                    String clipped = selectedText.length() > 1200 ? selectedText.substring(0, 1200) : selectedText;
                    return "[CONTEXT selection]\n" + clipped;
                }

                String documentText = editor.getDocument().getText();
                if (documentText != null && !documentText.trim().isEmpty()) {
                    int offset = editor.getCaretModel().getOffset();
                    int start = Math.max(0, offset - 600);
                    int end = Math.min(documentText.length(), offset + 600);
                    String snippet = documentText.substring(start, end).trim();
                    if (!snippet.isEmpty()) {
                        return "[CONTEXT selection]\n" + snippet;
                    }
                }
            }
            return "";
        }

        return "";
    }

    private void handleProgress(BackendConnector.ProgressUpdate update) {
        String type = update.type == null ? "progress" : update.type;
        String message = update.message == null ? "" : update.message;

        switch (type) {
            case "understanding":
            case "intent":
            case "progress":
            case "step":
            case "success":
            case "warning":
                if (!message.isEmpty()) {
                    addTimeline(type, message);
                }
                break;
            case "chat_response":
                if (!message.isEmpty()) {
                    addBubble("assistant", message);
                }
                break;
            case "error":
                addTimeline("error", message.isEmpty() ? "Unknown error" : message);
                statusLabel.setText("Error");
                break;
            case "complete":
                boolean completedSuccessfully = handleComplete(update.data);
                if (completedSuccessfully) {
                    statusLabel.setText("Ready");
                    statusLabel.setBackground(new JBColor(new Color(223, 242, 230), new Color(39, 76, 56)));
                    statusLabel.setForeground(new JBColor(new Color(24, 95, 50), new Color(141, 232, 175)));
                } else {
                    statusLabel.setText("Error");
                    statusLabel.setBackground(new JBColor(new Color(255, 233, 232), new Color(95, 45, 45)));
                    statusLabel.setForeground(new JBColor(new Color(150, 27, 27), new Color(255, 194, 194)));
                }
                break;
            case "keepalive":
                return;
            default:
                if (!message.isEmpty()) {
                    addTimeline("progress", message);
                }
        }

        persistState();
    }

    private boolean handleComplete(JsonObject eventData) {
        if (eventData != null && eventData.has("result") && eventData.get("result").isJsonObject()) {
            JsonObject result = eventData.getAsJsonObject("result");
            boolean success = !result.has("success") || result.get("success").getAsBoolean();

            int steps = result.has("steps_executed") ? result.get("steps_executed").getAsInt() : 0;
            int locators = result.has("locators_collected") ? result.get("locators_collected").getAsInt() : 0;
            String file = result.has("locators_file") ? result.get("locators_file").getAsString() : "";

            if ((steps == 0 && locators == 0) && result.has("exploration") && result.get("exploration").isJsonObject()) {
                JsonObject exploration = result.getAsJsonObject("exploration");
                steps = exploration.has("steps_executed") ? exploration.get("steps_executed").getAsInt() : 0;
                locators = exploration.has("locators_collected") ? exploration.get("locators_collected").getAsInt() : 0;
                file = exploration.has("locators_file") ? exploration.get("locators_file").getAsString() : file;
            }

            String summary;
            if (success) {
                summary = "Completed";
                if (steps > 0 || locators > 0) {
                    summary = "Completed " + steps + " steps and collected " + locators + " locators";
                }
                if (file != null && !file.isEmpty()) {
                    summary += " | " + file;
                }
                addTimeline("complete", summary);
            } else {
                String error = result.has("error") ? result.get("error").getAsString() : "Execution failed";
                String details = result.has("details") ? result.get("details").getAsString() : "";
                summary = "Failed: " + error + (details.isEmpty() ? "" : " | " + details);
                addTimeline("error", summary);
            }

            if (result.has("message") && !result.get("message").isJsonNull()) {
                String assistantMessage = result.get("message").getAsString();
                if (!assistantMessage.trim().isEmpty()) {
                    addBubble("assistant", assistantMessage);
                }
            }
            return success;
        }
        addTimeline("complete", "Completed.");
        return true;
    }

    private void addBubble(String role, String content) {
        chatHistory.add(new ChatEntry(role, content, now(), "bubble"));
        renderChat();
    }

    private void addTimeline(String type, String content) {
        chatHistory.add(new ChatEntry(type, content, now(), "timeline"));
        renderChat();
    }

    private String now() {
        return LocalDateTime.now().format(TIME_FORMAT);
    }

    private void renderChat() {
        boolean dark = UIUtil.isUnderDarcula();
        String bodyBg = dark ? "#2B2D33" : "#F2F5F9";
        String textColor = dark ? "#D8DEE9" : "#1F2937";
        String userBubbleBg = dark ? "#365880" : "#3574F0";
        String userBubbleText = "#FFFFFF";
        String assistantBubbleBg = dark ? "#3A3F47" : "#FFFFFF";
        String assistantBubbleText = dark ? "#E5EAF3" : "#111827";
        String bubbleBorder = dark ? "#515865" : "#D2DAE6";
        String metaColor = dark ? "#9AA4B5" : "#5F6B81";
        String cardBg = dark ? "#31363F" : "#FFFFFF";

        StringBuilder html = new StringBuilder();
        html.append("<html><head><style>")
            .append("body{font-family:SansSerif;margin:0;padding:14px;background-color:").append(bodyBg)
            .append(";color:").append(textColor).append(";}")
            .append(".row{margin:10px 0;}")
            .append(".bubble{padding:10px 12px;display:inline-block;line-height:1.45;}")
            .append(".user{background-color:").append(userBubbleBg).append(";color:").append(userBubbleText).append(";margin-left:18%;}")
            .append(".assistant{background-color:").append(assistantBubbleBg).append(";color:").append(assistantBubbleText)
            .append(";border:1px solid ").append(bubbleBorder).append(";}")
            .append(".meta{font-size:11px;color:").append(metaColor).append(";margin-top:3px;}")
            .append(".card{border-left:4px solid #4A88E8;background-color:").append(cardBg).append(";padding:9px 11px;")
            .append("margin:8px 0;line-height:1.35;}")
            .append(".card.success{border-left-color:#4A9E50;}")
            .append(".card.warning{border-left-color:#CC8A2E;}")
            .append(".card.error{border-left-color:#CF5B56;}")
            .append(".card.complete{border-left-color:#4C9A91;}")
            .append(".card.intent{border-left-color:#6184D8;}")
            .append("</style></head><body>");

        if (chatHistory.isEmpty()) {
            html.append("<div class='row'><div class='card intent'>Start by asking a goal: explore a screen, continue a flow, or generate tests.</div></div>");
        }

        for (ChatEntry entry : chatHistory) {
            if ("bubble".equals(entry.kind)) {
                String bubbleClass = "assistant";
                if ("user".equals(entry.role)) {
                    bubbleClass = "user";
                }
                String label = "user".equals(entry.role) ? "You" : "ScriptSherpa";
                html.append("<div class='row'>")
                    .append("<div class='bubble ").append(bubbleClass).append("'>")
                    .append(escapeHtml(entry.content))
                    .append("</div>")
                    .append("<div class='meta'>")
                    .append(label).append(" · ").append(escapeHtml(entry.time))
                    .append("</div>")
                    .append("</div>");
            } else {
                String cardClass = "card";
                if ("success".equals(entry.role)) cardClass += " success";
                if ("warning".equals(entry.role)) cardClass += " warning";
                if ("error".equals(entry.role)) cardClass += " error";
                if ("complete".equals(entry.role)) cardClass += " complete";
                if ("intent".equals(entry.role)) cardClass += " intent";
                html.append("<div class='row'>")
                    .append("<div class='").append(cardClass).append("'>")
                    .append(escapeHtml(entry.content))
                    .append("</div>")
                    .append("</div>");
            }
        }

        html.append("</body></html>");

        try {
            chatPane.setText(html.toString());
            chatPane.setCaretPosition(chatPane.getDocument().getLength());
        } catch (Exception renderEx) {
            LOG.warn("Failed rich chat render; falling back to minimal markup", renderEx);
            String fallback = "<html><body style='font-family:SansSerif;padding:10px;'>"
                + "<div>ScriptSherpa chat view is running with safe mode rendering.</div>"
                + "</body></html>";
            chatPane.setText(fallback);
            chatPane.setCaretPosition(chatPane.getDocument().getLength());
        }
    }

    private String escapeHtml(String input) {
        if (input == null) return "";
        return input
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("\n", "<br/>");
    }

    private void refreshSessionLabel() {
        sessionLabel.setText("Session: " + sessionId + " | Workspace: " + workspacePath);
    }

    private JLabel makeControlLabel(String text) {
        JLabel label = new JLabel(text);
        label.setForeground(new JBColor(new Color(77, 89, 109), new Color(171, 182, 202)));
        return label;
    }

    private JButton createChipButton(String text, String tooltip) {
        JButton button = new JButton(text);
        styleChipButton(button, false);
        button.setToolTipText(tooltip);
        button.putClientProperty("JButton.buttonType", "roundRect");
        return button;
    }

    private void showSelectionMenu(JButton invoker, JComboBox<String> combo) {
        JPopupMenu menu = new JPopupMenu();
        ComboBoxModel<String> model = combo.getModel();
        for (int i = 0; i < model.getSize(); i++) {
            String value = model.getElementAt(i);
            JMenuItem item = new JMenuItem(value);
            item.addActionListener(e -> combo.setSelectedItem(value));
            menu.add(item);
        }
        menu.show(invoker, 0, invoker.getHeight());
    }

    private void refreshChipLabels() {
        contextChipButton.setText("# " + contextShort((String) contextModeCombo.getSelectedItem()));
        agentChipButton.setText("🤖 " + agentShort((String) agentTypeCombo.getSelectedItem()));
        modelChipButton.setText("⚙ " + modelShort((String) modelCombo.getSelectedItem()));

        boolean contextActive = !"workspace".equals(contextModeCombo.getSelectedItem());
        boolean agentActive = !"balanced".equals(agentTypeCombo.getSelectedItem());
        boolean modelActive = !"auto".equals(modelCombo.getSelectedItem());

        styleChipButton(contextChipButton, contextActive);
        styleChipButton(agentChipButton, agentActive);
        styleChipButton(modelChipButton, modelActive);
    }

    private void removeDefaultStartupNoise() {
        chatHistory.removeIf(entry ->
            entry != null
                && "timeline".equals(entry.kind)
                && entry.content != null
                && (
                    entry.content.startsWith("Copilot session started.")
                    || entry.content.startsWith("Started a new session.")
                )
        );
    }

    private String contextShort(String value) {
        if ("current_file".equals(value)) return "File";
        if ("selection".equals(value)) return "Sel";
        return "WS";
    }

    private String agentShort(String value) {
        if ("planner".equals(value)) return "Plan";
        if ("executor".equals(value)) return "Exec";
        return "Bal";
    }

    private String modelShort(String value) {
        if (value == null || "auto".equals(value)) return "Auto";
        if (value.startsWith("gemini-1.5-pro")) return "G-Pro";
        if (value.startsWith("gemini-1.5-flash")) return "G-Flash";
        if (value.startsWith("gemini")) return "Gemini";
        if (value.startsWith("neural")) return "Neural";
        if (value.startsWith("llama3")) return "Llama3";
        return value;
    }

    private void styleChipButton(JButton button, boolean active) {
        button.setFocusPainted(false);
        button.setFont(button.getFont().deriveFont(Font.PLAIN, 12f));
        if (active) {
            button.setBackground(new JBColor(new Color(227, 237, 252), new Color(69, 91, 122)));
            button.setForeground(new JBColor(new Color(32, 77, 142), new Color(219, 231, 247)));
            button.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(new JBColor(new Color(165, 192, 228), new Color(97, 120, 150))),
                BorderFactory.createEmptyBorder(5, 9, 5, 9)
            ));
        } else {
            button.setBackground(new JBColor(new Color(250, 252, 255), new Color(64, 69, 78)));
            button.setForeground(new JBColor(new Color(59, 73, 96), new Color(206, 214, 227)));
            button.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(new JBColor(new Color(211, 219, 232), new Color(92, 100, 114))),
                BorderFactory.createEmptyBorder(5, 9, 5, 9)
            ));
        }
    }

    private void styleCombo(JComboBox<String> combo) {
        combo.setBackground(new JBColor(new Color(255, 255, 255), new Color(58, 63, 71)));
        combo.setForeground(new JBColor(new Color(30, 36, 48), new Color(228, 234, 245)));
        combo.setBorder(BorderFactory.createCompoundBorder(
            BorderFactory.createLineBorder(new JBColor(new Color(205, 214, 228), new Color(88, 95, 108))),
            BorderFactory.createEmptyBorder(2, 6, 2, 6)
        ));
    }

    private void styleButton(JButton button, boolean primary) {
        button.putClientProperty("JButton.buttonType", "roundRect");
        button.setFont(button.getFont().deriveFont(Font.PLAIN, 12f));
        if (primary) {
            button.setBackground(new JBColor(new Color(53, 116, 240), new Color(74, 124, 214)));
            button.setForeground(Color.WHITE);
            button.setBorder(BorderFactory.createEmptyBorder(7, 12, 7, 12));
        } else {
            button.setBackground(new JBColor(new Color(250, 252, 255), new Color(64, 69, 78)));
            button.setForeground(new JBColor(new Color(36, 46, 62), new Color(214, 223, 238)));
            button.setBorder(BorderFactory.createCompoundBorder(
                BorderFactory.createLineBorder(new JBColor(new Color(211, 220, 233), new Color(91, 99, 114))),
                BorderFactory.createEmptyBorder(5, 10, 5, 10)
            ));
        }
        button.setFocusPainted(false);
    }

    private void refreshAttachmentsLabel() {
        if (attachedFiles.isEmpty()) {
            attachmentsLabel.setText("Attachments: none");
        } else {
            attachmentsLabel.setText("Attachments: " + attachedFiles.size() + " file(s)");
        }
    }

    private File getStateFile() {
        File dir = new File(workspacePath, ".scriptSherpa");
        if (!dir.exists()) {
            dir.mkdirs();
        }
        return new File(dir, "unified_chat_state.json");
    }

    private void persistState() {
        try {
            PersistedState state = new PersistedState();
            state.sessionId = sessionId;
            state.contextMode = (String) contextModeCombo.getSelectedItem();
            state.agentType = (String) agentTypeCombo.getSelectedItem();
            state.model = (String) modelCombo.getSelectedItem();
            state.attachedFiles = new ArrayList<>(attachedFiles);
            state.chatHistory = new ArrayList<>(chatHistory);

            File stateFile = getStateFile();
            Files.writeString(stateFile.toPath(), gson.toJson(state), StandardCharsets.UTF_8);
        } catch (Exception exc) {
            LOG.warn("Failed to persist chat state", exc);
        }
    }

    private void restoreState() {
        try {
            File stateFile = getStateFile();
            if (!stateFile.exists()) {
                return;
            }

            String content = Files.readString(stateFile.toPath(), StandardCharsets.UTF_8);
            PersistedState state = gson.fromJson(content, PersistedState.class);
            if (state == null) {
                return;
            }

            if (state.sessionId != null && !state.sessionId.isEmpty()) {
                sessionId = state.sessionId;
            }
            if (state.contextMode != null) {
                contextModeCombo.setSelectedItem(state.contextMode);
            }
            if (state.agentType != null) {
                agentTypeCombo.setSelectedItem(state.agentType);
            }
            if (state.model != null) {
                modelCombo.setSelectedItem(state.model);
            }

            attachedFiles.clear();
            if (state.attachedFiles != null) {
                attachedFiles.addAll(state.attachedFiles);
            }

            chatHistory.clear();
            if (state.chatHistory != null) {
                chatHistory.addAll(state.chatHistory);
            }
        } catch (Exception exc) {
            LOG.warn("Failed to restore chat state", exc);
        }
    }

    public static class ChatEntry {
        public String role;
        public String content;
        public String time;
        public String kind;

        public ChatEntry() {}

        public ChatEntry(String role, String content, String time, String kind) {
            this.role = role;
            this.content = content;
            this.time = time;
            this.kind = kind;
        }
    }

    public static class PersistedState {
        public String sessionId;
        public String contextMode;
        public String agentType;
        public String model;
        public List<String> attachedFiles;
        public List<ChatEntry> chatHistory;
    }
}
