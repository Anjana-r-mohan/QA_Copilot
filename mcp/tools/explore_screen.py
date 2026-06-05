from ..tool import MCPTool


class ExploreScreenTool(MCPTool):

    name = "explore_screen"
    description = "Get current screen XML and elements"

    def __init__(self, ui_explorer, driver_manager=None):
        self.ui_explorer = ui_explorer
        self.driver_manager = driver_manager

    def execute(self, params):
        if self.ui_explorer.driver is None and self.driver_manager is not None:
            self.ui_explorer.driver = self.driver_manager.driver

        result = self.ui_explorer.explore_current_screen(
            "CurrentScreen"
        )

        return result