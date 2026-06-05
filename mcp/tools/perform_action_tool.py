from ..tool import MCPTool
import time


class PerformActionTool(MCPTool):

    name = "perform_action"
    description = "Click, enter text, scroll, back"

    def __init__(self, driver_manager):
        self.driver_manager = driver_manager

    def execute(self, params):

        driver = self.driver_manager.driver

        if driver is None:
            return {
                "success": False,
                "error": "No active device session. Connect device first."
            }

        action = params.get("action")

        if action == "click":

            xpath = params["xpath"]

            element = driver.find_element(
                "xpath",
                xpath
            )

            try:
                element.click()
            except Exception:
                try:
                    # UiAutomator2 fallback: native gesture click by element id.
                    driver.execute_script("mobile: clickGesture", {"elementId": element.id})
                except Exception:
                    # Final fallback: click by element center coordinates.
                    rect = element.rect
                    center_x = int(rect["x"] + rect["width"] / 2)
                    center_y = int(rect["y"] + rect["height"] / 2)
                    driver.execute_script("mobile: clickGesture", {"x": center_x, "y": center_y})

            return {
                "success": True
            }

        elif action == "enter":

            xpath = params["xpath"]

            value = params["value"]

            element = driver.find_element(
                "xpath",
                xpath
            )

            element.clear()
            element.send_keys(value)

            return {
                "success": True
            }

        elif action == "scroll":
            direction = str(params.get("direction", "down")).lower()
            if direction not in {"up", "down", "left", "right"}:
                direction = "down"

            size = driver.get_window_size()
            width = int(size.get("width", 1080))
            height = int(size.get("height", 1920))

            # Use a safe center viewport region to avoid system gesture edges.
            left = int(width * 0.1)
            top = int(height * 0.2)
            box_width = int(width * 0.8)
            box_height = int(height * 0.6)

            try:
                driver.execute_script(
                    "mobile: scrollGesture",
                    {
                        "left": left,
                        "top": top,
                        "width": box_width,
                        "height": box_height,
                        "direction": direction,
                        "percent": 0.75,
                    },
                )
            except Exception:
                try:
                    driver.execute_script(
                        "mobile: swipeGesture",
                        {
                            "left": left,
                            "top": top,
                            "width": box_width,
                            "height": box_height,
                            "direction": direction,
                            "percent": 0.75,
                        },
                    )
                except Exception:
                    # Last resort for older servers/drivers.
                    start_x = width // 2
                    if direction == "down":
                        start_y = int(height * 0.75)
                        end_y = int(height * 0.35)
                    elif direction == "up":
                        start_y = int(height * 0.35)
                        end_y = int(height * 0.75)
                    elif direction == "left":
                        start_x = int(width * 0.75)
                        end_x = int(width * 0.25)
                        start_y = int(height * 0.5)
                        driver.swipe(start_x, start_y, end_x, start_y, 450)
                        return {
                            "success": True
                        }
                    else:
                        start_x = int(width * 0.25)
                        end_x = int(width * 0.75)
                        start_y = int(height * 0.5)
                        driver.swipe(start_x, start_y, end_x, start_y, 450)
                        return {
                            "success": True
                        }

                    driver.swipe(start_x, start_y, start_x, end_y, 450)

            return {
                "success": True
            }

        elif action == "back":
            try:
                driver.back()
            except Exception:
                # Android fallback for flaky back dispatch on some emulators.
                driver.press_keycode(4)

            return {
                "success": True
            }

        elif action == "relaunch_app":

            app_package = params.get("app_package")
            app_activity = params.get("app_activity")

            if not app_package:
                return {
                    "success": False,
                    "error": "app_package is required for relaunch_app"
                }

            try:
                try:
                    driver.terminate_app(app_package)
                except Exception:
                    pass

                time.sleep(1)

                launched = False
                if app_activity:
                    try:
                        driver.execute_script(
                            "mobile: startActivity",
                            {"component": f"{app_package}/{app_activity}"}
                        )
                        launched = True
                    except Exception:
                        launched = False

                if not launched:
                    driver.activate_app(app_package)

                time.sleep(1)
                return {
                    "success": True,
                    "relaunch": True
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to relaunch app: {e}"
                }

        return {
            "success": False,
            "error": f"Unknown action {action}"
        }