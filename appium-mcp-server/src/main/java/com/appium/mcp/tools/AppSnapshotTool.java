package com.appium.mcp.tools;

import com.appium.mcp.driver.DriverManager;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.JsonObject;
import io.appium.java_client.android.AndroidDriver;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.w3c.dom.*;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.XMLConstants;
import java.io.ByteArrayInputStream;

/**
 * Captures a structured accessibility snapshot of the current screen.
 * This is the mobile equivalent of Playwright MCP's browser_snapshot -
 * the primary way the LLM "sees" and reasons about the app UI.
 *
 * Returns an indented tree of UI elements with their roles, names, states,
 * and selector hints that the LLM can use with element_tap, element_type, etc.
 */
public class AppSnapshotTool implements McpTool {
    private static final Logger log = LoggerFactory.getLogger(AppSnapshotTool.class);

    @Override
    public ToolDefinition getDefinition() {
        JsonObject schema = new JsonObject();
        schema.addProperty("type", "object");

        JsonObject props = new JsonObject();

        JsonObject depth = new JsonObject();
        depth.addProperty("type", "number");
        depth.addProperty("description", "Maximum depth of the UI tree to return (default: unlimited)");
        props.add("depth", depth);

        JsonObject compact = new JsonObject();
        compact.addProperty("type", "boolean");
        compact.addProperty("description", "If true, only show elements with text, id, or content-desc (default: false)");
        props.add("compact", compact);

        schema.add("properties", props);

        return new ToolDefinition(
            "app_snapshot",
            "Capture accessibility snapshot of the current app screen. This is better than screenshot - it returns a structured tree of UI elements that you can reason about and interact with. Use this as the primary way to understand what's on screen.",
            schema
        );
    }

    @Override
    public ToolResult execute(JsonObject params) {
        AndroidDriver driver = DriverManager.getInstance().getDriver();
        if (driver == null) return ToolResult.error("Not connected. Call device_connect first.");

        int maxDepth = params.has("depth") ? params.get("depth").getAsInt() : Integer.MAX_VALUE;
        boolean compact = params.has("compact") && params.get("compact").getAsBoolean();

        try {
            String pageSource = driver.getPageSource();
            String snapshot = buildSnapshot(pageSource, maxDepth, compact);
            return ToolResult.success(snapshot);
        } catch (Exception e) {
            log.error("Snapshot failed", e);
            return ToolResult.error("Snapshot failed: " + e.getMessage());
        }
    }

    private String buildSnapshot(String xml, int maxDepth, boolean compact) throws Exception {
        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
        dbf.setFeature("http://xml.org/sax/features/external-general-entities", false);
        dbf.setFeature("http://xml.org/sax/features/external-parameter-entities", false);

        Document doc = dbf.newDocumentBuilder()
            .parse(new ByteArrayInputStream(xml.getBytes()));

        StringBuilder sb = new StringBuilder();
        sb.append("App UI Snapshot:\n");
        buildTree(doc.getDocumentElement(), sb, 0, maxDepth, compact);
        return sb.toString();
    }

    private void buildTree(Node node, StringBuilder sb, int indent, int maxDepth, boolean compact) {
        if (indent > maxDepth) return;
        if (node.getNodeType() != Node.ELEMENT_NODE) return;

        Element el = (Element) node;
        String className = el.getNodeName();
        String resourceId = el.getAttribute("resource-id");
        String text = el.getAttribute("text");
        String contentDesc = el.getAttribute("content-desc");
        String bounds = el.getAttribute("bounds");
        boolean clickable = "true".equals(el.getAttribute("clickable"));
        boolean focusable = "true".equals(el.getAttribute("focusable"));
        boolean enabled = !"false".equals(el.getAttribute("enabled"));
        boolean checked = "true".equals(el.getAttribute("checked"));
        boolean selected = "true".equals(el.getAttribute("selected"));
        boolean scrollable = "true".equals(el.getAttribute("scrollable"));
        boolean longClickable = "true".equals(el.getAttribute("long-clickable"));
        boolean editable = className.contains("EditText");
        boolean checkable = "true".equals(el.getAttribute("checkable"));

        // Determine the "role" in accessibility terms
        String role = mapToRole(className, clickable, editable, checkable, scrollable);

        boolean hasContent = (resourceId != null && !resourceId.isEmpty())
            || (text != null && !text.isEmpty())
            || (contentDesc != null && !contentDesc.isEmpty());

        // In compact mode, skip nodes with no useful info (but still recurse children)
        boolean showThisNode = !compact || hasContent || clickable || editable || scrollable;

        if (showThisNode) {
            String pad = "  ".repeat(indent);
            sb.append(pad).append("- ").append(role);

            // Accessible name (text or content-desc)
            String accessibleName = (contentDesc != null && !contentDesc.isEmpty()) ? contentDesc
                : (text != null && !text.isEmpty()) ? text : null;
            if (accessibleName != null) {
                sb.append(" \"").append(accessibleName).append("\"");
            }

            // Selector hint for the LLM
            if (resourceId != null && !resourceId.isEmpty()) {
                // Strip package prefix for cleaner display
                String shortId = resourceId.contains(":id/")
                    ? resourceId.substring(resourceId.indexOf(":id/") + 4)
                    : resourceId;
                sb.append(" [id=").append(shortId).append("]");
            }

            // State info
            StringBuilder states = new StringBuilder();
            if (!enabled) states.append(" disabled");
            if (checked) states.append(" checked");
            if (selected) states.append(" selected");
            if (editable) states.append(" editable");
            if (scrollable) states.append(" scrollable");
            if (longClickable) states.append(" long-clickable");
            if (states.length() > 0) {
                sb.append(" {").append(states.toString().trim()).append("}");
            }

            if (bounds != null && !bounds.isEmpty()) {
                sb.append(" ").append(bounds);
            }

            sb.append("\n");
        }

        // Recurse children
        NodeList children = node.getChildNodes();
        int childIndent = showThisNode ? indent + 1 : indent;
        for (int i = 0; i < children.getLength(); i++) {
            buildTree(children.item(i), sb, childIndent, maxDepth, compact);
        }
    }

    private String mapToRole(String className, boolean clickable, boolean editable,
                             boolean checkable, boolean scrollable) {
        // Map Android widget classes to semantic roles (like Playwright's ARIA roles)
        if (className.contains("EditText")) return "textbox";
        if (className.contains("Button")) return "button";
        if (className.contains("CheckBox")) return "checkbox";
        if (className.contains("RadioButton")) return "radio";
        if (className.contains("Switch") || className.contains("ToggleButton")) return "switch";
        if (className.contains("ImageView")) return clickable ? "img-button" : "img";
        if (className.contains("TextView")) return clickable ? "link" : "text";
        if (className.contains("RecyclerView") || className.contains("ListView")) return "list";
        if (className.contains("ScrollView") || className.contains("HorizontalScrollView")) return "scroll-container";
        if (className.contains("ViewPager")) return "pager";
        if (className.contains("TabLayout") || className.contains("TabWidget")) return "tabbar";
        if (className.contains("Toolbar") || className.contains("ActionBar")) return "toolbar";
        if (className.contains("ProgressBar")) return "progressbar";
        if (className.contains("SeekBar")) return "slider";
        if (className.contains("Spinner")) return "dropdown";
        if (className.contains("WebView")) return "webview";
        if (className.contains("ViewGroup") || className.contains("FrameLayout")
            || className.contains("LinearLayout") || className.contains("RelativeLayout")
            || className.contains("ConstraintLayout")) {
            if (clickable) return "clickable-container";
            if (scrollable) return "scroll-container";
            return "group";
        }
        if (clickable) return "clickable";
        return className.substring(className.lastIndexOf('.') + 1);
    }
}
