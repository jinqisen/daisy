from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import json
import asyncio


class StateType(Enum):
    SESSION = "session"
    USER = "user"
    CONVERSATION = "conversation"
    GLOBAL = "global"


class StateScope(Enum):
    TRANSIENT = "transient"
    PERSISTENT = "persistent"
    EPHEMERAL = "ephemeral"


@dataclass
class StateEntry:
    key: str
    value: Any
    state_type: StateType
    scope: StateScope
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at


@dataclass
class SessionState:
    session_id: str
    user_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_activity(self) -> None:
        self.last_activity = datetime.utcnow()
        self.updated_at = datetime.utcnow()


@dataclass
class UserState:
    user_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update(self) -> None:
        self.updated_at = datetime.utcnow()


@dataclass
class ConversationState:
    conversation_id: str
    session_id: str
    user_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    state: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        })
        self.updated_at = datetime.utcnow()
        
    def get_recent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.messages[-limit:] if limit > 0 else self.messages


class StateManager:
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
        self._users: Dict[str, UserState] = {}
        self._conversations: Dict[str, ConversationState] = {}
        self._global_state: Dict[str, Any] = {}
        self._state_listeners: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()
        
    async def create_session(
        self,
        session_id: str,
        user_id: str,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> SessionState:
        async with self._lock:
            session = SessionState(
                session_id=session_id,
                user_id=user_id,
                state=initial_state or {}
            )
            self._sessions[session_id] = session
            await self._notify_listeners("session_created", session)
            return session
            
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        return self._sessions.get(session_id)
        
    async def update_session(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> Optional[SessionState]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.state.update(updates)
                session.update_activity()
                await self._notify_listeners("session_updated", session)
            return session
            
    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                session = self._sessions.pop(session_id)
                await self._notify_listeners("session_deleted", session)
                return True
            return False
            
    async def create_user(
        self,
        user_id: str,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> UserState:
        async with self._lock:
            user = UserState(
                user_id=user_id,
                state=initial_state or {}
            )
            self._users[user_id] = user
            await self._notify_listeners("user_created", user)
            return user
            
    async def get_user(self, user_id: str) -> Optional[UserState]:
        return self._users.get(user_id)
        
    async def update_user(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ) -> Optional[UserState]:
        async with self._lock:
            user = self._users.get(user_id)
            if user:
                user.state.update(updates)
                user.update()
                await self._notify_listeners("user_updated", user)
            return user
            
    async def create_conversation(
        self,
        conversation_id: str,
        session_id: str,
        user_id: str,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> ConversationState:
        async with self._lock:
            conversation = ConversationState(
                conversation_id=conversation_id,
                session_id=session_id,
                user_id=user_id,
                state=initial_state or {}
            )
            self._conversations[conversation_id] = conversation
            await self._notify_listeners("conversation_created", conversation)
            return conversation
            
    async def get_conversation(self, conversation_id: str) -> Optional[ConversationState]:
        return self._conversations.get(conversation_id)
        
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ConversationState]:
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation:
                conversation.add_message(role, content, metadata)
                await self._notify_listeners("message_added", conversation)
            return conversation
            
    async def update_conversation(
        self,
        conversation_id: str,
        updates: Dict[str, Any]
    ) -> Optional[ConversationState]:
        async with self._lock:
            conversation = self._conversations.get(conversation_id)
            if conversation:
                conversation.state.update(updates)
                conversation.updated_at = datetime.utcnow()
                await self._notify_listeners("conversation_updated", conversation)
            return conversation
            
    async def get_global_state(self, key: str, default: Any = None) -> Any:
        return self._global_state.get(key, default)
        
    async def set_global_state(self, key: str, value: Any) -> None:
        async with self._lock:
            self._global_state[key] = value
            await self._notify_listeners("global_state_updated", {"key": key, "value": value})
            
    async def get_state(
        self,
        state_type: StateType,
        identifier: str,
        key: Optional[str] = None,
        default: Any = None
    ) -> Any:
        if state_type == StateType.SESSION:
            session = await self.get_session(identifier)
            if session:
                return session.state.get(key, default) if key else session.state
        elif state_type == StateType.USER:
            user = await self.get_user(identifier)
            if user:
                return user.state.get(key, default) if key else user.state
        elif state_type == StateType.CONVERSATION:
            conversation = await self.get_conversation(identifier)
            if conversation:
                return conversation.state.get(key, default) if key else conversation.state
        elif state_type == StateType.GLOBAL:
            return await self.get_global_state(key, default) if key else self._global_state
        return default
        
    async def set_state(
        self,
        state_type: StateType,
        identifier: str,
        key: str,
        value: Any
    ) -> bool:
        if state_type == StateType.SESSION:
            session = await self.update_session(identifier, {key: value})
            return session is not None
        elif state_type == StateType.USER:
            user = await self.update_user(identifier, {key: value})
            return user is not None
        elif state_type == StateType.CONVERSATION:
            conversation = await self.update_conversation(identifier, {key: value})
            return conversation is not None
        elif state_type == StateType.GLOBAL:
            await self.set_global_state(key, value)
            return True
        return False
        
    async def cleanup_expired_sessions(self, max_idle_seconds: int = 3600) -> int:
        async with self._lock:
            now = datetime.utcnow()
            expired_sessions = []
            for session_id, session in self._sessions.items():
                idle_time = (now - session.last_activity).total_seconds()
                if idle_time > max_idle_seconds:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                await self.delete_session(session_id)
            
            return len(expired_sessions)
            
    def register_listener(self, event_type: str, callback: Callable) -> None:
        if event_type not in self._state_listeners:
            self._state_listeners[event_type] = []
        self._state_listeners[event_type].append(callback)
        
    async def _notify_listeners(self, event_type: str, data: Any) -> None:
        if event_type in self._state_listeners:
            for callback in self._state_listeners[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception:
                    pass
                    
    async def export_state(self, state_type: StateType, identifier: Optional[str] = None) -> Dict[str, Any]:
        if state_type == StateType.SESSION and identifier:
            session = await self.get_session(identifier)
            return session.__dict__ if session else {}
        elif state_type == StateType.USER and identifier:
            user = await self.get_user(identifier)
            return user.__dict__ if user else {}
        elif state_type == StateType.CONVERSATION and identifier:
            conversation = await self.get_conversation(identifier)
            return conversation.__dict__ if conversation else {}
        elif state_type == StateType.GLOBAL:
            return self._global_state.copy()
        return {}
        
    async def import_state(
        self,
        state_type: StateType,
        identifier: str,
        state_data: Dict[str, Any]
    ) -> bool:
        try:
            if state_type == StateType.SESSION:
                session = SessionState(**state_data)
                self._sessions[identifier] = session
            elif state_type == StateType.USER:
                user = UserState(**state_data)
                self._users[identifier] = user
            elif state_type == StateType.CONVERSATION:
                conversation = ConversationState(**state_data)
                self._conversations[identifier] = conversation
            elif state_type == StateType.GLOBAL:
                self._global_state.update(state_data)
            return True
        except Exception:
            return False


__all__ = [
    "StateType",
    "StateScope",
    "StateEntry",
    "SessionState",
    "UserState",
    "ConversationState",
    "StateManager"
]
