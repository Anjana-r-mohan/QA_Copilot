package com.bizom.qaCopilot.actions;

import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.ui.Messages;
import org.jetbrains.annotations.NotNull;

public class NavigateUIAction extends AnAction {
    private static final Logger LOG = Logger.getInstance(NavigateUIAction.class);

    @Override
    public void actionPerformed(@NotNull AnActionEvent e) {
        LOG.info("Navigate UI action triggered");
        
        String command = Messages.showInputDialog(
            e.getProject(),
            "Enter navigation command:",
            "Navigate UI",
            null,
            "e.g., Navigate to PJP screen and start call",
            null
        );

        if (command != null && !command.isEmpty()) {
            LOG.info("Navigation command: " + command);
            Messages.showInfoMessage("Navigation started: " + command, "QA Copilot");
        }
    }
}
