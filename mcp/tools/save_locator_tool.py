import json
import os

from ..tool import MCPTool


class SaveLocatorTool(MCPTool):

    name = "save_locator"

    def execute(self, params):

        output_file = params["file"]

        locator = params["locator"]

        os.makedirs(
            os.path.dirname(output_file),
            exist_ok=True
        )

        with open(output_file, "a") as f:
            f.write(
                json.dumps(locator) + "\n"
            )

        return {
            "success": True
        }