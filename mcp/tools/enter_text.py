# mcp/tools/enter_text.py

class EnterTextTool:

    def execute(self, xpath, value):
        element = driver.find_element("xpath", xpath)
        element.send_keys(value)

        return {
            "success": True
        }