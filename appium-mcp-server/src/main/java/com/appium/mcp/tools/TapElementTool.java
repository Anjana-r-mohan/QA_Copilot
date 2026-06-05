package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.By;
import org.openqa.selenium.WebElement;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

public class TapElementTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(TapElementTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject selector = new JsonObject();
        selector.addProperty("type", "string");
        selector.addProperty("description", "Element selector - resource-id, text, content-desc, or XPath");
        props.add("selector", selector);

        JsonObject selectorType = new JsonObject();
        selectorType.addProperty("type", "string");
        selectorType.addProperty("description", "Selector type: id, text, contentDesc, xpath, className (default: id)");
        props.add("selectorType", selectorType);

        schema.add("properties", props);

        var required = new com.google.gson.JsonArray();
        required.add("selector");
        schema.add("required", required);

        return new ToolDefinition(
            "element_tap",
            "Tap/click on a UI element on the screen. Use after exploring the screen to find elements.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String selector = params.get("selector").getAsString();
        String type = params.has("selectorType") ? params.get("selectorType").getAsString() : "id";

        try {
            WebElement element = findElement(driver, selector, type);
            if (element == null) {
                return ToolResult.error("Element not found: " + selector + " (type: " + type + ")");
            }
            element.click();
            return ToolResult.success("Tapped element: " + selector);
        } catch (Exception e) {
            log.error("Tap failed", e);
            return ToolResult.error("Tap failed: " + e.getMessage());
        }
    }

    static WebElement findElement(AndroidDriver driver, String selector, String type) {
        try {
            return switch (type.toLowerCase()) {
                case "id" -> driver.findElement(By.id(selector));
                case "text" -> driver.findElement(By.xpath("//*[@text='" + escapeXpath(selector) + "']"));
                case "contentdesc", "content-desc", "accessibility" ->
                    driver.findElement(By.xpath("//*[@content-desc='" + escapeXpath(selector) + "']"));
                case "xpath" -> driver.findElement(By.xpath(selector));
                case "classname", "class" -> driver.findElement(By.className(selector));
                default -> driver.findElement(By.id(selector));
            };
        } catch (org.openqa.selenium.NoSuchElementException e) {
            // Try fallback strategies
            return tryFallback(driver, selector);
        }
    }

    private static WebElement tryFallback(AndroidDriver driver, String selector) {
        // Try by text
        try {
            List<WebElement> byText = driver.findElements(
                By.xpath("//*[contains(@text,'" + escapeXpath(selector) + "')]"));
            if (!byText.isEmpty()) return byText.get(0);
        } catch (Exception ignored) {}

        // Try by content-desc
        try {
            List<WebElement> byDesc = driver.findElements(
                By.xpath("//*[contains(@content-desc,'" + escapeXpath(selector) + "')]"));
            if (!byDesc.isEmpty()) return byDesc.get(0);
        } catch (Exception ignored) {}

        // Try by resource-id containing
        try {
            List<WebElement> byId = driver.findElements(
                By.xpath("//*[contains(@resource-id,'" + escapeXpath(selector) + "')]"));
            if (!byId.isEmpty()) return byId.get(0);
        } catch (Exception ignored) {}

        return null;
    }

    static String escapeXpath(String value) {
        if (!value.contains("'")) return value;
        if (!value.contains("\"")) return value; // can use double quotes outside
        // Use XPath concat() for values with both quote types
        StringBuilder sb = new StringBuilder("concat(");
        String[] parts = value.split("'", -1);
        for (int i = 0; i < parts.length; i++) {
            if (i > 0) sb.append(",\"'\",");
            sb.append("'").append(parts[i]).append("'");
        }
        sb.append(")");
        return sb.toString();
    }

    private static By byText(String value) {
        if (value.contains("'") && value.contains("\"")) {
            return By.xpath("//*[@text=" + escapeXpath(value) + "]");
        }
        return By.xpath("//*[@text='" + value.replace("'", "\\'") + "']");
    }

    private static By byContentDesc(String value) {
        if (value.contains("'") && value.contains("\"")) {
            return By.xpath("//*[@content-desc=" + escapeXpath(value) + "]");
        }
        return By.xpath("//*[@content-desc='" + value.replace("'", "\\'") + "']");
    }
}
