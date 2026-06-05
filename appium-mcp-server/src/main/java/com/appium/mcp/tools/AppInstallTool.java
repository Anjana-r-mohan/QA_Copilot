package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;

/**
 * Install an APK on the device.
 * Mobile-equivalent of Playwright's browser installation.
 */
public class AppInstallTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(AppInstallTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject appPath = new JsonObject();
        appPath.addProperty("type", "string");
        appPath.addProperty("description", "Absolute path to the APK file to install");
        props.add("appPath", appPath);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("appPath");
        schema.add("required", required);

        return new ToolDefinition(
            "app_install",
            "Install an APK on the connected device.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String appPath = params.get("appPath").getAsString();

        // Basic path validation - reject paths with suspicious patterns
        if (appPath.contains("..") || appPath.contains("\0")) {
            return ToolResult.error("Invalid app path");
        }

        try {
            driver.installApp(appPath);
            return ToolResult.success("App installed from: " + appPath);
        } catch (Exception e) {
            log.error("Install failed", e);
            return ToolResult.error("Install failed: " + e.getMessage());
        }
    }
}
