package com.bizom.qaCopilot.actions;

import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.wm.ToolWindowManager;
import org.jetbrains.annotations.NotNull;

public class ShowChatAction extends AnAction {
    @Override
    public void actionPerformed(@NotNull AnActionEvent e) {
        ToolWindowManager toolWindowManager = ToolWindowManager.getInstance(e.getProject());
        toolWindowManager.getToolWindow("QA Copilot").show(null);
    }
}
