package com.appium.mcp.model;

import com.google.gson.JsonObject;

public class JsonRpcRequest {
    private String jsonrpc = "2.0";
    private String method;
    private JsonObject params;
    private Object id;

    public String getJsonrpc() { return jsonrpc; }
    public String getMethod() { return method; }
    public JsonObject getParams() { return params; }
    public Object getId() { return id; }

    public void setJsonrpc(String jsonrpc) { this.jsonrpc = jsonrpc; }
    public void setMethod(String method) { this.method = method; }
    public void setParams(JsonObject params) { this.params = params; }
    public void setId(Object id) { this.id = id; }
}
