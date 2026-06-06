package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.interactions.PointerInput;
import org.openqa.selenium.interactions.Sequence;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.util.Collections;

/**
 * Long-press on an element or coordinates.
 * Mobile-specific gesture with no web equivalent.
 */
public class LongPressTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(LongPressTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject selector = new JsonObject();
        selector.addProperty("type", "string");
        selector.addProperty("description", "Element selector to long-press");
        props.add("selector", selector);

        JsonObject selectorType = new JsonObject();
        selectorType.addProperty("type", "string");
        selectorType.addProperty("description", "Selector type: id, text, contentDesc, xpath, className (default: id)");
        props.add("selectorType", selectorType);

        JsonObject durationMs = new JsonObject();
        durationMs.addProperty("type", "number");
        durationMs.addProperty("description", "Duration of long press in milliseconds (default: 1500)");
        props.add("durationMs", durationMs);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("selector");
        schema.add("required", required);

        return new ToolDefinition(
            "element_long_press",
            "Long-press (tap and hold) on a UI element. Useful for context menus, drag initiation, or other long-press actions.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String selector = params.get("selector").getAsString();
        String type = params.has("selectorType") ? params.get("selectorType").getAsString() : "id";
        int duration = params.has("durationMs") ? params.get("durationMs").getAsInt() : 1500;

        try {
            WebElement element = TapElementTool.findElement(driver, selector, type);
            if (element == null) {
                return ToolResult.error("Element not found: " + selector);
            }

            int centerX = element.getLocation().getX() + element.getSize().getWidth() / 2;
            int centerY = element.getLocation().getY() + element.getSize().getHeight() / 2;

            PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
            Sequence longPress = new Sequence(finger, 0);
            longPress.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), centerX, centerY));
            longPress.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            longPress.addAction(finger.createPointerMove(Duration.ofMillis(duration), PointerInput.Origin.viewport(), centerX, centerY));
            longPress.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            driver.perform(Collections.singletonList(longPress));

            return ToolResult.success("Long-pressed element: " + selector + " for " + duration + "ms");
        } catch (Exception e) {
            log.error("Long press failed", e);
            return ToolResult.error("Long press failed: " + e.getMessage());
        }
    }
}
