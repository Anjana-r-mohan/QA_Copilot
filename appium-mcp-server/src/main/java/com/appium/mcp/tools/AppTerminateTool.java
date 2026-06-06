package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Terminate a running app.
 * Paired with app_launch for full app lifecycle control.
 */
public class AppTerminateTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(AppTerminateTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject appPackage = new JsonObject();
        appPackage.addProperty("type", "string");
        appPackage.addProperty("description", "App package name to terminate (e.g. com.example.app)");
        props.add("appPackage", appPackage);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("appPackage");
        schema.add("required", required);

        return new ToolDefinition(
            "app_terminate",
            "Terminate/close a running app. The app process will be killed.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String appPackage = params.get("appPackage").getAsString();

        try {
            boolean terminated = driver.terminateApp(appPackage);
            if (terminated) {
                return ToolResult.success("App terminated: " + appPackage);
            } else {
                return ToolResult.success("App was not running: " + appPackage);
            }
        } catch (Exception e) {
            log.error("Terminate failed", e);
            return ToolResult.error("Terminate failed: " + e.getMessage());
        }
    }
}
