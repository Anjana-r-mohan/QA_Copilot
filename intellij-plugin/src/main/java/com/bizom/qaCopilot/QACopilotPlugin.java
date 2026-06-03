package com.bizom.qaCopilot;

import com.intellij.openapi.components.ApplicationComponent;
import com.intellij.openapi.diagnostic.Logger;

public class QACopilotPlugin implements ApplicationComponent {
    private static final Logger LOG = Logger.getInstance(QACopilotPlugin.class);

    @Override
    public void initComponent() {
        LOG.info("🚀 QA Copilot Plugin Initialized");
    }

    @Override
    public void disposeComponent() {
        LOG.info("🛑 QA Copilot Plugin Disposed");
    }

    @Override
    public String getComponentName() {
        return "QACopilot";
    }
}
