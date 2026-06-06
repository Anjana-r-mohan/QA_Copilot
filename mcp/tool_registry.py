"""
MCP Tool Registry
Central registry for all callable tools (actions)
"""

from typing import Dict, List, Any, Optional, Callable
from abc import ABC, abstractmethod
import time
from .protocol import ToolDefinition, ToolCall, ToolResult


class Tool(ABC):
    """
    Base class for all tools
    """
    
    @abstractmethod
    def name(self) -> str:
        """Tool name"""
        pass
    
    @abstractmethod
    def description(self) -> str:
        """Tool description"""
        pass
    
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """JSON schema for input parameters"""
        pass
    
    @abstractmethod
    def output_schema(self) -> Dict[str, Any]:
        """JSON schema for output"""
        pass
    
    @abstractmethod
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments"""
        pass
    
    def is_async(self) -> bool:
        """Whether tool supports async execution"""
        return False
    
    def to_definition(self) -> ToolDefinition:
        """Convert to tool definition"""
        return ToolDefinition(
            name=self.name(),
            description=self.description(),
            input_schema=self.input_schema(),
            output_schema=self.output_schema(),
            async_capable=self.is_async()
        )


class ToolRegistry:
    """
    Central registry for all tools
    """
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.async_results: Dict[str, ToolResult] = {}
    
    def register(self, tool: Tool):
        """Register a tool"""
        self.tools[tool.name()] = tool
        print(f"✅ Registered tool: {tool.name()}")
    
    def unregister(self, tool_name: str):
        """Unregister a tool"""
        if tool_name in self.tools:
            del self.tools[tool_name]
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get a tool by name"""
        return self.tools.get(tool_name)
    
    def list_tools(self) -> List[ToolDefinition]:
        """List all registered tools"""
        return [tool.to_definition() for tool in self.tools.values()]
    
    def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool synchronously
        """
        start_time = time.time()
        
        tool = self.get_tool(tool_call.tool_name)
        if not tool:
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output=None,
                error=f"Tool not found: {tool_call.tool_name}"
            )
        
        try:
            result = tool.execute(tool_call.arguments)
            result.execution_time = time.time() - start_time
            return result
        except Exception as e:
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output=None,
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    def execute_tool_async(self, tool_call: ToolCall) -> str:
        """
        Execute a tool asynchronously, return job ID
        """
        tool = self.get_tool(tool_call.tool_name)
        if not tool:
            result = ToolResult(
                call_id=tool_call.call_id,
                success=False,
                output=None,
                error=f"Tool not found: {tool_call.tool_name}"
            )
            self.async_results[tool_call.call_id] = result
            return tool_call.call_id
        
        # Execute in background (simplified - in production use proper async/threading)
        import threading
        
        def run_async():
            try:
                result = tool.execute(tool_call.arguments)
                self.async_results[tool_call.call_id] = result
            except Exception as e:
                self.async_results[tool_call.call_id] = ToolResult(
                    call_id=tool_call.call_id,
                    success=False,
                    output=None,
                    error=str(e)
                )
        
        thread = threading.Thread(target=run_async)
        thread.start()
        
        return tool_call.call_id
    
    def get_async_result(self, call_id: str) -> Optional[ToolResult]:
        """Get result of async tool call"""
        return self.async_results.get(call_id)


# ==================== APPIUM TOOLS ====================

class ConnectDeviceTool(Tool):
    """Tool to connect to Android device via Appium"""
    
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
    
    def name(self) -> str:
        return "connect_device"
    
    def description(self) -> str:
        return "Connect to Android device/emulator via Appium"
    
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "device_name": {"type": "string"},
                "app_package": {"type": "string"},
                "app_activity": {"type": "string"}
            },
            "required": ["device_name"]
        }
    
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "connected": {"type": "boolean"},
                "device_name": {"type": "string"}
            }
        }
    
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            result = self.driver_manager.connect(
                device_name=arguments['device_name'],
                app_package=arguments.get('app_package'),
                app_activity=arguments.get('app_activity')
            )
            return ToolResult(
                call_id="",
                success=result['success'],
                output=result
            )
        except Exception as e:
            return ToolResult(
                call_id="",
                success=False,
                output=None,
                error=str(e)
            )


class GetScreenStateTool(Tool):
    """Tool to get current screen state (page source + elements)"""
    
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
    
    def name(self) -> str:
        return "get_screen_state"
    
    def description(self) -> str:
        return "Get current screen state including page source and parsed elements"
    
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {}
        }
    
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "page_source": {"type": "string"},
                "elements": {"type": "array"}
            }
        }
    
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            state = self.driver_manager.get_screen_state()
            return ToolResult(
                call_id="",
                success=True,
                output=state
            )
        except Exception as e:
            return ToolResult(
                call_id="",
                success=False,
                output=None,
                error=str(e)
            )


class TapElementTool(Tool):
    """Tool to tap an element"""
    
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
    
    def name(self) -> str:
        return "tap_element"
    
    def description(self) -> str:
        return "Tap/click an element by locator"
    
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "locator_type": {"type": "string", "enum": ["id", "xpath", "text"]},
                "locator_value": {"type": "string"}
            },
            "required": ["locator_type", "locator_value"]
        }
    
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tapped": {"type": "boolean"}
            }
        }
    
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            result = self.driver_manager.tap_element(
                locator_type=arguments['locator_type'],
                locator_value=arguments['locator_value']
            )
            return ToolResult(
                call_id="",
                success=True,
                output=result
            )
        except Exception as e:
            return ToolResult(
                call_id="",
                success=False,
                output=None,
                error=str(e)
            )


class InputTextTool(Tool):
    """Tool to input text into an element"""
    
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
    
    def name(self) -> str:
        return "input_text"
    
    def description(self) -> str:
        return "Input text into an element"
    
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "locator_type": {"type": "string"},
                "locator_value": {"type": "string"},
                "text": {"type": "string"}
            },
            "required": ["locator_type", "locator_value", "text"]
        }
    
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input_completed": {"type": "boolean"}
            }
        }
    
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            result = self.driver_manager.input_text(
                locator_type=arguments['locator_type'],
                locator_value=arguments['locator_value'],
                text=arguments['text']
            )
            return ToolResult(
                call_id="",
                success=True,
                output=result
            )
        except Exception as e:
            return ToolResult(
                call_id="",
                success=False,
                output=None,
                error=str(e)
            )


class ScrollTool(Tool):
    """Tool to scroll the screen"""
    
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
    
    def name(self) -> str:
        return "scroll"
    
    def description(self) -> str:
        return "Scroll the screen up or down"
    
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"]}
            },
            "required": ["direction"]
        }
    
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scrolled": {"type": "boolean"}
            }
        }
    
    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        try:
            result = self.driver_manager.scroll(direction=arguments['direction'])
            return ToolResult(
                call_id="",
                success=True,
                output=result
            )
        except Exception as e:
            return ToolResult(
                call_id="",
                success=False,
                output=None,
                error=str(e)
            )
