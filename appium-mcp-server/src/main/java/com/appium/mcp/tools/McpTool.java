package com.appium.mcp.tools;

import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;

public interface McpTool {
    ToolDefinition getDefinition();
    ToolResult execute(JsonObject params);
}
