package com.appium.mcp.driver;

import io.appium.java_client.android.AndroidDriver;
import io.appium.java_client.android.options.UiAutomator2Options;
import org.openqa.selenium.remote.DesiredCapabilities;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.MalformedURLException;
import java.net.URL;
import java.time.Duration;

public class DriverManager {
    private static final Logger log = LoggerFactory.getLogger(DriverManager.class);
    private static DriverManager instance;
    private AndroidDriver driver;

    private DriverManager() {}

    public static synchronized DriverManager getInstance() {
        if (instance == null) {
            instance = new DriverManager();
        }
        return instance;
    }

    public AndroidDriver connect(String appiumUrl, String deviceName, String platformVersion,
                                  String appPackage, String appActivity) throws MalformedURLException {
        if (driver != null) {
            try {
                driver.getPageSource();
                log.info("Reusing existing driver session");
                return driver;
            } catch (Exception e) {
                log.info("Existing session stale, creating new one");
                driver = null;
            }
        }

        UiAutomator2Options options = new UiAutomator2Options();
        options.setDeviceName(deviceName != null ? deviceName : "emulator-5554");
        if (platformVersion != null) {
            options.setPlatformVersion(platformVersion);
        }
        options.setAutomationName("UiAutomator2");
        options.setNoReset(true);
        options.setNewCommandTimeout(Duration.ofSeconds(300));

        if (appPackage != null) {
            options.setAppPackage(appPackage);
        }
        if (appActivity != null) {
            options.setAppActivity(appActivity);
        }

        String url = appiumUrl != null ? appiumUrl : "http://127.0.0.1:4723";
        String deviceDisplay = deviceName != null ? deviceName : "emulator-5554";
        log.info("Connecting to Appium at {} with device {}", url, deviceDisplay);
        driver = new AndroidDriver(new URL(url), options);
        log.info("Connected. Session ID: {}", driver.getSessionId());
        return driver;
    }

    public AndroidDriver getDriver() {
        return driver;
    }

    public boolean isConnected() {
        if (driver == null) return false;
        try {
            driver.getPageSource();
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public void disconnect() {
        if (driver != null) {
            try {
                driver.quit();
            } catch (Exception e) {
                log.warn("Error disconnecting: {}", e.getMessage());
            }
            driver = null;
        }
    }
}
