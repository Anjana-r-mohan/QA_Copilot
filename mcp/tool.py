"""
Base MCP Tool class
"""

from abc import ABC, abstractmethod


class MCPTool(ABC):
    """
    Base class for all MCP tools
    """
    
    name = "base_tool"
    description = "Base tool"
    
    @abstractmethod
    def execute(self, params: dict) -> dict:
        """
        Execute the tool with given parameters
        Returns dict with results
        """
        pass
