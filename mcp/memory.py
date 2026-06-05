"""
MCP Memory Layer
Context persistence and retrieval
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from .protocol import MemoryItem, SessionContext
import json


class MemoryStore:
    """
    In-memory storage for session context and history
    In production, this would be backed by Redis/PostgreSQL
    """
    
    def __init__(self):
        self.sessions: Dict[str, SessionContext] = {}
        self.memory_items: Dict[str, List[MemoryItem]] = {}  # session_id -> items
    
    def create_session(self, session_id: Optional[str] = None, metadata: Optional[Dict] = None) -> SessionContext:
        """Create a new session"""
        import uuid
        if not session_id:
            session_id = str(uuid.uuid4())
        
        session = SessionContext(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            last_active=datetime.now().isoformat(),
            memory={},
            metadata=metadata or {}
        )
        
        self.sessions[session_id] = session
        self.memory_items[session_id] = []
        
        return session
    
    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get session by ID"""
        session = self.sessions.get(session_id)
        if session:
            session.update_activity()
        return session
    
    def end_session(self, session_id: str):
        """End a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
        if session_id in self.memory_items:
            del self.memory_items[session_id]
    
    def set_memory(self, session_id: str, key: str, value: Any, tags: Optional[List[str]] = None):
        """Set a memory item in session"""
        session = self.get_session(session_id)
        if not session:
            session = self.create_session(session_id)
        
        # Update session memory dict
        session.memory[key] = value
        
        # Add to memory items list
        memory_item = MemoryItem(
            key=key,
            value=value,
            session_id=session_id,
            tags=tags or [],
            timestamp=datetime.now().isoformat()
        )
        
        if session_id not in self.memory_items:
            self.memory_items[session_id] = []
        
        self.memory_items[session_id].append(memory_item)
    
    def get_memory(self, session_id: str, key: str) -> Optional[Any]:
        """Get a memory value from session"""
        session = self.get_session(session_id)
        if not session:
            return None
        return session.memory.get(key)
    
    def get_all_memory(self, session_id: str) -> Dict[str, Any]:
        """Get all memory for a session"""
        session = self.get_session(session_id)
        if not session:
            return {}
        return session.memory
    
    def search_memory(self, session_id: str, query: Optional[str] = None, 
                     tags: Optional[List[str]] = None, limit: int = 10) -> List[MemoryItem]:
        """
        Search memory items
        In production, this would use vector search or full-text search
        """
        if session_id not in self.memory_items:
            return []
        
        items = self.memory_items[session_id]
        
        # Filter by tags
        if tags:
            items = [item for item in items if any(tag in (item.tags or []) for tag in tags)]
        
        # Simple text search if query provided
        if query:
            query_lower = query.lower()
            items = [
                item for item in items
                if query_lower in str(item.key).lower() or query_lower in str(item.value).lower()
            ]
        
        # Return most recent first
        items = sorted(items, key=lambda x: x.timestamp, reverse=True)
        
        return items[:limit]
    
    def clear_memory(self, session_id: str):
        """Clear all memory for a session"""
        session = self.get_session(session_id)
        if session:
            session.memory = {}
        if session_id in self.memory_items:
            self.memory_items[session_id] = []
    
    def get_history(self, session_id: str, limit: int = 10) -> List[MemoryItem]:
        """Get recent memory history"""
        if session_id not in self.memory_items:
            return []
        
        items = self.memory_items[session_id]
        return sorted(items, key=lambda x: x.timestamp, reverse=True)[:limit]


class ContextBuilder:
    """
    Builds context for LLM prompts from memory
    """
    
    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store
    
    def build_context(self, session_id: str, include_history: bool = True,
                     tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Build context dict for prompt template
        """
        context = {}
        
        # Get current session memory
        session_memory = self.memory_store.get_all_memory(session_id)
        context.update(session_memory)
        
        # Add history if requested
        if include_history:
            history = self.memory_store.get_history(session_id, limit=5)
            context['_history'] = [
                {
                    'key': item.key,
                    'value': item.value,
                    'timestamp': item.timestamp
                }
                for item in history
            ]
        
        # Add tagged memories
        if tags:
            tagged_items = self.memory_store.search_memory(session_id, tags=tags, limit=10)
            context['_tagged'] = [
                {
                    'key': item.key,
                    'value': item.value,
                    'tags': item.tags
                }
                for item in tagged_items
            ]
        
        return context
    
    def format_context_for_prompt(self, context: Dict[str, Any]) -> str:
        """
        Format context as text for prompt injection
        """
        lines = []
        
        # Current values
        if context:
            lines.append("CURRENT CONTEXT:")
            for key, value in context.items():
                if not key.startswith('_'):
                    lines.append(f"  {key}: {value}")
        
        # History
        if '_history' in context and context['_history']:
            lines.append("\nRECENT HISTORY:")
            for item in context['_history']:
                lines.append(f"  [{item['timestamp']}] {item['key']}: {item['value']}")
        
        return "\n".join(lines)
