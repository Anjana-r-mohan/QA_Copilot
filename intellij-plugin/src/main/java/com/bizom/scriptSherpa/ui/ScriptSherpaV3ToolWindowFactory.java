package com.bizom.scriptSherpa.ui;

import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowFactory;
import com.intellij.ui.content.ContentFactory;
import org.jetbrains.annotations.NotNull;

import javax.swing.*;
import java.awt.*;
import java.io.PrintWriter;
import java.io.StringWriter;

public class ScriptSherpaV3ToolWindowFactory implements ToolWindowFactory {
    private static final Logger LOG = Logger.getInstance(ScriptSherpaV3ToolWindowFactory.class);

    @Override
    public void createToolWindowContent(@NotNull Project project, @NotNull ToolWindow toolWindow) {
        LOG.info("Creating ScriptSherpa V3 Tool Window with Unified Chat");

        ContentFactory contentFactory = ContentFactory.getInstance();

        try {
            UnifiedChatPanel panel = new UnifiedChatPanel(project);
            toolWindow.getContentManager().addContent(
                contentFactory.createContent(panel, "V3 Chat", false)
            );
        } catch (Exception ex) {
            LOG.error("Failed to initialize ScriptSherpa V3 panel", ex);

            JPanel fallback = new JPanel(new BorderLayout());
            JLabel title = new JLabel("ScriptSherpa V3 failed to initialize", SwingConstants.LEFT);
            title.setBorder(BorderFactory.createEmptyBorder(10, 10, 6, 10));
            title.setFont(title.getFont().deriveFont(Font.BOLD, 13f));

            JTextArea details = new JTextArea();
            details.setEditable(false);
            details.setLineWrap(true);
            details.setWrapStyleWord(true);

            StringWriter sw = new StringWriter();
            ex.printStackTrace(new PrintWriter(sw));
            details.setText(
                "ScriptSherpa V3 could not render the chat panel.\n" +
                "Please reinstall the latest zip and restart IntelliJ.\n\n" +
                sw.toString()
            );

            fallback.add(title, BorderLayout.NORTH);
            fallback.add(new JScrollPane(details), BorderLayout.CENTER);

            toolWindow.getContentManager().addContent(
                contentFactory.createContent(fallback, "V3 Chat", false)
            );
        }
    }
}
