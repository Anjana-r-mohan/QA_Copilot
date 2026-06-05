"""
MCP (Model Context Protocol) Package
"""

from .protocol import (
    MCPRequest,
    MCPResponse,
    MCPStreamEvent,
    MCPMethod,
    ToolDefinition,
    ToolCall,
    ToolResult,
    MemoryItem,
    SessionContext
)

from .tool_registry import (
    Tool,
    ToolRegistry,
    ConnectDeviceTool,
    GetScreenStateTool,
    TapElementTool,
    InputTextTool,
    ScrollTool
)

from .memory import (
    MemoryStore,
    ContextBuilder
)

from .server import MCPServer

# Initialize driver manager
from .driver_manager import AppiumDriverManager

__all__ = [
    # Protocol
    'MCPRequest',
    'MCPResponse',
    'MCPStreamEvent',
    'MCPMethod',
    'ToolDefinition',
    'ToolCall',
    'ToolResult',
    'MemoryItem',
    'SessionContext',
    
    # Tools
    'Tool',
    'ToolRegistry',
    'ConnectDeviceTool',
    'GetScreenStateTool',
    'TapElementTool',
    'InputTextTool',
    'ScrollTool',
    
    # Memory
    'MemoryStore',
    'ContextBuilder',
    
    # Server
    'MCPServer'
]
