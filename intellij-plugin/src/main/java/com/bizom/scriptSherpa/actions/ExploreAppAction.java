package com.bizom.scriptSherpa.actions;

import com.intellij.openapi.actionSystem.AnAction;
import com.intellij.openapi.actionSystem.AnActionEvent;
import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.ui.Messages;
import org.jetbrains.annotations.NotNull;

public class ExploreAppAction extends AnAction {
    private static final Logger LOG = Logger.getInstance(ExploreAppAction.class);

    @Override
    public void actionPerformed(@NotNull AnActionEvent e) {
        LOG.info("Explore App action triggered");
        Messages.showInfoMessage("Starting app exploration...", "ScriptSherpa");
    }
}
