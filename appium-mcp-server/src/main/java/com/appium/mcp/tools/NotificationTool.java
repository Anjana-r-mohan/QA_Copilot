package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Open the notification shade or quick settings.
 * Mobile-specific with no web equivalent.
 */
public class NotificationTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(NotificationTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject action = new JsonObject();
        action.addProperty("type", "string");
        action.addProperty("description", "Action: 'open' to open notification shade, 'close' to close it (default: open)");
        props.add("action", action);

        schema.add("properties", props);

        return new ToolDefinition(
            "device_notifications",
            "Open or close the notification shade. After opening, use app_snapshot to see notification content.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String action = params.has("action") ? params.get("action").getAsString() : "open";

        try {
            if ("close".equalsIgnoreCase(action)) {
                driver.pressKey(new io.appium.java_client.android.nativekey.KeyEvent(
                    io.appium.java_client.android.nativekey.AndroidKey.BACK));
                return ToolResult.success("Notification shade closed");
            } else {
                driver.openNotifications();
                return ToolResult.success("Notification shade opened. Use app_snapshot to see notifications.");
            }
        } catch (Exception e) {
            log.error("Notifications failed", e);
            return ToolResult.error("Notifications failed: " + e.getMessage());
        }
    }
}
