package com.bizom.scriptSherpa.backend;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.intellij.openapi.diagnostic.Logger;
import okhttp3.*;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

public class BackendConnector {
    private static final Logger LOG = Logger.getInstance(BackendConnector.class);
    private static final String API_URL = "http://localhost:8000/api";
    private final OkHttpClient client = new OkHttpClient.Builder()
        .connectTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(600, java.util.concurrent.TimeUnit.SECONDS)  // 10 minutes for streaming
        .writeTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .build();

    /**
     * Navigate UI with REAL-TIME SSE streaming for live progress updates
     * @param progressCallback Called for each progress update
     */
    public NavigationResult navigateUIWithProgress(String command, String deviceName, 
                                                    String appPackage, String appActivity, 
                                                    String workspacePath,
                                                    Consumer<ProgressUpdate> progressCallback) throws IOException {
        LOG.info("🚀 Starting streaming navigation: " + command);

        // Send initial progress
        progressCallback.accept(new ProgressUpdate("understanding", "🎯 Understanding your command...", null));

        JsonObject requestBody = new JsonObject();
        requestBody.addProperty("command", command);
        requestBody.addProperty("device_name", deviceName);
        requestBody.addProperty("app_package", appPackage);
        requestBody.addProperty("app_activity", appActivity);
        requestBody.addProperty("workspace_path", workspacePath);

        RequestBody body = RequestBody.create(
            requestBody.toString(),
            MediaType.parse("application/json")
        );

        Request request = new Request.Builder()
            .url(API_URL + "/navigate-ui-stream")
            .post(body)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("API call failed: " + response.code());
            }

            // Read SSE stream line by line for real-time updates
            BufferedReader reader = new BufferedReader(new InputStreamReader(response.body().byteStream()));
            String line;
            NavigationResult finalResult = null;

            while ((line = reader.readLine()) != null) {
                if (line.startsWith("data: ")) {
                    String jsonData = line.substring(6); // Remove "data: " prefix
                    try {
                        JsonObject event = JsonParser.parseString(jsonData).getAsJsonObject();
                        String type = event.has("type") ? event.get("type").getAsString() : "unknown";
                        String message = event.has("message") ? event.get("message").getAsString() : "";

                        // Send REAL-TIME progress update to UI immediately
                        ProgressUpdate update = new ProgressUpdate(type, message, event);
                        progressCallback.accept(update);

                        // Check for completion
                        if ("complete".equals(type) && event.has("result")) {
                            JsonObject result = event.getAsJsonObject("result");
                            boolean success = result.has("success") && result.get("success").getAsBoolean();
                            int stepsExecuted = result.has("steps_executed") ? result.get("steps_executed").getAsInt() : 0;
                            int locatorsCollected = result.has("locators_collected") ? result.get("locators_collected").getAsInt() : 0;
                            String locatorsFile = result.has("locators_file") ? result.get("locators_file").getAsString() : "";
                            finalResult = new NavigationResult(success, stepsExecuted, locatorsCollected, locatorsFile);
                        } else if ("error".equals(type)) {
                            finalResult = new NavigationResult(false, 0, 0, "");
                        }
                    } catch (Exception e) {
                        LOG.warn("Failed to parse SSE event: " + jsonData, e);
                    }
                }
            }

            return finalResult != null ? finalResult : new NavigationResult(false, 0, 0, "");
        }
    }

    public NavigationResult navigateUI(String command, String deviceName, String appPackage, String appActivity, String workspacePath) throws IOException {
        LOG.info("Calling navigate-ui: " + command);

        JsonObject requestBody = new JsonObject();
        requestBody.addProperty("command", command);
        requestBody.addProperty("device_name", deviceName);
        requestBody.addProperty("app_package", appPackage);
        requestBody.addProperty("app_activity", appActivity);
        requestBody.addProperty("workspace_path", workspacePath);

        RequestBody body = RequestBody.create(
            requestBody.toString(),
            MediaType.parse("application/json")
        );

        Request request = new Request.Builder()
            .url(API_URL + "/navigate-ui")
            .post(body)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new IOException("API call failed: " + response.code());
            }

            String responseBody = response.body().string();
            JsonObject json = JsonParser.parseString(responseBody).getAsJsonObject();

            boolean success = json.has("success") && json.get("success").getAsBoolean();
            int stepsExecuted = json.has("steps_executed") ? json.get("steps_executed").getAsInt() : 0;
            int locatorsCollected = json.has("locators_collected") ? json.get("locators_collected").getAsInt() : 0;
            String locatorsFile = json.has("locators_file") ? json.get("locators_file").getAsString() : "";

            LOG.info("Navigation result: success=" + success + ", steps=" + stepsExecuted + ", locators=" + locatorsCollected);

            return new NavigationResult(success, stepsExecuted, locatorsCollected, locatorsFile);
        }
    }

    public static class ProgressUpdate {
        public final String type;
        public final String message;
        public final JsonObject data;

        public ProgressUpdate(String type, String message, JsonObject data) {
            this.type = type;
            this.message = message;
            this.data = data;
        }
    }

    public static class NavigationResult {
        public final boolean success;
        public final int stepsExecuted;
        public final int locatorsCollected;
        public final String locatorsFile;

        public NavigationResult(boolean success, int stepsExecuted, int locatorsCollected, String locatorsFile) {
            this.success = success;
            this.stepsExecuted = stepsExecuted;
            this.locatorsCollected = locatorsCollected;
            this.locatorsFile = locatorsFile;
        }
    }
}
