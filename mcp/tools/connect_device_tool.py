from ..tool import MCPTool


class ConnectDeviceTool(MCPTool):

    name = "connect_device"
    description = "Connect to Android/iOS device"

    def __init__(self, driver_manager, ui_explorer=None):
        self.driver_manager = driver_manager
        self.ui_explorer = ui_explorer

    def execute(self, params):
        device_name = params.get("device_name")
        app_package = params.get("app_package")
        app_activity = params.get("app_activity")

        result = self.driver_manager.connect(
            device_name=device_name,
            app_package=app_package,
            app_activity=app_activity
        )

        success = bool(result.get("success"))

        # Keep MCP tools on the same live Appium session.
        if success and self.ui_explorer is not None:
            self.ui_explorer.driver = self.driver_manager.driver

        return {
            "success": success,
            "device": device_name,
            "connected": bool(result.get("connected")),
            "message": result.get("message"),
            "error": result.get("error"),
        }