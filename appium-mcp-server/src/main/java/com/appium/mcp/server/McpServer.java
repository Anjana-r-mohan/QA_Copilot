package com.appium.mcp.server;

import com.appium.mcp.model.JsonRpcRequest;
import com.appium.mcp.model.JsonRpcResponse;
import com.appium.mcp.model.ToolDefinition;
import com.appium.mcp.model.ToolResult;
import com.google.gson.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.*;
import java.nio.charset.StandardCharsets;

/**
 * MCP Server that communicates over stdio using JSON-RPC 2.0.
 * Exactly mirrors the Playwright MCP server protocol.
 */
public class McpServer {
    private static final Logger log = LoggerFactory.getLogger(McpServer.class);
    private static final Gson gson = new GsonBuilder().create();
    private static final String SERVER_NAME = "appium-mcp-server";
    private static final String SERVER_VERSION = "1.0.0";
    private static final String PROTOCOL_VERSION = "2024-11-05";

    private final ToolRegistry toolRegistry;
    private boolean initialized = false;

    public McpServer() {
        this.toolRegistry = new ToolRegistry();
    }

    public void start() throws IOException {
        log.info("Appium MCP Server starting (stdio mode)...");
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        PrintWriter writer = new PrintWriter(new OutputStreamWriter(System.out, StandardCharsets.UTF_8), true);

        String line;
        while ((line = reader.readLine()) != null) {
            line = line.trim();
            if (line.isEmpty()) continue;

            try {
                JsonRpcRequest request = gson.fromJson(line, JsonRpcRequest.class);
                JsonRpcResponse response = handleRequest(request);

                if (response != null) {
                    String json = gson.toJson(response);
                    writer.println(json);
                    writer.flush();
                }
            } catch (JsonSyntaxException e) {
                log.error("Invalid JSON: {}", line);
                JsonRpcResponse error = JsonRpcResponse.error(null, -32700, "Parse error");
                writer.println(gson.toJson(error));
                writer.flush();
            } catch (Exception e) {
                log.error("Error handling request", e);
                JsonRpcResponse error = JsonRpcResponse.error(null, -32603, "Internal error: " + e.getMessage());
                writer.println(gson.toJson(error));
                writer.flush();
            }
        }

        log.info("MCP Server shutting down");
    }

    private JsonRpcResponse handleRequest(JsonRpcRequest request) {
        String method = request.getMethod();
        Object id = request.getId();

        log.info("Received: {} (id={})", method, id);

        return switch (method) {
            case "initialize" -> handleInitialize(id, request.getParams());
            case "notifications/initialized" -> { initialized = true; yield null; } // notification, no response
            case "tools/list" -> handleToolsList(id);
            case "tools/call" -> handleToolsCall(id, request.getParams());
            case "ping" -> JsonRpcResponse.success(id, new JsonObject());
            default -> {
                log.warn("Unknown method: {}", method);
                yield JsonRpcResponse.error(id, -32601, "Method not found: " + method);
            }
        };
    }

    private JsonRpcResponse handleInitialize(Object id, JsonObject params) {
        JsonObject result = new JsonObject();

        // Protocol version
        result.addProperty("protocolVersion", PROTOCOL_VERSION);

        // Server capabilities
        JsonObject capabilities = new JsonObject();
        JsonObject toolsCap = new JsonObject();
        toolsCap.addProperty("listChanged", false);
        capabilities.add("tools", toolsCap);
        result.add("capabilities", capabilities);

        // Server info
        JsonObject serverInfo = new JsonObject();
        serverInfo.addProperty("name", SERVER_NAME);
        serverInfo.addProperty("version", SERVER_VERSION);
        result.add("serverInfo", serverInfo);

        log.info("Initialized MCP server: {} v{}", SERVER_NAME, SERVER_VERSION);
        return JsonRpcResponse.success(id, result);
    }

    private JsonRpcResponse handleToolsList(Object id) {
        JsonObject result = new JsonObject();
        JsonArray toolsArray = new JsonArray();

        for (ToolDefinition tool : toolRegistry.listTools()) {
            toolsArray.add(tool.toJson());
        }

        result.add("tools", toolsArray);
        return JsonRpcResponse.success(id, result);
    }

    private JsonRpcResponse handleToolsCall(Object id, JsonObject params) {
        if (params == null || !params.has("name")) {
            return JsonRpcResponse.error(id, -32602, "Missing tool name");
        }

        String toolName = params.get("name").getAsString();
        JsonObject arguments = params.has("arguments") ? params.getAsJsonObject("arguments") : new JsonObject();

        ToolResult result = toolRegistry.executeTool(toolName, arguments);
        return JsonRpcResponse.success(id, result.toJson());
    }

    public static void main(String[] args) throws IOException {
        // Redirect SLF4J/logging to stderr so stdout is pure JSON-RPC
        System.setProperty("org.slf4j.simpleLogger.logFile", "System.err");
        System.setProperty("org.slf4j.simpleLogger.defaultLogLevel", "info");

        McpServer server = new McpServer();
        server.start();
    }
}
