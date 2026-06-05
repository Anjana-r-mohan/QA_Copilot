package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.OutputType;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Base64;

public class ScreenshotTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(ScreenshotTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");
        schema.add("properties", new JsonObject());
        return new ToolDefinition(
            "device_screenshot",
            "Take a screenshot of the current device screen. Returns the image directly. You can't perform actions based on the screenshot alone - use app_snapshot for actionable element data.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        try {
            byte[] screenshot = driver.getScreenshotAs(OutputType.BYTES);
            String base64 = Base64.getEncoder().encodeToString(screenshot);
            return ToolResult.image(base64, "image/png");
        } catch (Exception e) {
            log.error("Screenshot failed", e);
            return ToolResult.error("Screenshot failed: " + e.getMessage());
        }
    }
}
