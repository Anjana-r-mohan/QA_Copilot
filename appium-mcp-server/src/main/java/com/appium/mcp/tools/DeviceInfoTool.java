package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Map;

/**
 * Get device and session info.
 * Useful for the LLM to understand the current context.
 */
public class DeviceInfoTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(DeviceInfoTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");
        schema.add("properties", new JsonObject());

        return new ToolDefinition(
            "device_info",
            "Get information about the connected device: model, OS version, screen size, current app, and session details.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        try {
            StringBuilder sb = new StringBuilder();
            sb.append("Device Information:\n");

            // Session info
            sb.append("  Session ID: ").append(driver.getSessionId()).append("\n");

            // Device capabilities
            var caps = driver.getCapabilities();
            appendCap(sb, "Device Name", caps, "deviceName");
            appendCap(sb, "Platform", caps, "platformName");
            appendCap(sb, "Platform Version", caps, "platformVersion");
            appendCap(sb, "Automation", caps, "automationName");
            appendCap(sb, "Device Model", caps, "deviceModel");
            appendCap(sb, "Device Manufacturer", caps, "deviceManufacturer");
            appendCap(sb, "Device UDID", caps, "udid");

            // Screen size
            try {
                var size = driver.manage().window().getSize();
                sb.append("  Screen Size: ").append(size.getWidth()).append("x").append(size.getHeight()).append("\n");
            } catch (Exception ignored) {}

            // Current package/activity
            try {
                sb.append("  Current Package: ").append(driver.getCurrentPackage()).append("\n");
            } catch (Exception ignored) {}
            try {
                sb.append("  Current Activity: ").append(driver.currentActivity()).append("\n");
            } catch (Exception ignored) {}

            return ToolResult.success(sb.toString());
        } catch (Exception e) {
            log.error("Device info failed", e);
            return ToolResult.error("Device info failed: " + e.getMessage());
        }
    }

    private void appendCap(StringBuilder sb, String label, org.openqa.selenium.Capabilities caps, String key) {
        Object val = caps.getCapability(key);
        if (val != null) {
            sb.append("  ").append(label).append(": ").append(val).append("\n");
        }
    }
}
