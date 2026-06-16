"""
WebSocket API for real-time chat with Concierge Agent
"""

import json
import logging
from typing import Dict, Set
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.websockets import WebSocketState

from ..agents.concierge_agent import get_concierge_agent, ConciergeAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["WebSocket"])


class ConnectionManager:
    """
    Manages WebSocket connections for real-time chat
    """
    
    def __init__(self):
        # Active connections: {session_id: WebSocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # User sessions: {user_id: set of session_ids}
        self.user_sessions: Dict[int, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, session_id: str, user_id: int):
        """
        Accept and register a new WebSocket connection
        
        Args:
            websocket: WebSocket instance
            session_id: Unique session identifier
            user_id: User identifier
        """
        await websocket.accept()
        
        self.active_connections[session_id] = websocket
        
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = set()
        self.user_sessions[user_id].add(session_id)
        
        logger.info(f"WebSocket connected: session={session_id}, user={user_id}")
    
    def disconnect(self, session_id: str, user_id: int):
        """
        Remove a WebSocket connection
        
        Args:
            session_id: Session to disconnect
            user_id: User identifier
        """
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        
        if user_id in self.user_sessions:
            self.user_sessions[user_id].discard(session_id)
            if not self.user_sessions[user_id]:
                del self.user_sessions[user_id]
        
        logger.info(f"WebSocket disconnected: session={session_id}, user={user_id}")
    
    async def send_message(self, session_id: str, message: dict):
        """
        Send a message to a specific session
        
        Args:
            session_id: Target session
            message: Message dict to send
        """
        websocket = self.active_connections.get(session_id)
        if websocket and websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_json(message)
    
    async def send_to_user(self, user_id: int, message: dict):
        """
        Send a message to all sessions of a user
        
        Args:
            user_id: Target user
            message: Message dict to send
        """
        sessions = self.user_sessions.get(user_id, set())
        for session_id in sessions:
            await self.send_message(session_id, message)
    
    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected clients
        
        Args:
            message: Message to broadcast
        """
        for session_id in self.active_connections:
            await self.send_message(session_id, message)
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)
    
    def is_connected(self, session_id: str) -> bool:
        """Check if a session is connected"""
        return session_id in self.active_connections


# Global connection manager
manager = ConnectionManager()


@router.websocket("/chat/ws")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token"),
    user_id: int = Query(..., description="User ID"),
    session_id: str = Query(None, description="Optional session ID")
):
    """
    WebSocket endpoint for real-time chat with AI concierge
    
    Connect: ws://localhost:8000/api/ai/chat/ws?token=xxx&user_id=123&session_id=optional
    
    Send message format:
    {
        "type": "message",
        "content": "Your message here",
        "preferences": {...}  // Optional
    }
    
    Receive message format:
    {
        "type": "response" | "typing" | "error" | "recommendations",
        "content": "...",
        "timestamp": "...",
        "session_id": "..."
    }
    """
    # TODO: Validate JWT token here
    # For now, we accept the connection
    
    # Generate session ID if not provided
    if not session_id:
        session_id = f"ws_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Get concierge agent
    concierge = get_concierge_agent()
    
    # Connect
    await manager.connect(websocket, session_id, user_id)
    
    # Send welcome message
    await manager.send_message(session_id, {
        "type": "connected",
        "content": "Connected to AI Concierge. How can I help you today?",
        "session_id": session_id,
        "timestamp": datetime.now().isoformat()
    })
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            message_type = data.get("type", "message")
            content = data.get("content", "")
            preferences = data.get("preferences")
            
            if message_type == "message" and content:
                # Send typing indicator
                await manager.send_message(session_id, {
                    "type": "typing",
                    "content": "AI is thinking...",
                    "timestamp": datetime.now().isoformat()
                })
                
                try:
                    # Process message with concierge agent
                    response = await concierge.chat(
                        user_id=user_id,
                        message=content,
                        session_id=session_id,
                        preferences=preferences
                    )
                    
                    # Send response
                    await manager.send_message(session_id, {
                        "type": "response",
                        "content": response.get("response", ""),
                        "session_id": session_id,
                        "timestamp": response.get("timestamp", datetime.now().isoformat())
                    })
                    
                    # Send recommendations if any
                    recommendations = response.get("recommendations", [])
                    if recommendations:
                        await manager.send_message(session_id, {
                            "type": "recommendations",
                            "content": recommendations,
                            "session_id": session_id,
                            "timestamp": datetime.now().isoformat()
                        })
                
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await manager.send_message(session_id, {
                        "type": "error",
                        "content": "Sorry, I encountered an error. Please try again.",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat()
                    })
            
            elif message_type == "ping":
                # Respond to ping for connection keepalive
                await manager.send_message(session_id, {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
            
            elif message_type == "history":
                # Get conversation history
                history = await concierge.get_conversation_history(session_id)
                await manager.send_message(session_id, {
                    "type": "history",
                    "content": history,
                    "timestamp": datetime.now().isoformat()
                })
            
            elif message_type == "clear":
                # Clear conversation
                await concierge.clear_session(session_id)
                await manager.send_message(session_id, {
                    "type": "cleared",
                    "content": "Conversation cleared. How can I help you?",
                    "timestamp": datetime.now().isoformat()
                })
    
    except WebSocketDisconnect:
        manager.disconnect(session_id, user_id)
        logger.info(f"WebSocket disconnected: session={session_id}")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(session_id, user_id)


@router.get("/chat/ws/status")
async def websocket_status():
    """
    Get WebSocket connection status
    
    Returns:
        Connection statistics
    """
    return {
        "active_connections": manager.get_connection_count(),
        "timestamp": datetime.now().isoformat()
    }
