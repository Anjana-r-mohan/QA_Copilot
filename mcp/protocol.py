"""
MCP Protocol Definition
Standardized request/response format for all agent operations
"""

from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import uuid


@dataclass
class MCPRequest:
    """
    Standard MCP request format
    """
    id: str
    method: str
    params: Dict[str, Any]
    session_id: Optional[str] = None
    
    @classmethod
    def create(cls, method: str, params: Dict[str, Any], session_id: Optional[str] = None):
        return cls(
            id=str(uuid.uuid4()),
            method=method,
            params=params,
            session_id=session_id or str(uuid.uuid4())
        )
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict):
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str):
        return cls.from_dict(json.loads(json_str))


@dataclass
class MCPResponse:
    """
    Standard MCP response format
    """
    id: str  # Matches request ID
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict):
        return cls(**data)
    
    @classmethod
    def success_response(cls, request_id: str, result: Any, metadata: Optional[Dict] = None):
        return cls(
            id=request_id,
            success=True,
            result=result,
            metadata=metadata
        )
    
    @classmethod
    def error_response(cls, request_id: str, error: str, metadata: Optional[Dict] = None):
        return cls(
            id=request_id,
            success=False,
            error=error,
            metadata=metadata
        )


@dataclass
class MCPStreamEvent:
    """
    Streaming event for progress updates
    """
    request_id: str
    event_type: str  # 'progress', 'step', 'success', 'error', 'complete'
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    def to_sse(self) -> str:
        """Convert to Server-Sent Event format"""
        return f"data: {self.to_json()}\n\n"


# Standard MCP Methods
class MCPMethod:
    """Registry of standard MCP methods"""
    
    # Tool execution
    CALL_TOOL = "callTool"
    CALL_TOOL_ASYNC = "callToolAsync"
    GET_TOOL_RESULT = "getToolResult"
    LIST_TOOLS = "listTools"
    
    # Test execution
    EXECUTE_TEST_STEP = "executeTestStep"
    EXECUTE_TEST_PLAN = "executeTestPlan"
    
    # Memory operations
    GET_MEMORY = "getMemory"
    SET_MEMORY = "setMemory"
    SEARCH_MEMORY = "searchMemory"
    CLEAR_MEMORY = "clearMemory"
    
    # Prompt/LLM
    RUN_PROMPT = "runPrompt"
    COMPLETE = "complete"
    
    # Session
    CREATE_SESSION = "createSession"
    GET_SESSION = "getSession"
    END_SESSION = "endSession"
    
    # Code generation
    GENERATE_CODE = "generateCode"
    
    # Device/App control
    CONNECT_DEVICE = "connectDevice"
    DISCONNECT_DEVICE = "disconnectDevice"
    GET_SCREEN_STATE = "getScreenState"


@dataclass
class ToolDefinition:
    """
    Definition of a callable tool
    """
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    async_capable: bool = False
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ToolCall:
    """
    A tool execution request
    """
    tool_name: str
    arguments: Dict[str, Any]
    call_id: Optional[str] = None
    
    def __post_init__(self):
        if self.call_id is None:
            self.call_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ToolResult:
    """
    Result of a tool execution
    """
    call_id: str
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class MemoryItem:
    """
    A single memory entry
    """
    key: str
    value: Any
    session_id: str
    timestamp: str = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SessionContext:
    """
    Session state and context
    """
    session_id: str
    created_at: str
    last_active: str
    memory: Dict[str, Any]
    metadata: Dict[str, Any]
    
    def __post_init__(self):
        if not hasattr(self, 'created_at') or self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if not hasattr(self, 'last_active') or self.last_active is None:
            self.last_active = datetime.now().isoformat()
        if not hasattr(self, 'memory') or self.memory is None:
            self.memory = {}
        if not hasattr(self, 'metadata') or self.metadata is None:
            self.metadata = {}
    
    def update_activity(self):
        self.last_active = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return asdict(self)
