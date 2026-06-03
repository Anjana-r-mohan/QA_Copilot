package com.bizom.qaCopilot.ui;

import com.intellij.openapi.diagnostic.Logger;
import com.intellij.openapi.project.Project;
import com.intellij.openapi.wm.ToolWindow;
import com.intellij.openapi.wm.ToolWindowFactory;
import com.intellij.ui.content.ContentFactory;
import org.jetbrains.annotations.NotNull;

public class QACopilotToolWindowFactory implements ToolWindowFactory {
    private static final Logger LOG = Logger.getInstance(QACopilotToolWindowFactory.class);

    @Override
    public void createToolWindowContent(@NotNull Project project, @NotNull ToolWindow toolWindow) {
        LOG.info("Creating QA Copilot Tool Window");
        
        QACopilotPanel panel = new QACopilotPanel(project);
        ContentFactory contentFactory = ContentFactory.getInstance();
        
        toolWindow.getContentManager().addContent(
            contentFactory.createContent(panel, "Chat", false)
        );
    }
}
