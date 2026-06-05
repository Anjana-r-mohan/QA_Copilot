package com.appium.mcp.model;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

public class ToolResult {
    private final boolean isError;
    private final String content;
    private final String imageBase64;
    private final String imageMimeType;

    private ToolResult(boolean isError, String content, String imageBase64, String imageMimeType) {
        this.isError = isError;
        this.content = content;
        this.imageBase64 = imageBase64;
        this.imageMimeType = imageMimeType;
    }

    public static ToolResult success(String content) {
        return new ToolResult(false, content, null, null);
    }

    public static ToolResult error(String content) {
        return new ToolResult(true, content, null, null);
    }

    public static ToolResult image(String base64Data, String mimeType) {
        return new ToolResult(false, null, base64Data, mimeType);
    }

    public static ToolResult imageWithText(String text, String base64Data, String mimeType) {
        return new ToolResult(false, text, base64Data, mimeType);
    }

    public JsonObject toJson() {
        JsonObject result = new JsonObject();
        JsonArray contentArray = new JsonArray();

        if (content != null) {
            JsonObject textContent = new JsonObject();
            textContent.addProperty("type", "text");
            textContent.addProperty("text", content);
            contentArray.add(textContent);
        }

        if (imageBase64 != null) {
            JsonObject imageContent = new JsonObject();
            imageContent.addProperty("type", "image");
            imageContent.addProperty("data", imageBase64);
            imageContent.addProperty("mimeType", imageMimeType != null ? imageMimeType : "image/png");
            contentArray.add(imageContent);
        }

        result.add("content", contentArray);
        result.addProperty("isError", isError);
        return result;
    }

    public boolean isError() { return isError; }
    public String getContent() { return content; }
}
