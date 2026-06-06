package com.appium.mcp.model;

import com.google.gson.JsonElement;

public class JsonRpcResponse {
    private final String jsonrpc = "2.0";
    private Object id;
    private JsonElement result;
    private JsonRpcError error;

    public static JsonRpcResponse success(Object id, JsonElement result) {
        JsonRpcResponse r = new JsonRpcResponse();
        r.id = id;
        r.result = result;
        return r;
    }

    public static JsonRpcResponse error(Object id, int code, String message) {
        JsonRpcResponse r = new JsonRpcResponse();
        r.id = id;
        r.error = new JsonRpcError(code, message);
        return r;
    }

    public String getJsonrpc() { return jsonrpc; }
    public Object getId() { return id; }
    public JsonElement getResult() { return result; }
    public JsonRpcError getError() { return error; }

    public static class JsonRpcError {
        private final int code;
        private final String message;

        public JsonRpcError(int code, String message) {
            this.code = code;
            this.message = message;
        }

        public int getCode() { return code; }
        public String getMessage() { return message; }
    }
}
