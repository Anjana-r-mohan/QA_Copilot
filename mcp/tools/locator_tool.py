class LocatorTool:

    def get_best_locator(
        self,
        element
    ):

        if element.get("resource_id"):

            return {
                "strategy": "id",
                "value": element["resource_id"]
            }

        if element.get("accessibility_id"):

            return {
                "strategy": "accessibility_id",
                "value": element["accessibility_id"]
            }

        if element.get("xpath"):

            return {
                "strategy": "xpath",
                "value": element["xpath"]
            }

        return None