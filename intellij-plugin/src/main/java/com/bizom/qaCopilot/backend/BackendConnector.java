package com.bizom.qaCopilot.backend;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.intellij.openapi.diagnostic.Logger;
import okhttp3.*;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

public class BackendConnector {
    private static final Logger LOG = Logger.getInstance(BackendConnector.class);
    private static final String API_URL = "http://localhost:8000/api";
    private final OkHttpClient client = new OkHttpClient.Builder()
        .connectTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .readTimeout(300, java.util.concurrent.TimeUnit.SECONDS)  // 5 minutes for long-running navigation
        .writeTimeout(60, java.util.concurrent.TimeUnit.SECONDS)
        .build();

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
