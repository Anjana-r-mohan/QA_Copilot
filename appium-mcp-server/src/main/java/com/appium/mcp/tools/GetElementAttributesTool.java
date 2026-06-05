package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.openqa.selenium.WebElement;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Get detailed attributes of a specific element.
 * Like Playwright's browser_evaluate but for element inspection.
 */
public class GetElementAttributesTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(GetElementAttributesTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject selector = new JsonObject();
        selector.addProperty("type", "string");
        selector.addProperty("description", "Element selector to inspect");
        props.add("selector", selector);

        JsonObject selectorType = new JsonObject();
        selectorType.addProperty("type", "string");
        selectorType.addProperty("description", "Selector type: id, text, contentDesc, xpath, className (default: id)");
        props.add("selectorType", selectorType);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("selector");
        schema.add("required", required);

        return new ToolDefinition(
            "element_get_attributes",
            "Get all attributes of a specific UI element (text, content-desc, class, bounds, enabled, checked, selected, etc.). Useful for verifying element state.",
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
            WebElement element = TapElementTool.findElement(driver, selector, type);
            if (element == null) {
                return ToolResult.error("Element not found: " + selector);
            }

            StringBuilder sb = new StringBuilder();
            sb.append("Element: ").append(selector).append("\n");
            sb.append("  Tag: ").append(element.getTagName()).append("\n");
            sb.append("  Text: ").append(element.getText()).append("\n");
            sb.append("  Displayed: ").append(element.isDisplayed()).append("\n");
            sb.append("  Enabled: ").append(element.isEnabled()).append("\n");
            sb.append("  Selected: ").append(element.isSelected()).append("\n");
            sb.append("  Location: (").append(element.getLocation().getX())
                .append(", ").append(element.getLocation().getY()).append(")\n");
            sb.append("  Size: ").append(element.getSize().getWidth())
                .append("x").append(element.getSize().getHeight()).append("\n");

            // Try common Android attributes
            appendAttr(sb, element, "resource-id");
            appendAttr(sb, element, "content-desc");
            appendAttr(sb, element, "class");
            appendAttr(sb, element, "package");
            appendAttr(sb, element, "checkable");
            appendAttr(sb, element, "checked");
            appendAttr(sb, element, "clickable");
            appendAttr(sb, element, "focusable");
            appendAttr(sb, element, "focused");
            appendAttr(sb, element, "scrollable");
            appendAttr(sb, element, "long-clickable");
            appendAttr(sb, element, "password");
            appendAttr(sb, element, "bounds");

            return ToolResult.success(sb.toString());
        } catch (Exception e) {
            log.error("Get attributes failed", e);
            return ToolResult.error("Get attributes failed: " + e.getMessage());
        }
    }

    private void appendAttr(StringBuilder sb, WebElement element, String attr) {
        try {
            String val = element.getAttribute(attr);
            if (val != null && !val.isEmpty()) {
                sb.append("  ").append(attr).append(": ").append(val).append("\n");
            }
        } catch (Exception ignored) {}
    }
}
