from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException
import time


class AppiumTool:

    def __init__(self, driver):
        self.driver = driver

    def click(self, locator_type, locator_value):

        try:

            element = self.driver.find_element(
                locator_type,
                locator_value
            )

            element.click()

            return {
                "success": True,
                "action": "click"
            }

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }

    def type_text(
        self,
        locator_type,
        locator_value,
        value
    ):

        try:

            element = self.driver.find_element(
                locator_type,
                locator_value
            )

            element.clear()
            element.send_keys(value)

            return {
                "success": True,
                "action": "type"
            }

        except Exception as e:

            return {
                "success": False,
                "error": str(e)
            }

    def is_visible(
        self,
        locator_type,
        locator_value
    ):

        try:

            element = self.driver.find_element(
                locator_type,
                locator_value
            )

            return {
                "success": True,
                "visible": element.is_displayed()
            }

        except NoSuchElementException:

            return {
                "success": False,
                "visible": False
            }

    def wait(
        self,
        seconds=2
    ):

        time.sleep(seconds)

        return {
            "success": True
        }

    def swipe_up(self):

        size = self.driver.get_window_size()

        start_x = size["width"] // 2

        start_y = int(size["height"] * 0.8)

        end_y = int(size["height"] * 0.3)

        self.driver.swipe(
            start_x,
            start_y,
            start_x,
            end_y,
            500
        )

        return {
            "success": True
        }