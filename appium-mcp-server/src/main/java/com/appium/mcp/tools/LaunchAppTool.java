package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LaunchAppTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(LaunchAppTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject appPackage = new JsonObject();
        appPackage.addProperty("type", "string");
        appPackage.addProperty("description", "App package name (e.g. com.example.app)");
        props.add("appPackage", appPackage);

        JsonObject appActivity = new JsonObject();
        appActivity.addProperty("type", "string");
        appActivity.addProperty("description", "App activity (e.g. .MainActivity)");
        props.add("appActivity", appActivity);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("appPackage");
        schema.add("required", required);

        return new ToolDefinition(
            "app_launch",
            "Launch or relaunch an app on the device. Terminates the app first if running, then starts it fresh.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String appPackage = params.get("appPackage").getAsString();
        String appActivity = params.has("appActivity") ? params.get("appActivity").getAsString() : null;

        try {
            // Terminate if running
            try {
                driver.terminateApp(appPackage);
                Thread.sleep(1000);
            } catch (Exception ignored) {}

            // Activate/launch
            if (appActivity != null) {
                var activity = new io.appium.java_client.android.Activity(appPackage, appActivity);
                driver.startActivity(activity);
            } else {
                driver.activateApp(appPackage);
            }

            return ToolResult.success("Launched app: " + appPackage);
        } catch (Exception e) {
            log.error("Launch failed", e);
            return ToolResult.error("Launch failed: " + e.getMessage());
        }
    }
}
