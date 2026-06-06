package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.WebElement;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;

public class WaitForElementTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(WaitForElementTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject selector = new JsonObject();
        selector.addProperty("type", "string");
        selector.addProperty("description", "Element selector to wait for");
        props.add("selector", selector);

        JsonObject selectorType = new JsonObject();
        selectorType.addProperty("type", "string");
        selectorType.addProperty("description", "Selector type: id, text, contentDesc, xpath (default: id)");
        props.add("selectorType", selectorType);

        JsonObject timeoutSec = new JsonObject();
        timeoutSec.addProperty("type", "number");
        timeoutSec.addProperty("description", "Maximum wait time in seconds (default: 10)");
        props.add("timeoutSeconds", timeoutSec);

        schema.add("properties", props);

        var required = new com.google.gson.JsonArray();
        required.add("selector");
        schema.add("required", required);

        return new ToolDefinition(
            "element_wait_visible",
            "Wait for a UI element to become visible on screen. Useful before interacting with elements that may take time to appear.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String selector = params.get("selector").getAsString();
        String type = params.has("selectorType") ? params.get("selectorType").getAsString() : "id";
        int timeout = params.has("timeoutSeconds") ? params.get("timeoutSeconds").getAsInt() : 10;

        try {
            long deadline = System.currentTimeMillis() + (timeout * 1000L);
            WebElement found = null;

            while (System.currentTimeMillis() < deadline) {
                found = TapElementTool.findElement(driver, selector, type);
                if (found != null && found.isDisplayed()) {
                    return ToolResult.success("Element visible: " + selector);
                }
                Thread.sleep(500);
            }

            return ToolResult.error("Timeout waiting for element: " + selector + " (" + timeout + "s)");
        } catch (Exception e) {
            log.error("Wait failed", e);
            return ToolResult.error("Wait failed: " + e.getMessage());
        }
    }
}
