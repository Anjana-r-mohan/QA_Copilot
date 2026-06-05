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
import java.util.Map;

public class ScrollTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(ScrollTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject direction = new JsonObject();
        direction.addProperty("type", "string");
        direction.addProperty("description", "Scroll direction: up, down, left, right (default: down)");
        props.add("direction", direction);

        JsonObject amount = new JsonObject();
        amount.addProperty("type", "number");
        amount.addProperty("description", "Scroll amount as fraction of screen (0.0-1.0, default: 0.5)");
        props.add("amount", amount);

        schema.add("properties", props);

        return new ToolDefinition(
            "device_scroll",
            "Scroll the screen in a direction. Useful to reveal elements not currently visible.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String direction = params.has("direction") ? params.get("direction").getAsString() : "down";
        double amount = params.has("amount") ? params.get("amount").getAsDouble() : 0.5;

        try {
            // Try mobile:scrollGesture first (W3C)
            if (tryScrollGesture(driver, direction, amount)) {
                return ToolResult.success("Scrolled " + direction);
            }
            // Fallback to swipe gesture
            if (trySwipeGesture(driver, direction, amount)) {
                return ToolResult.success("Scrolled " + direction + " (swipe)");
            }
            // Last resort: W3C pointer actions
            performLegacySwipe(driver, direction, amount);
            return ToolResult.success("Scrolled " + direction + " (legacy)");
        } catch (Exception e) {
            log.error("Scroll failed", e);
            return ToolResult.error("Scroll failed: " + e.getMessage());
        }
    }

    private boolean tryScrollGesture(AndroidDriver driver, String direction, double amount) {
        try {
            Dimension size = driver.manage().window().getSize();
            driver.executeScript("mobile: scrollGesture", Map.of(
                "left", size.width / 4,
                "top", size.height / 4,
                "width", size.width / 2,
                "height", size.height / 2,
                "direction", direction,
                "percent", amount
            ));
            return true;
        } catch (Exception e) {
            log.debug("scrollGesture failed, trying swipe: {}", e.getMessage());
            return false;
        }
    }

    private boolean trySwipeGesture(AndroidDriver driver, String direction, double amount) {
        try {
            Dimension size = driver.manage().window().getSize();
            driver.executeScript("mobile: swipeGesture", Map.of(
                "left", size.width / 4,
                "top", size.height / 4,
                "width", size.width / 2,
                "height", size.height / 2,
                "direction", direction,
                "percent", amount
            ));
            return true;
        } catch (Exception e) {
            log.debug("swipeGesture failed, trying legacy: {}", e.getMessage());
            return false;
        }
    }

    private void performLegacySwipe(AndroidDriver driver, String direction, double amount) {
        Dimension size = driver.manage().window().getSize();
        int centerX = size.width / 2;
        int centerY = size.height / 2;
        int distance = (int) (size.height * amount * 0.4);

        int startX = centerX, startY = centerY, endX = centerX, endY = centerY;

        switch (direction.toLowerCase()) {
            case "down" -> { startY = centerY + distance / 2; endY = centerY - distance / 2; }
            case "up" -> { startY = centerY - distance / 2; endY = centerY + distance / 2; }
            case "left" -> { startX = centerX - (int)(size.width * amount * 0.4); endX = centerX + (int)(size.width * amount * 0.4); }
            case "right" -> { startX = centerX + (int)(size.width * amount * 0.4); endX = centerX - (int)(size.width * amount * 0.4); }
        }

        PointerInput finger = new PointerInput(PointerInput.Kind.TOUCH, "finger");
        Sequence swipe = new Sequence(finger, 0);
        swipe.addAction(finger.createPointerMove(Duration.ZERO, PointerInput.Origin.viewport(), startX, startY));
        swipe.addAction(finger.createPointerDown(PointerInput.MouseButton.LEFT.asArg()));
        swipe.addAction(finger.createPointerMove(Duration.ofMillis(600), PointerInput.Origin.viewport(), endX, endY));
        swipe.addAction(finger.createPointerUp(PointerInput.MouseButton.LEFT.asArg()));
        driver.perform(Collections.singletonList(swipe));
    }
}
