package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.nativekey.AndroidKey;
import io.appium.java_client.android.nativekey.KeyEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Press a hardware/system key on the device.
 * Equivalent to Playwright's browser_press_key but for Android system keys.
 */
public class PressKeyTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(PressKeyTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject key = new JsonObject();
        key.addProperty("type", "string");
        key.addProperty("description", "Key to press: home, back, enter, menu, volume_up, volume_down, power, tab, delete, search, camera, app_switch");
        props.add("key", key);

        schema.add("properties", props);

        JsonArray required = new JsonArray();
        required.add("key");
        schema.add("required", required);

        return new ToolDefinition(
            "device_press_key",
            "Press a hardware or system key on the device (home, back, enter, menu, volume, etc.)",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String keyName = params.get("key").getAsString().toLowerCase().trim();

        try {
            AndroidKey androidKey = mapKey(keyName);
            if (androidKey == null) {
                return ToolResult.error("Unknown key: " + keyName + ". Valid keys: home, back, enter, menu, volume_up, volume_down, power, tab, delete, search, camera, app_switch");
            }
            driver.pressKey(new KeyEvent(androidKey));
            return ToolResult.success("Pressed key: " + keyName);
        } catch (Exception e) {
            log.error("Press key failed", e);
            return ToolResult.error("Press key failed: " + e.getMessage());
        }
    }

    private AndroidKey mapKey(String keyName) {
        return switch (keyName) {
            case "home" -> AndroidKey.HOME;
            case "back" -> AndroidKey.BACK;
            case "enter", "return" -> AndroidKey.ENTER;
            case "menu" -> AndroidKey.MENU;
            case "volume_up" -> AndroidKey.VOLUME_UP;
            case "volume_down" -> AndroidKey.VOLUME_DOWN;
            case "power" -> AndroidKey.POWER;
            case "tab" -> AndroidKey.TAB;
            case "delete", "backspace" -> AndroidKey.DEL;
            case "search" -> AndroidKey.SEARCH;
            case "camera" -> AndroidKey.CAMERA;
            case "app_switch", "recent", "recents" -> AndroidKey.APP_SWITCH;
            case "notification" -> AndroidKey.NOTIFICATION;
            case "settings" -> AndroidKey.SETTINGS;
            case "space" -> AndroidKey.SPACE;
            default -> null;
        };
    }
}
