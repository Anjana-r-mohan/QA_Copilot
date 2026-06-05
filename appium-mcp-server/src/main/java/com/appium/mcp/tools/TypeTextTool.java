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

public class TypeTextTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(TypeTextTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject selector = new JsonObject();
        selector.addProperty("type", "string");
        selector.addProperty("description", "Element selector for the input field");
        props.add("selector", selector);

        JsonObject selectorType = new JsonObject();
        selectorType.addProperty("type", "string");
        selectorType.addProperty("description", "Selector type: id, text, contentDesc, xpath, className (default: id)");
        props.add("selectorType", selectorType);

        JsonObject text = new JsonObject();
        text.addProperty("type", "string");
        text.addProperty("description", "Text to type into the element");
        props.add("text", text);

        JsonObject clearFirst = new JsonObject();
        clearFirst.addProperty("type", "boolean");
        clearFirst.addProperty("description", "Clear existing text before typing (default: true)");
        props.add("clearFirst", clearFirst);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("selector");
        required.add("text");
        schema.add("required", required);

        return new ToolDefinition(
            "element_type",
            "Type text into an input field. Optionally clear existing text first.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String selector = params.get("selector").getAsString();
        String text = params.get("text").getAsString();
        String type = params.has("selectorType") ? params.get("selectorType").getAsString() : "id";
        boolean clearFirst = !params.has("clearFirst") || params.get("clearFirst").getAsBoolean();

        try {
            WebElement element = TapElementTool.findElement(driver, selector, type);
            if (element == null) {
                return ToolResult.error("Input field not found: " + selector);
            }
            if (clearFirst) {
                element.clear();
            }
            element.sendKeys(text);
            return ToolResult.success("Typed '" + text + "' into " + selector);
        } catch (Exception e) {
            log.error("Type failed", e);
            return ToolResult.error("Type failed: " + e.getMessage());
        }
    }
}
