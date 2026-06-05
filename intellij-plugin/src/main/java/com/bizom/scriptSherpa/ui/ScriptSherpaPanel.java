package com.bizom.scriptSherpa.ui;

import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.progress.ProgressIndicator;
import com.intellij.openapi.progress.ProgressManager;
import com.intellij.openapi.progress.Task;
import com.intellij.openapi.project.Project;
import com.intellij.ui.components.JBPanel;
import com.intellij.ui.components.JBScrollPane;
import com.intellij.ui.components.JBTextArea;
import com.bizom.scriptSherpa.backend.BackendConnector;
import org.jetbrains.annotations.NotNull;

import javax.swing.*;
import javax.swing.filechooser.FileNameExtensionFilter;
import java.awt.*;
import java.io.File;

public class ScriptSherpaPanel extends JBPanel<ScriptSherpaPanel> {
    private static final Logger LOG = Logger.getInstance(ScriptSherpaPanel.class);
    
    private final Project project;
    private final JBTextArea chatArea;
    private final JBTextArea inputArea;
    private final BackendConnector backendConnector;
    private final JLabel selectedContextLabel;
    private String selectedTestPlanPath = "";
    private String selectedCsvPath = "";
    private String lastLocatorsFile = "";  // Track last generated locators file
    
    // Hidden configuration (hardcoded defaults)
    private static final String DEVICE_NAME = "127.0.0.1:6555";
    private static final String APP_PACKAGE = "co.bizom.apps";
    private static final String APP_ACTIVITY = ".android.MainActivity";
    private static final String WORKSPACE_PATH = "/Users/anjana.mohan/KMMAuto_demo";
    
    // Feature flags
    private static final boolean USE_STREAMING = true;  // TRUE = Real-time SSE streaming!

    public ScriptSherpaPanel(Project project) {
        this.project = project;
        this.backendConnector = new BackendConnector();
        setLayout(new BorderLayout());

        // Top: File Selection + Generate Tests Button
        JPanel topPanel = new JPanel(new FlowLayout(FlowLayout.LEFT, 5, 5));
        
        JButton pickTestPlanBtn = new JButton("📋 Test Plan");
        pickTestPlanBtn.setPreferredSize(new Dimension(120, 30));
        pickTestPlanBtn.addActionListener(e -> selectTestPlan());
        topPanel.add(pickTestPlanBtn);
        
        JButton pickCsvBtn = new JButton("📄 CSV");
        pickCsvBtn.setPreferredSize(new Dimension(100, 30));
        pickCsvBtn.addActionListener(e -> selectCSV());
        topPanel.add(pickCsvBtn);
        
        // Add separator
        topPanel.add(new JLabel("  |  "));
        
        // Add Generate Tests button
        JButton generateTestsBtn = new JButton("✨ Generate Tests");
        generateTestsBtn.setPreferredSize(new Dimension(150, 30));
        generateTestsBtn.setToolTipText("Generate test code using AI");
        generateTestsBtn.addActionListener(e -> showGenerateTestsDialog());
        topPanel.add(generateTestsBtn);
        
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
        chatArea.setText("👋 Welcome to ScriptSherpa!\n\nClick 📋 or 📄 to select context files, then type your command.\n\n");
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

        LOG.info("ScriptSherpa Panel initialized");
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
        chatArea.append("🤖 ScriptSherpa is thinking...\n");
        
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
        if (USE_STREAMING) {
            // Try streaming first
            processMessageWithStreaming(message);
        } else {
            // Use modal progress dialog as fallback
            processMessageWithModal(message);
        }
    }
    
    private void processMessageWithStreaming(String message) {
        // Use hardcoded configuration (hidden from user) with real-time streaming
        new Thread(() -> {
            try {
                backendConnector.navigateUIWithProgress(
                    message,
                    DEVICE_NAME,
                    APP_PACKAGE,
                    APP_ACTIVITY,
                    WORKSPACE_PATH,
                    progressUpdate -> {
                        // Handle each progress update in real-time
                        SwingUtilities.invokeLater(() -> {
                            handleProgressUpdate(progressUpdate);
                        });
                    }
                );
            } catch (Exception e) {
                LOG.error("Streaming failed, falling back to modal", e);
                // Fallback to modal on streaming failure
                SwingUtilities.invokeLater(() -> {
                    try {
                        processMessageWithModal(message);
                    } catch (Exception ex) {
                        chatArea.append("❌ Error: " + ex.getMessage() + "\n\n");
                    }
                });
            }
        }).start();
    }
    
    private void processMessageWithModal(String message) {
        // Use IntelliJ's progress modal with background task
        ProgressManager.getInstance().run(new Task.Backgroundable(project, "ScriptSherpa Processing...", true) {
            private BackendConnector.NavigationResult result;
            private StringBuilder progressLog = new StringBuilder();
            
            @Override
            public void run(@NotNull ProgressIndicator indicator) {
                try {
                    indicator.setText("🎯 Understanding your command...");
                    progressLog.append("🎯 Understanding: ").append(message).append("\n");
                    Thread.sleep(500);
                    
                    // Use streaming endpoint but collect in modal
                    backendConnector.navigateUIWithProgress(
                        message,
                        DEVICE_NAME,
                        APP_PACKAGE,
                        APP_ACTIVITY,
                        WORKSPACE_PATH,
                        progressUpdate -> {
                            String msg = progressUpdate.message;
                            progressLog.append(msg).append("\n");
                            
                            // Update progress indicator
                            indicator.setText(msg);
                            
                            // Extract percentage if available
                            if (progressUpdate.data != null) {
                                if (progressUpdate.data.has("test_case_number") && progressUpdate.data.has("total_test_cases")) {
                                    int current = progressUpdate.data.get("test_case_number").getAsInt();
                                    int total = progressUpdate.data.get("total_test_cases").getAsInt();
                                    double fraction = (double) current / total;
                                    indicator.setFraction(fraction);
                                }
                            }
                            
                            // Check for cancellation
                            if (indicator.isCanceled()) {
                                throw new RuntimeException("User cancelled operation");
                            }
                        }
                    );
                    
                } catch (Exception e) {
                    LOG.error("Error in modal processing", e);
                    progressLog.append("❌ Error: ").append(e.getMessage()).append("\n");
                }
            }
            
            @Override
            public void onSuccess() {
                SwingUtilities.invokeLater(() -> {
                    // Remove thinking indicator
                    String current = chatArea.getText();
                    String withoutThinking = current.replace("🤖 ScriptSherpa is thinking...\n", "");
                    chatArea.setText(withoutThinking);
                    
                    // Append all progress
                    chatArea.append(progressLog.toString());
                    chatArea.append("\n");
                    
                    // Auto-scroll
                    chatArea.setCaretPosition(chatArea.getDocument().getLength());
                });
            }
            
            @Override
            public void onThrowable(@NotNull Throwable error) {
                SwingUtilities.invokeLater(() -> {
                    chatArea.append("❌ Error: " + error.getMessage() + "\n\n");
                });
            }
        });
    }

    private void handleProgressUpdate(BackendConnector.ProgressUpdate update) {
        String type = update.type;
        String message = update.message;
        
        // Remove "thinking" indicator on first real update
        if ("understanding".equals(type) || "intent".equals(type)) {
            String current = chatArea.getText();
            String withoutThinking = current.replace("🤖 ScriptSherpa is thinking...\n", "");
            chatArea.setText(withoutThinking);
        }
        
        // Display progress based on type
        switch (type) {
            case "understanding":
            case "intent":
                chatArea.append(message + "\n");
                break;
                
            case "progress":
                chatArea.append(message + "\n");
                break;
                
            case "success":
                chatArea.append(message + "\n");
                break;
                
            case "test_case_start":
                chatArea.append("\n" + message + "\n");
                break;
                
            case "step":
                chatArea.append(message + "\n");
                break;
                
            case "elements_found":
                chatArea.append(message + "\n");
                break;
                
            case "locators_update":
                chatArea.append(message + "\n");
                break;
                
            case "warning":
                chatArea.append(message + "\n");
                break;
                
            case "error":
                chatArea.append("❌ " + message + "\n\n");
                break;
                
            case "complete":
                // Final summary
                if (update.data != null && update.data.has("result")) {
                    com.google.gson.JsonObject result = update.data.getAsJsonObject("result");
                    int steps = result.has("steps_executed") ? result.get("steps_executed").getAsInt() : 0;
                    int locators = result.has("locators_collected") ? result.get("locators_collected").getAsInt() : 0;
                    String file = result.has("locators_file") ? result.get("locators_file").getAsString() : "";
                    
                    // Save locators file path for code generation
                    if (!file.isEmpty()) {
                        lastLocatorsFile = file;
                    }
                    
                    chatArea.append("\n" + "═".repeat(50) + "\n");
                    chatArea.append("✅ Navigation Complete!\n");
                    chatArea.append(String.format("   Test Cases Executed: %d\n", steps));
                    chatArea.append(String.format("   Locators Collected: %d\n", locators));
                    chatArea.append(String.format("   Saved to: %s\n", file));
                    chatArea.append("═".repeat(50) + "\n\n");
                } else {
                    chatArea.append("\n✅ " + message + "\n\n");
                }
                break;
                
            case "keepalive":
                // Don't display keepalive messages, just keep connection alive
                break;
                
            default:
                chatArea.append(message + "\n");
        }
        
        // Auto-scroll to bottom
        chatArea.setCaretPosition(chatArea.getDocument().getLength());
    }

    private void formatResponse(BackendConnector.NavigationResult result) {
        // Not used anymore - kept for compatibility
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

    
    private void showGenerateTestsDialog() {
        // Create dialog for test generation
        JDialog dialog = new JDialog((Frame) SwingUtilities.getWindowAncestor(this), "Generate Test Code", true);
        dialog.setLayout(new BorderLayout(10, 10));
        dialog.setSize(500, 300);
        dialog.setLocationRelativeTo(this);
        
        // Main panel
        JPanel mainPanel = new JPanel(new BorderLayout(10, 10));
        mainPanel.setBorder(BorderFactory.createEmptyBorder(15, 15, 15, 15));
        
        // Instruction panel
        JPanel instructionPanel = new JPanel(new BorderLayout(5, 5));
        instructionPanel.add(new JLabel("Tell me what kind of tests to generate:"), BorderLayout.NORTH);
        
        JBTextArea instructionArea = new JBTextArea();
        instructionArea.setRows(5);
        instructionArea.setLineWrap(true);
        instructionArea.setWrapStyleWord(true);
        instructionArea.setText("Generate Playwright tests in TypeScript with proper project structure");
        instructionPanel.add(new JBScrollPane(instructionArea), BorderLayout.CENTER);
        
        mainPanel.add(instructionPanel, BorderLayout.CENTER);
        
        // Info panel
        JPanel infoPanel = new JPanel(new GridLayout(3, 1, 5, 5));
        infoPanel.setBorder(BorderFactory.createTitledBorder("Context"));
        
        String testPlanInfo = selectedTestPlanPath.isEmpty() ? "None selected" : new File(selectedTestPlanPath).getName();
        String locatorsInfo = lastLocatorsFile.isEmpty() ? "None available" : new File(lastLocatorsFile).getName();
        
        infoPanel.add(new JLabel("📋 Test Plan: " + testPlanInfo));
        infoPanel.add(new JLabel("🔍 Locators: " + locatorsInfo));
        infoPanel.add(new JLabel("📁 Workspace: " + WORKSPACE_PATH));
        
        mainPanel.add(infoPanel, BorderLayout.NORTH);
        
        // Button panel
        JPanel buttonPanel = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        JButton generateBtn = new JButton("✨ Generate");
        JButton cancelBtn = new JButton("Cancel");
        
        generateBtn.addActionListener(e -> {
            String instruction = instructionArea.getText().trim();
            if (!instruction.isEmpty()) {
                dialog.dispose();
                generateTestCode(instruction);
            }
        });
        
        cancelBtn.addActionListener(e -> dialog.dispose());
        
        buttonPanel.add(cancelBtn);
        buttonPanel.add(generateBtn);
        
        mainPanel.add(buttonPanel, BorderLayout.SOUTH);
        
        dialog.add(mainPanel);
        dialog.setVisible(true);
    }
    
    private void generateTestCode(String instruction) {
        // Display user instruction in chat
        chatArea.append("\n✨ Generating Tests\n");
        chatArea.append("📝 Instruction: " + instruction + "\n");
        chatArea.append("🤖 ScriptSherpa is working...\n");
        
        // Generate in background
        new Thread(() -> {
            try {
                backendConnector.generateTestCode(
                    instruction,
                    selectedTestPlanPath.isEmpty() ? null : selectedTestPlanPath,
                    lastLocatorsFile.isEmpty() ? null : lastLocatorsFile,
                    WORKSPACE_PATH,
                    progressUpdate -> {
                        SwingUtilities.invokeLater(() -> {
                            handleCodeGenerationProgress(progressUpdate);
                        });
                    }
                );
            } catch (Exception e) {
                LOG.error("Code generation failed", e);
                SwingUtilities.invokeLater(() -> {
                    chatArea.append("❌ Error: " + e.getMessage() + "\n\n");
                });
            }
        }).start();
    }
    
    private void handleCodeGenerationProgress(BackendConnector.ProgressUpdate update) {
        String type = update.type;
        String message = update.message;
        
        // Remove "working" indicator on first update
        if ("understanding".equals(type)) {
            String current = chatArea.getText();
            String withoutWorking = current.replace("🤖 ScriptSherpa is working...\n", "");
            chatArea.setText(withoutWorking);
        }
        
        // Display progress
        switch (type) {
            case "understanding":
            case "intent":
            case "progress":
            case "success":
                chatArea.append(message + "\n");
                break;
                
            case "complete":
                // Show generated files
                if (update.data != null) {
                    String framework = update.data.has("framework") ? update.data.get("framework").getAsString() : "Unknown";
                    String language = update.data.has("language") ? update.data.get("language").getAsString() : "Unknown";
                    int filesCount = update.data.has("files_generated") ? update.data.get("files_generated").getAsInt() : 0;
                    
                    chatArea.append("\n" + "═".repeat(50) + "\n");
                    chatArea.append("✅ Test Code Generated!\n");
                    chatArea.append(String.format("   Framework: %s\n", framework));
                    chatArea.append(String.format("   Language: %s\n", language));
                    chatArea.append(String.format("   Files Created: %d\n", filesCount));
                    chatArea.append(String.format("   Location: %s/generated_tests/\n", WORKSPACE_PATH));
                    chatArea.append("═".repeat(50) + "\n\n");
                    chatArea.append("💡 Tip: Check the generated_tests folder for your code!\n\n");
                } else {
                    chatArea.append("\n✅ " + message + "\n\n");
                }
                break;
                
            case "error":
                chatArea.append("❌ " + message + "\n\n");
                break;
                
            default:
                chatArea.append(message + "\n");
        }
        
        // Auto-scroll
        chatArea.setCaretPosition(chatArea.getDocument().getLength());
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
