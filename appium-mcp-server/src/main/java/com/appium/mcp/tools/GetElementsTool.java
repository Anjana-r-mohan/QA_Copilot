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
import org.w3c.dom.*;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.XMLConstants;
import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.List;

public class GetElementsTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(GetElementsTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject filter = new JsonObject();
        filter.addProperty("type", "string");
        filter.addProperty("description", "Filter elements: 'clickable', 'editable', 'all' (default: all)");
        props.add("filter", filter);

        schema.add("properties", props);

        return new ToolDefinition(
            "screen_get_elements",
            "Get all UI elements visible on the current screen. Returns element tree with resource-ids, text, content-desc, class names, and bounds. Use this to understand what's on screen before tapping or typing.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        String filter = params.has("filter") ? params.get("filter").getAsString() : "all";

        try {
            String pageSource = driver.getPageSource();
            List<ElementInfo> elements = parseElements(pageSource, filter);

            StringBuilder sb = new StringBuilder();
            sb.append("Screen elements (").append(elements.size()).append(" found):\n\n");

            for (int i = 0; i < elements.size(); i++) {
                ElementInfo el = elements.get(i);
                sb.append(i + 1).append(". ");
                sb.append("[").append(el.className).append("]");
                if (el.resourceId != null && !el.resourceId.isEmpty()) {
                    sb.append(" id=").append(el.resourceId);
                }
                if (el.text != null && !el.text.isEmpty()) {
                    sb.append(" text=\"").append(el.text).append("\"");
                }
                if (el.contentDesc != null && !el.contentDesc.isEmpty()) {
                    sb.append(" desc=\"").append(el.contentDesc).append("\"");
                }
                sb.append(" clickable=").append(el.clickable);
                sb.append(" bounds=").append(el.bounds);
                sb.append("\n");
            }

            return ToolResult.success(sb.toString());
        } catch (Exception e) {
            log.error("Get elements failed", e);
            return ToolResult.error("Failed to get elements: " + e.getMessage());
        }
    }

    private List<ElementInfo> parseElements(String xml, String filter) {
        List<ElementInfo> elements = new ArrayList<>();
        try {
            DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
            dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
            dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            dbf.setFeature("http://xml.org/sax/features/external-general-entities", false);
            dbf.setFeature("http://xml.org/sax/features/external-parameter-entities", false);

            Document doc = dbf.newDocumentBuilder()
                .parse(new ByteArrayInputStream(xml.getBytes()));

            collectElements(doc.getDocumentElement(), elements, filter);
        } catch (Exception e) {
            log.error("XML parse error", e);
        }
        return elements;
    }

    private void collectElements(Node node, List<ElementInfo> elements, String filter) {
        if (node.getNodeType() == Node.ELEMENT_NODE) {
            Element el = (Element) node;
            String className = el.getNodeName();
            String resourceId = el.getAttribute("resource-id");
            String text = el.getAttribute("text");
            String contentDesc = el.getAttribute("content-desc");
            String bounds = el.getAttribute("bounds");
            boolean clickable = "true".equals(el.getAttribute("clickable"));
            boolean editable = className.contains("EditText");

            boolean hasContent = (resourceId != null && !resourceId.isEmpty())
                || (text != null && !text.isEmpty())
                || (contentDesc != null && !contentDesc.isEmpty());

            boolean include = switch (filter.toLowerCase()) {
                case "clickable" -> clickable && hasContent;
                case "editable" -> editable;
                default -> hasContent;
            };

            if (include) {
                ElementInfo info = new ElementInfo();
                info.className = className;
                info.resourceId = resourceId;
                info.text = text;
                info.contentDesc = contentDesc;
                info.bounds = bounds;
                info.clickable = clickable;
                elements.add(info);
            }
        }

        NodeList children = node.getChildNodes();
        for (int i = 0; i < children.getLength(); i++) {
            collectElements(children.item(i), elements, filter);
        }
    }

    private static class ElementInfo {
        String className;
        String resourceId;
        String text;
        String contentDesc;
        String bounds;
        boolean clickable;
    }
}
