package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Wait for text to appear or disappear, or wait a specified time.
 * Direct equivalent of Playwright's browser_wait_for.
 */
public class WaitForTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(WaitForTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject time = new JsonObject();
        time.addProperty("type", "number");
        time.addProperty("description", "Time to wait in seconds");
        props.add("time", time);

        JsonObject text = new JsonObject();
        text.addProperty("type", "string");
        text.addProperty("description", "Text to wait for to appear on screen");
        props.add("text", text);

        JsonObject textGone = new JsonObject();
        textGone.addProperty("type", "string");
        textGone.addProperty("description", "Text to wait for to disappear from screen");
        props.add("textGone", textGone);

        JsonObject timeoutSec = new JsonObject();
        timeoutSec.addProperty("type", "number");
        timeoutSec.addProperty("description", "Maximum wait time in seconds (default: 30)");
        props.add("timeoutSeconds", timeoutSec);

        schema.add("properties", props);

        return new ToolDefinition(
            "app_wait_for",
            "Wait for text to appear or disappear on the screen, or wait a specified time. Equivalent to Playwright's browser_wait_for.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        // Simple time wait
        if (params.has("time")) {
            int seconds = params.get("time").getAsInt();
            if (seconds > 60) {
                return ToolResult.error("Maximum wait time is 60 seconds");
            }
            try {
                Thread.sleep(seconds * 1000L);
                return ToolResult.success("Waited " + seconds + " seconds");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return ToolResult.error("Wait interrupted");
            }
        }

        int timeout = params.has("timeoutSeconds") ? params.get("timeoutSeconds").getAsInt() : 30;
        if (timeout > 120) timeout = 120;

        // Wait for text to appear
        if (params.has("text")) {
            String text = params.get("text").getAsString();
            return waitForText(driver, text, true, timeout);
        }

        // Wait for text to disappear
        if (params.has("textGone")) {
            String text = params.get("textGone").getAsString();
            return waitForText(driver, text, false, timeout);
        }

        return ToolResult.error("Specify 'time', 'text', or 'textGone'");
    }

    private ToolResult waitForText(AndroidDriver driver, String text, boolean waitForPresent, int timeout) {
        long deadline = System.currentTimeMillis() + (timeout * 1000L);

        try {
            while (System.currentTimeMillis() < deadline) {
                String pageSource = driver.getPageSource();
                boolean found = pageSource.contains(text);

                if (waitForPresent && found) {
                    return ToolResult.success("Text appeared: \"" + text + "\"");
                }
                if (!waitForPresent && !found) {
                    return ToolResult.success("Text disappeared: \"" + text + "\"");
                }

                Thread.sleep(500);
            }

            if (waitForPresent) {
                return ToolResult.error("Timeout waiting for text: \"" + text + "\" (" + timeout + "s)");
            } else {
                return ToolResult.error("Timeout waiting for text to disappear: \"" + text + "\" (" + timeout + "s)");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return ToolResult.error("Wait interrupted");
        } catch (Exception e) {
            log.error("Wait for text failed", e);
            return ToolResult.error("Wait failed: " + e.getMessage());
        }
    }
}
