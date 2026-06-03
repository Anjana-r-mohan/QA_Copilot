package com.bizom.qaCopilot.ui;

import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.project.Project;
import com.intellij.ui.components.JBPanel;
import com.intellij.ui.components.JBScrollPane;
import com.intellij.ui.components.JBTextArea;
import com.bizom.qaCopilot.backend.BackendConnector;

import javax.swing.*;
import javax.swing.filechooser.FileNameExtensionFilter;
import java.awt.*;
import java.io.File;

public class QACopilotPanel extends JBPanel<QACopilotPanel> {
    private static final Logger LOG = Logger.getInstance(QACopilotPanel.class);
    
    private final Project project;
    private final JBTextArea chatArea;
    private final JBTextArea inputArea;
    private final BackendConnector backendConnector;
    private final JLabel selectedContextLabel;
    private String selectedTestPlanPath = "";
    private String selectedCsvPath = "";
    
    // Hidden configuration (hardcoded defaults)
    private static final String DEVICE_NAME = "127.0.0.1:6555";
    private static final String APP_PACKAGE = "co.bizom.apps";
    private static final String APP_ACTIVITY = ".android.MainActivity";
    private static final String WORKSPACE_PATH = "/Users/anjana.mohan/KMMAuto_demo";

    public QACopilotPanel(Project project) {
        this.project = project;
        this.backendConnector = new BackendConnector();
        setLayout(new BorderLayout());

        // Top: File Selection Only (Clean, Simple UI)
        JPanel topPanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 5, 5));
        
        JButton pickTestPlanBtn = new JButton("📋 Test Plan");
        pickTestPlanBtn.setPreferredSize(new Dimension(120, 30));
        pickTestPlanBtn.addActionListener(e -> selectTestPlan());
        topPanel.add(pickTestPlanBtn);
        
        JButton pickCsvBtn = new JButton("📄 CSV");
        pickCsvBtn.setPreferredSize(new Dimension(100, 30));
        pickCsvBtn.addActionListener(e -> selectCSV());
        topPanel.add(pickCsvBtn);
        
        selectedContextLabel = new JLabel("📌 No files selected");
        selectedContextLabel.setFont(selectedContextLabel.getFont().deriveFont(Font.ITALIC, 11));
        selectedContextLabel.setForeground(new Color(100, 120, 140));
        topPanel.add(selectedContextLabel);
        
        add(topPanel, BorderLayout.NORTH);

        // Middle: Chat Display
        chatArea = new JBTextArea();
        chatArea.setEditable(false);
        chatArea.setLineWrap(true);
        chatArea.setWrapStyleWord(true);
        chatArea.setText("👋 Welcome to QA Copilot!\n\nClick 📋 or 📄 to select context files, then type your command.\n\n");
        JBScrollPane chatScroll = new JBScrollPane(chatArea);
        add(chatScroll, BorderLayout.CENTER);

        // Bottom: Input Area
        JPanel bottomPanel = new JPanel(new BorderLayout());
        inputArea = new JBTextArea();
        inputArea.setRows(3);
        inputArea.setLineWrap(true);
        inputArea.setWrapStyleWord(true);
        bottomPanel.add(new JBScrollPane(inputArea), BorderLayout.CENTER);

        JButton sendButton = new JButton("Send");
        sendButton.addActionListener(e -> sendMessage());
        bottomPanel.add(sendButton, BorderLayout.EAST);

        add(bottomPanel, BorderLayout.SOUTH);

        LOG.info("QA Copilot Panel initialized");
    }

    private void sendMessage() {
        String userMessage = inputArea.getText().trim();
        if (userMessage.isEmpty()) return;

        // Append context to message if available
        String finalMessage = userMessage;
        if (!selectedTestPlanPath.isEmpty() || !selectedCsvPath.isEmpty()) {
            StringBuilder contextInfo = new StringBuilder(userMessage);
            
            if (!selectedTestPlanPath.isEmpty()) {
                contextInfo.append("\n[TEST_PLAN: ").append(selectedTestPlanPath).append("]");
            }
            if (!selectedCsvPath.isEmpty()) {
                contextInfo.append("\n[CSV: ").append(selectedCsvPath).append("]");
            }
            
            finalMessage = contextInfo.toString();
        }
        
        // Display user message
        chatArea.append("\n📝 You: " + userMessage + "\n");
        
        // Show thinking indicator
        chatArea.append("🤖 QA Copilot is thinking...\n");
        
        // Clear input
        inputArea.setText("");

        // Process message in background thread
        String messageForThread = finalMessage;
        new Thread(() -> {
            try {
                processMessage(messageForThread);
            } catch (Exception e) {
                LOG.error("Error processing message", e);
                SwingUtilities.invokeLater(() -> {
                    chatArea.append("❌ Error: " + e.getMessage() + "\n");
                });
            }
        }).start();
    }

    private void processMessage(String message) throws Exception {
        // Use hardcoded configuration (hidden from user)
        BackendConnector.NavigationResult result = backendConnector.navigateUI(
            message,
            DEVICE_NAME,
            APP_PACKAGE,
            APP_ACTIVITY,
            WORKSPACE_PATH
        );
        
        String response = formatResponse(result);
        
        SwingUtilities.invokeLater(() -> {
            // Remove thinking indicator
            String current = chatArea.getText();
            String withoutThinking = current.replace("🤖 QA Copilot is thinking...\n", "");
            chatArea.setText(withoutThinking);
            chatArea.append(response);
        });
    }

    private String formatResponse(BackendConnector.NavigationResult result) {
        if (result.success) {
            return String.format(
                "✅ Navigation Complete!\n" +
                "  Steps Executed: %d\n" +
                "  Locators Collected: %d\n" +
                "  Saved to: %s\n\n",
                result.stepsExecuted,
                result.locatorsCollected,
                result.locatorsFile
            );
        } else {
            // Provide helpful guidance even on failure
            return "⚠️ Navigation encountered an issue.\n" +
                   "Possible solutions:\n" +
                   "  1. Ensure device is connected: adb devices\n" +
                   "  2. Verify app is running on device\n" +
                   "  3. Check API server is running\n" +
                   "  4. Check logs for details\n\n";
        }
    }

    private void selectTestPlan() {
        JFileChooser fileChooser = new JFileChooser();
        fileChooser.setDialogTitle("Select Test Plan File");
        fileChooser.setFileFilter(new FileNameExtensionFilter("Markdown files (*.md)", "md"));
        
        File testPlansDir = new File(WORKSPACE_PATH + "/test_plans");
        if (testPlansDir.exists()) {
            fileChooser.setCurrentDirectory(testPlansDir);
        }
        
        int result = fileChooser.showOpenDialog(this);
        if (result == JFileChooser.APPROVE_OPTION) {
            selectedTestPlanPath = fileChooser.getSelectedFile().getAbsolutePath();
            updateContextLabel();
            LOG.info("Selected test plan: " + selectedTestPlanPath);
        }
    }

    private void selectCSV() {
        JFileChooser fileChooser = new JFileChooser();
        fileChooser.setDialogTitle("Select CSV File");
        fileChooser.setFileFilter(new FileNameExtensionFilter("CSV files (*.csv)", "csv"));
        
        fileChooser.setCurrentDirectory(new File(WORKSPACE_PATH));
        
        int result = fileChooser.showOpenDialog(this);
        if (result == JFileChooser.APPROVE_OPTION) {
            selectedCsvPath = fileChooser.getSelectedFile().getAbsolutePath();
            updateContextLabel();
            LOG.info("Selected CSV: " + selectedCsvPath);
        }
    }

    private void updateContextLabel() {
        StringBuilder contextText = new StringBuilder();
        
        if (!selectedTestPlanPath.isEmpty()) {
            contextText.append("📋 ").append(new File(selectedTestPlanPath).getName());
        }
        
        if (!selectedCsvPath.isEmpty()) {
            if (contextText.length() > 0) {
                contextText.append("  |  ");
            }
            contextText.append("📄 ").append(new File(selectedCsvPath).getName());
        }
        
        if (contextText.length() == 0) {
            contextText = new StringBuilder("📌 No files selected");
        } else {
            contextText.insert(0, "📌 ");
        }
        
        selectedContextLabel.setText(contextText.toString());
    }
}
