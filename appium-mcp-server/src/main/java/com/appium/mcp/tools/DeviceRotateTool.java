package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.ScreenOrientation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Rotate the device between portrait and landscape.
 * Mobile-specific - equivalent of Playwright's viewport resize but for device orientation.
 */
public class DeviceRotateTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(DeviceRotateTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject orientation = new JsonObject();
        orientation.addProperty("type", "string");
        orientation.addProperty("description", "Orientation: 'portrait' or 'landscape'");
        props.add("orientation", orientation);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("orientation");
        schema.add("required", required);

        return new ToolDefinition(
            "device_rotate",
            "Rotate the device between portrait and landscape orientation.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String orientation = params.get("orientation").getAsString().toLowerCase().trim();

        try {
            switch (orientation) {
                case "portrait" -> driver.rotate(ScreenOrientation.PORTRAIT);
                case "landscape" -> driver.rotate(ScreenOrientation.LANDSCAPE);
                default -> {
                    return ToolResult.error("Invalid orientation: " + orientation + ". Use 'portrait' or 'landscape'.");
                }
            }
            return ToolResult.success("Device rotated to: " + orientation);
        } catch (Exception e) {
            log.error("Rotate failed", e);
            return ToolResult.error("Rotate failed: " + e.getMessage());
        }
    }
}
