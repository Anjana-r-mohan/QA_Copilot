package com.appium.mcp.model;

import com.google.gson.JsonObject;
import java.util.List;

public class ToolDefinition {
    private final String name;
    private final String description;
    private final JsonObject inputSchema;

    public ToolDefinition(String name, String description, JsonObject inputSchema) {
        this.name = name;
        this.description = description;
        this.inputSchema = inputSchema;
    }

    public String getName() { return name; }
    public String getDescription() { return description; }
    public JsonObject getInputSchema() { return inputSchema; }

    public JsonObject toJson() {
        JsonObject obj = new JsonObject();
        obj.addProperty("name", name);
        obj.addProperty("description", description);
        obj.add("inputSchema", inputSchema);
        return obj;
    }
}
