package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ConnectDeviceTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(ConnectDeviceTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject appiumUrl = new JsonObject();
        appiumUrl.addProperty("type", "string");
        appiumUrl.addProperty("description", "Appium server URL (default: http://127.0.0.1:4723)");
        props.add("appiumUrl", appiumUrl);

        JsonObject deviceName = new JsonObject();
        deviceName.addProperty("type", "string");
        deviceName.addProperty("description", "Device name or emulator ID (default: emulator-5554)");
        props.add("deviceName", deviceName);

        JsonObject platformVersion = new JsonObject();
        platformVersion.addProperty("type", "string");
        platformVersion.addProperty("description", "Android version (e.g. 14)");
        props.add("platformVersion", platformVersion);

        JsonObject appPackage = new JsonObject();
        appPackage.addProperty("type", "string");
        appPackage.addProperty("description", "App package name to launch (e.g. com.example.app)");
        props.add("appPackage", appPackage);

        JsonObject appActivity = new JsonObject();
        appActivity.addProperty("type", "string");
        appActivity.addProperty("description", "App activity to launch (e.g. .MainActivity)");
        props.add("appActivity", appActivity);

        schema.add("properties", props);

        return new ToolDefinition(
            "device_connect",
            "Connect to an Android device or emulator via Appium. Starts an automation session.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        try {
            String appiumUrl = params.has("appiumUrl") ? params.get("appiumUrl").getAsString() : null;
            String deviceName = params.has("deviceName") ? params.get("deviceName").getAsString() : null;
            String platformVersion = params.has("platformVersion") ? params.get("platformVersion").getAsString() : null;
            String appPackage = params.has("appPackage") ? params.get("appPackage").getAsString() : null;
            String appActivity = params.has("appActivity") ? params.get("appActivity").getAsString() : null;

            var driver = DriverManager.getInstance().connect(appiumUrl, deviceName, platformVersion, appPackage, appActivity);
            return ToolResult.success("Connected to device. Session: " + driver.getSessionId());
        } catch (Exception e) {
            log.error("Failed to connect", e);
            return ToolResult.error("Connection failed: " + e.getMessage());
        }
    }
}
