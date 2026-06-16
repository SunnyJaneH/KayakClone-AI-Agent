"""
Conversation Store - Persists chat history for sessions
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

import redis.asyncio as redis

from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a conversation message"""
    session_id: str
    user_id: int
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    metadata: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Message":
        return cls(**data)


class ConversationStore:
    """
    Stores and retrieves conversation history
    
    Uses Redis for fast access and automatic expiration
    Falls back to in-memory storage if Redis unavailable
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl_hours: int = 24
    ):
        """
        Initialize conversation store
        
        Args:
            redis_url: Redis connection URL
            ttl_hours: Hours to keep conversation history
        """
        self.redis_url = redis_url or f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        self.ttl = timedelta(hours=ttl_hours)
        self.redis_client: Optional[redis.Redis] = None
        
        # Fallback in-memory storage
        self.memory_store: Dict[str, List[Message]] = {}
        
        self._initialized = False
    
    async def _ensure_connected(self):
        """Ensure Redis connection is established"""
        if self._initialized:
            return
        
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self.redis_client.ping()
            self._initialized = True
            logger.info("ConversationStore connected to Redis")
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory storage: {e}")
            self.redis_client = None
            self._initialized = True
    
    def _get_key(self, session_id: str) -> str:
        """Generate Redis key for a session"""
        return f"conversation:{session_id}"
    
    async def save_message(
        self,
        session_id: str,
        user_id: int,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> Message:
        """
        Save a message to conversation history
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata
            
        Returns:
            Saved Message object
        """
        await self._ensure_connected()
        
        message = Message(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            metadata=metadata
        )
        
        try:
            if self.redis_client:
                key = self._get_key(session_id)
                
                # Append message to list
                await self.redis_client.rpush(key, json.dumps(message.to_dict()))
                
                # Set expiration
                await self.redis_client.expire(key, int(self.ttl.total_seconds()))
                
                logger.debug(f"Saved message to Redis: session={session_id}")
            else:
                # Fallback to in-memory
                if session_id not in self.memory_store:
                    self.memory_store[session_id] = []
                self.memory_store[session_id].append(message)
                
                logger.debug(f"Saved message to memory: session={session_id}")
            
            return message
            
        except Exception as e:
            logger.error(f"Error saving message: {e}")
            # Fallback to memory on error
            if session_id not in self.memory_store:
                self.memory_store[session_id] = []
            self.memory_store[session_id].append(message)
            return message
    
    async def get_history(
        self,
        session_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get conversation history for a session
        
        Args:
            session_id: Session identifier
            limit: Maximum messages to retrieve
            
        Returns:
            List of message dicts (oldest first)
        """
        await self._ensure_connected()
        
        try:
            if self.redis_client:
                key = self._get_key(session_id)
                
                # Get last N messages
                messages = await self.redis_client.lrange(key, -limit, -1)
                
                return [json.loads(m) for m in messages]
            else:
                # From memory
                messages = self.memory_store.get(session_id, [])
                return [m.to_dict() for m in messages[-limit:]]
            
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            messages = self.memory_store.get(session_id, [])
            return [m.to_dict() for m in messages[-limit:]]
    
    async def get_recent_messages(
        self,
        session_id: str,
        count: int = 10
    ) -> List[Dict]:
        """
        Get most recent messages for a session
        
        Args:
            session_id: Session identifier
            count: Number of recent messages
            
        Returns:
            List of recent message dicts
        """
        history = await self.get_history(session_id, limit=count)
        return history
    
    async def clear_session(self, session_id: str):
        """
        Clear all messages for a session
        
        Args:
            session_id: Session to clear
        """
        await self._ensure_connected()
        
        try:
            if self.redis_client:
                key = self._get_key(session_id)
                await self.redis_client.delete(key)
            
            # Also clear from memory
            if session_id in self.memory_store:
                del self.memory_store[session_id]
            
            logger.info(f"Cleared session: {session_id}")
            
        except Exception as e:
            logger.error(f"Error clearing session: {e}")
            if session_id in self.memory_store:
                del self.memory_store[session_id]
    
    async def get_session_metadata(self, session_id: str) -> Dict:
        """
        Get metadata about a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Dict with session metadata
        """
        history = await self.get_history(session_id)
        
        if not history:
            return {
                "session_id": session_id,
                "message_count": 0,
                "exists": False
            }
        
        first_message = history[0]
        last_message = history[-1]
        
        return {
            "session_id": session_id,
            "message_count": len(history),
            "user_id": first_message.get("user_id"),
            "started_at": first_message.get("timestamp"),
            "last_activity": last_message.get("timestamp"),
            "exists": True
        }
    
    async def get_user_sessions(self, user_id: int) -> List[str]:
        """
        Get all session IDs for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            List of session IDs
        """
        await self._ensure_connected()
        
        sessions = []
        
        try:
            if self.redis_client:
                # Scan for user's sessions
                cursor = 0
                pattern = "conversation:*"
                
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor=cursor,
                        match=pattern,
                        count=100
                    )
                    
                    for key in keys:
                        # Check if session belongs to user
                        messages = await self.redis_client.lrange(key, 0, 0)
                        if messages:
                            first_msg = json.loads(messages[0])
                            if first_msg.get("user_id") == user_id:
                                session_id = key.replace("conversation:", "")
                                sessions.append(session_id)
                    
                    if cursor == 0:
                        break
            else:
                # From memory
                for session_id, messages in self.memory_store.items():
                    if messages and messages[0].user_id == user_id:
                        sessions.append(session_id)
            
            return sessions
            
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []
    
    async def search_conversations(
        self,
        user_id: int,
        query: str,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search user's conversations for a query
        
        Args:
            user_id: User identifier
            query: Search query
            limit: Max results
            
        Returns:
            List of matching messages with session info
        """
        sessions = await self.get_user_sessions(user_id)
        results = []
        
        query_lower = query.lower()
        
        for session_id in sessions:
            history = await self.get_history(session_id)
            
            for msg in history:
                if query_lower in msg.get("content", "").lower():
                    results.append({
                        "session_id": session_id,
                        "message": msg,
                        "timestamp": msg.get("timestamp")
                    })
                    
                    if len(results) >= limit:
                        return results
        
        return results
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            logger.info("ConversationStore connection closed")


# Singleton instance
_store_instance: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    """Get singleton instance of ConversationStore"""
    global _store_instance
    if _store_instance is None:
        _store_instance = ConversationStore()
    return _store_instance
