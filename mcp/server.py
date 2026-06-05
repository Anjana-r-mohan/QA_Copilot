from mcp.tools.connect_device_tool import ConnectDeviceTool
from mcp.tools.explore_screen import ExploreScreenTool
from mcp.tools.perform_action_tool import PerformActionTool
from mcp.tools.save_locator_tool import SaveLocatorTool
from mcp.memory import MemoryStore
from mcp.protocol import MCPMethod, MCPResponse


class MCPServer:

    def __init__(
        self,
        driver_manager,
        ui_explorer
    ):

        self.tools = {}
        self.memory = MemoryStore()

        self.register(
            ConnectDeviceTool(driver_manager, ui_explorer)
        )

        self.register(
            ExploreScreenTool(ui_explorer, driver_manager)
        )

        self.register(
            PerformActionTool(driver_manager)
        )

        self.register(
            SaveLocatorTool()
        )

    def register(self, tool):

        self.tools[tool.name] = tool

    def call_tool(
        self,
        tool_name,
        params
    ):
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }

        try:
            return tool.execute(params or {})
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc)
            }

    def list_tools(self):
        """Return lightweight tool metadata for MCP discovery."""
        return [
            {
                "name": tool.name,
                "description": getattr(tool, "description", "")
            }
            for tool in self.tools.values()
        ]

    def handle_request(self, request):
        """Handle protocol-level MCP requests from /mcp endpoint."""
        request_id = getattr(request, "id", "unknown")

        try:
            method = request.method
            params = request.params or {}
            session_id = request.session_id

            if method == MCPMethod.LIST_TOOLS:
                return MCPResponse.success_response(
                    request_id,
                    {
                        "tools": self.list_tools()
                    }
                )

            if method == MCPMethod.CALL_TOOL:
                tool_name = params.get("tool_name") or params.get("name")
                arguments = params.get("arguments") or params.get("params") or {}

                if not tool_name:
                    return MCPResponse.error_response(request_id, "Missing tool_name")

                result = self.call_tool(tool_name, arguments)
                return MCPResponse.success_response(request_id, result)

            if method == MCPMethod.CREATE_SESSION:
                session = self.memory.create_session(
                    session_id=session_id,
                    metadata=params.get("metadata")
                )
                return MCPResponse.success_response(request_id, session.to_dict())

            if method == MCPMethod.GET_SESSION:
                sid = session_id or params.get("session_id")
                if not sid:
                    return MCPResponse.error_response(request_id, "Missing session_id")

                session = self.memory.get_session(sid)
                if not session:
                    return MCPResponse.error_response(request_id, f"Session not found: {sid}")

                return MCPResponse.success_response(request_id, session.to_dict())

            if method == MCPMethod.END_SESSION:
                sid = session_id or params.get("session_id")
                if not sid:
                    return MCPResponse.error_response(request_id, "Missing session_id")

                self.memory.end_session(sid)
                return MCPResponse.success_response(request_id, {"ended": True, "session_id": sid})

            if method == MCPMethod.SET_MEMORY:
                sid = session_id or params.get("session_id")
                key = params.get("key")
                value = params.get("value")

                if not sid:
                    return MCPResponse.error_response(request_id, "Missing session_id")
                if not key:
                    return MCPResponse.error_response(request_id, "Missing key")

                self.memory.set_memory(sid, key, value, tags=params.get("tags"))
                return MCPResponse.success_response(request_id, {"stored": True})

            if method == MCPMethod.GET_MEMORY:
                sid = session_id or params.get("session_id")
                key = params.get("key")

                if not sid:
                    return MCPResponse.error_response(request_id, "Missing session_id")
                if not key:
                    return MCPResponse.success_response(
                        request_id,
                        {"memory": self.memory.get_all_memory(sid)}
                    )

                return MCPResponse.success_response(
                    request_id,
                    {"key": key, "value": self.memory.get_memory(sid, key)}
                )

            if method == MCPMethod.SEARCH_MEMORY:
                sid = session_id or params.get("session_id")
                if not sid:
                    return MCPResponse.error_response(request_id, "Missing session_id")

                items = self.memory.search_memory(
                    sid,
                    query=params.get("query"),
                    tags=params.get("tags"),
                    limit=params.get("limit", 10)
                )
                return MCPResponse.success_response(
                    request_id,
                    {"items": [item.to_dict() for item in items]}
                )

            if method == MCPMethod.CLEAR_MEMORY:
                sid = session_id or params.get("session_id")
                if not sid:
                    return MCPResponse.error_response(request_id, "Missing session_id")

                self.memory.clear_memory(sid)
                return MCPResponse.success_response(request_id, {"cleared": True})

            return MCPResponse.error_response(request_id, f"Unsupported method: {method}")

        except Exception as exc:
            return MCPResponse.error_response(request_id, str(exc))