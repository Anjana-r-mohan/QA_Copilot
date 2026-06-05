package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.nativekey.AndroidKey;
import io.appium.java_client.android.nativekey.KeyEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PressBackTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(PressBackTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");
        schema.add("properties", new JsonObject());
        return new ToolDefinition(
            "device_back",
            "Press the Android back button.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        try {
            driver.pressKey(new KeyEvent(AndroidKey.BACK));
            return ToolResult.success("Pressed back button");
        } catch (Exception e) {
            try {
                driver.navigate().back();
                return ToolResult.success("Pressed back button (navigate)");
            } catch (Exception e2) {
                log.error("Back failed", e2);
                return ToolResult.error("Back press failed: " + e2.getMessage());
            }
        }
    }
}
