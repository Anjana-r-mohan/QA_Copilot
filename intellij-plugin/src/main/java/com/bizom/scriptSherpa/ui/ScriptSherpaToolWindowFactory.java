package com.bizom.scriptSherpa.ui;

import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowFactory;
import com.intellij.ui.content.ContentFactory;
import org.jetbrains.annotations.NotNull;

public class ScriptSherpaToolWindowFactory implements ToolWindowFactory {
    private static final Logger LOG = Logger.getInstance(ScriptSherpaToolWindowFactory.class);

    @Override
    public void createToolWindowContent(@NotNull Project project, @NotNull ToolWindow toolWindow) {
        LOG.info("Creating ScriptSherpa Tool Window with Unified Chat");
        
        // Use NEW unified chat panel - intelligent, no buttons needed!
        UnifiedChatPanel panel = new UnifiedChatPanel(project);
        ContentFactory contentFactory = ContentFactory.getInstance();
        
        toolWindow.getContentManager().addContent(
            contentFactory.createContent(panel, "Chat", false)
        );
    }
}
