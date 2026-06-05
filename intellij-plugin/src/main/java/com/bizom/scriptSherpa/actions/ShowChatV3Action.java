package com.bizom.scriptSherpa.actions;

import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.wm.ToolWindowManager;
import org.jetbrains.annotations.NotNull;

public class ShowChatV3Action extends AnAction {
    @Override
    public void actionPerformed(@NotNull AnActionEvent e) {
        ToolWindowManager toolWindowManager = ToolWindowManager.getInstance(e.getProject());
        if (toolWindowManager.getToolWindow("ScriptSherpa") != null) {
            toolWindowManager.getToolWindow("ScriptSherpa").show(null);
        }
    }
}
