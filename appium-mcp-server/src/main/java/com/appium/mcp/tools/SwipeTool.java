package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.Dimension;
import org.openqa.selenium.interactions.PointerInput;
import org.openqa.selenium.interactions.Sequence;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;
import java.util.Collections;

/**
 * Perform a swipe gesture at specific coordinates.
 * Unlike scroll (which scrolls content), swipe is for gestures like
 * dismissing notifications, switching pages, etc.
 */
public class SwipeTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(SwipeTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject startX = new JsonObject();
        startX.addProperty("type", "number");
        startX.addProperty("description", "Start X coordinate (as fraction 0.0-1.0 of screen width)");
        props.add("startX", startX);

        JsonObject startY = new JsonObject();
        startY.addProperty("type", "number");
        startY.addProperty("description", "Start Y coordinate (as fraction 0.0-1.0 of screen height)");
        props.add("startY", startY);

        JsonObject endX = new JsonObject();
        endX.addProperty("type", "number");
        endX.addProperty("description", "End X coordinate (as fraction 0.0-1.0 of screen width)");
        props.add("endX", endX);

        JsonObject endY = new JsonObject();
        endY.addProperty("type", "number");
        endY.addProperty("description", "End Y coordinate (as fraction 0.0-1.0 of screen height)");
        props.add("endY", endY);

        JsonObject durationMs = new JsonObject();
        durationMs.addProperty("type", "number");
        durationMs.addProperty("description", "Swipe duration in milliseconds (default: 500)");
        props.add("durationMs", durationMs);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("startX");
        required.add("startY");
        required.add("endX");
        required.add("endY");
        schema.add("required", required);

        return new ToolDefinition(
            "device_swipe",
            "Perform a swipe gesture between two points on screen. Coordinates are fractions of screen dimensions (0.0-1.0). For scrolling content, prefer device_scroll instead.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        double startXFrac = params.get("startX").getAsDouble();
        double startYFrac = params.get("startY").getAsDouble();
        double endXFrac = params.get("endX").getAsDouble();
        double endYFrac = params.get("endY").getAsDouble();
        int duration = params.has("durationMs") ? params.get("durationMs").getAsInt() : 500;

        try {
            Dimension size = driver.manage().window().getSize();
            int sx = (int) (size.width * Math.max(0, Math.min(1, startXFrac)));
            int sy = (int) (size.height * Math.max(0, Math.min(1, startYFrac)));
            int ex = (int) (size.width * Math.max(0, Math.min(1, endXFrac)));
            int ey = (int) (size.height * Math.max(0, Math.min(1, endYFrac)));

            PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
            Sequence swipe = new Sequence(finger, 0);
            swipe.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), sx, sy));
            swipe.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
            swipe.addAction(finger.createPointerMove(Duration.ofMillis(duration), PointerInput.Origin.viewport(), ex, ey));
            swipe.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
            driver.perform(Collections.singletonList(swipe));

            return ToolResult.success(String.format("Swiped from (%.1f,%.1f) to (%.1f,%.1f)",
                startXFrac, startYFrac, endXFrac, endYFrac));
        } catch (Exception e) {
            log.error("Swipe failed", e);
            return ToolResult.error("Swipe failed: " + e.getMessage());
        }
    }
}
