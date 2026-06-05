package com.appium.mcp.server;

import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.appium.mcp.tools.*;
import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;

public class ToolRegistry {
    private static final Logger log = LoggerFactory.getLogger(ToolRegistry.class);
    private final Map<String, McpTool> tools = new LinkedHashMap<>();

    public ToolRegistry() {
        // Core: Device connection & info
        register(new ConnectDeviceTool());
        register(new DeviceInfoTool());

        // Snapshot & inspection (like Playwright's browser_snapshot)
        register(new AppSnapshotTool());
        register(new ScreenshotTool());
        register(new GetElementsTool());
        register(new GetElementAttributesTool());

        // Element interaction (like Playwright's browser_click, browser_type)
        register(new TapElementTool());
        register(new TypeTextTool());
        register(new LongPressTool());

        // Navigation & gestures (like Playwright's browser_navigate, browser_press_key)
        register(new ScrollTool());
        register(new SwipeTool());
        register(new PressBackTool());
        register(new PressKeyTool());
        register(new DeviceRotateTool());

        // App lifecycle (like Playwright's browser_close, tab management)
        register(new LaunchAppTool());
        register(new AppTerminateTool());
        register(new AppInstallTool());

        // Wait & synchronization (like Playwright's browser_wait_for)
        register(new WaitForElementTool());
        register(new WaitForTool());

        // Device features
        register(new NotificationTool());
    }

    private void register(McpTool tool) {
        String name = tool.getDefinition().getName();
        tools.put(name, tool);
        log.info("Registered tool: {}", name);
    }

    public List<ToolDefinition> listTools() {
        return tools.values().stream()
            .map(McpTool::getDefinition)
            .toList();
    }

    public ToolResult executeTool(String name, JsonObject params) {
        McpTool tool = tools.get(name);
        if (tool == null) {
            return ToolResult.error("Unknown tool: " + name);
        }
        log.info("Executing tool: {} with params: {}", name, params);
        return tool.execute(params);
    }

    public boolean hasTool(String name) {
        return tools.containsKey(name);
    }
}
