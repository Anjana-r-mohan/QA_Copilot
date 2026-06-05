# mcp/tools/click_element.py

class ClickElementTool:

    def execute(self, xpath):
        element = driver.find_element("xpath", xpath)
        element.click()

        return {
            "success": True
        }