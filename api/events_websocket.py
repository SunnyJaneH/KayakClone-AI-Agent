# api/events_websocket.py
"""
/events WebSocket endpoint for real-time push notifications
Handles: price alerts, inventory alerts, deal notifications
"""

import json
import asyncio
from datetime import datetime
from typing import Dict, Set, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
from pydantic import BaseModel


# ============================================
# Event Models
# ============================================

class EventMessage(BaseModel):
    """WebSocket event message"""
    event_type: str  # "price_alert", "inventory_alert", "deal_found", "watch_triggered"
    title: str
    message: str
    payload: Dict[str, Any]
    timestamp: str
    read: bool = False


class ConnectionInfo(BaseModel):
    """Information about a WebSocket connection"""
    user_id: str
    session_id: str
    connected_at: str
    last_ping: str


# ============================================
# Events Connection Manager
# ============================================

class EventsConnectionManager:
    """
    Manages WebSocket connections for /events endpoint.
    Supports:
    - Per-user connections
    - Broadcasting to all users
    - Targeted push to specific users
    - Unread message counting
    """
    
    def __init__(self):
        # user_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        
        # user_id -> list of pending events (for offline users)
        self.pending_events: Dict[str, list] = {}
        
        # user_id -> unread count
        self.unread_counts: Dict[str, int] = {}
        
        # user_id -> connection info
        self.connection_info: Dict[str, ConnectionInfo] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        
        self.active_connections[user_id] = websocket
        self.connection_info[user_id] = ConnectionInfo(
            user_id=user_id,
            session_id=f"events_{user_id}",
            connected_at=datetime.utcnow().isoformat(),
            last_ping=datetime.utcnow().isoformat()
        )
        
        logger.info(f"Events WebSocket connected: user={user_id}")
        
        # Send welcome message
        await self.send_to_user(user_id, EventMessage(
            event_type="connected",
            title="Connected",
            message="You are now connected to real-time updates",
            payload={"user_id": user_id},
            timestamp=datetime.utcnow().isoformat()
        ))
        
        # Send any pending events
        await self._send_pending_events(user_id)
    
    def disconnect(self, user_id: str):
        """Handle WebSocket disconnection"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.connection_info:
            del self.connection_info[user_id]
        
        logger.info(f"Events WebSocket disconnected: user={user_id}")
    
    async def send_to_user(self, user_id: str, event: EventMessage):
        """Send event to a specific user"""
        if user_id in self.active_connections:
            try:
                websocket = self.active_connections[user_id]
                await websocket.send_json(event.model_dump())
                logger.debug(f"Sent event to user {user_id}: {event.event_type}")
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                self.disconnect(user_id)
                # Queue for later delivery
                self._queue_pending_event(user_id, event)
        else:
            # User not connected, queue event
            self._queue_pending_event(user_id, event)
            self._increment_unread(user_id)
    
    def _queue_pending_event(self, user_id: str, event: EventMessage):
        """Queue event for offline user"""
        if user_id not in self.pending_events:
            self.pending_events[user_id] = []
        
        # Keep max 50 pending events per user
        if len(self.pending_events[user_id]) < 50:
            self.pending_events[user_id].append(event.model_dump())
            logger.debug(f"Queued event for offline user {user_id}")
    
    async def _send_pending_events(self, user_id: str):
        """Send all pending events when user reconnects"""
        if user_id in self.pending_events and self.pending_events[user_id]:
            events = self.pending_events[user_id]
            logger.info(f"Sending {len(events)} pending events to user {user_id}")
            
            for event_dict in events:
                if user_id in self.active_connections:
                    try:
                        await self.active_connections[user_id].send_json(event_dict)
                    except Exception as e:
                        logger.error(f"Error sending pending event: {e}")
                        break
            
            # Clear pending events
            self.pending_events[user_id] = []
            self.unread_counts[user_id] = 0
    
    def _increment_unread(self, user_id: str):
        """Increment unread count for user"""
        if user_id not in self.unread_counts:
            self.unread_counts[user_id] = 0
        self.unread_counts[user_id] += 1
    
    def get_unread_count(self, user_id: str) -> int:
        """Get unread count for user"""
        return self.unread_counts.get(user_id, 0)
    
    def clear_unread(self, user_id: str):
        """Clear unread count for user"""
        self.unread_counts[user_id] = 0
    
    async def broadcast(self, event: EventMessage, exclude_user: Optional[str] = None):
        """Broadcast event to all connected users"""
        for user_id, websocket in self.active_connections.items():
            if user_id != exclude_user:
                await self.send_to_user(user_id, event)
    
    async def broadcast_deal(self, deal_info: Dict[str, Any]):
        """Broadcast a new deal to all users"""
        event = EventMessage(
            event_type="deal_found",
            title="New Deal Found!",
            message=f"{deal_info.get('name', 'Great deal')} - {deal_info.get('discount', '15%')} off!",
            payload=deal_info,
            timestamp=datetime.utcnow().isoformat()
        )
        await self.broadcast(event)
    
    async def send_price_alert(self, user_id: str, listing_name: str, 
                                old_price: float, new_price: float,
                                listing_id: str, listing_type: str):
        """Send price drop alert to user"""
        savings = old_price - new_price
        savings_percent = (savings / old_price) * 100
        
        event = EventMessage(
            event_type="price_alert",
            title="Price Drop!",
            message=f"{listing_name} dropped to ${new_price:.0f} (save ${savings:.0f}, {savings_percent:.0f}% off)",
            payload={
                "listing_id": listing_id,
                "listing_type": listing_type,
                "listing_name": listing_name,
                "old_price": old_price,
                "new_price": new_price,
                "savings": savings,
                "savings_percent": savings_percent
            },
            timestamp=datetime.utcnow().isoformat()
        )
        await self.send_to_user(user_id, event)
    
    async def send_inventory_alert(self, user_id: str, listing_name: str,
                                    inventory: int, listing_id: str, listing_type: str):
        """Send low inventory alert to user"""
        event = EventMessage(
            event_type="inventory_alert",
            title="Low Availability!",
            message=f"Only {inventory} left for {listing_name}!",
            payload={
                "listing_id": listing_id,
                "listing_type": listing_type,
                "listing_name": listing_name,
                "inventory": inventory
            },
            timestamp=datetime.utcnow().isoformat()
        )
        await self.send_to_user(user_id, event)
    
    async def send_watch_triggered(self, user_id: str, watch_event: Dict[str, Any]):
        """Send watch triggered notification"""
        event = EventMessage(
            event_type="watch_triggered",
            title="Watch Alert!",
            message=watch_event.get("message", "Your price watch was triggered"),
            payload=watch_event,
            timestamp=datetime.utcnow().isoformat()
        )
        await self.send_to_user(user_id, event)
    
    def is_connected(self, user_id: str) -> bool:
        """Check if user is connected"""
        return user_id in self.active_connections
    
    def get_connected_users(self) -> list:
        """Get list of connected user IDs"""
        return list(self.active_connections.keys())
    
    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return len(self.active_connections)


# ============================================
# Global Instance
# ============================================

events_manager = EventsConnectionManager()


# ============================================
# Helper function to register with watch_store
# ============================================

def register_watch_callback():
    """Register callback with watch_store to push events"""
    try:
        from api.watches import watch_store
        
        async def on_watch_triggered(watch_event):
            """Called when a watch is triggered"""
            user_id = watch_event.user_id
            await events_manager.send_watch_triggered(user_id, watch_event.model_dump())
        
        def sync_callback(watch_event):
            """Sync wrapper for async callback"""
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(on_watch_triggered(watch_event))
                else:
                    loop.run_until_complete(on_watch_triggered(watch_event))
            except Exception as e:
                logger.error(f"Error in watch callback: {e}")
        
        watch_store.register_trigger_callback(sync_callback)
        logger.info("Registered watch trigger callback with events manager")
    except ImportError:
        logger.warning("Could not import watch_store for callback registration")


# ============================================
# FastAPI Router
# ============================================

router = APIRouter(tags=["AI Events"])


@router.websocket("/api/ai/events")
async def events_websocket(websocket: WebSocket, user_id: str = Query(...)):
    """
    WebSocket endpoint for real-time event notifications.
    
    Connect: ws://localhost:8000/api/ai/events?user_id=xxx
    
    Events pushed:
    - price_alert: Price dropped below threshold
    - inventory_alert: Inventory dropped below threshold
    - deal_found: New deal discovered
    - watch_triggered: User's watch was triggered
    """
    await events_manager.connect(websocket, user_id)
    
    try:
        while True:
            # Wait for client messages (ping/pong, etc.)
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")
                
                if msg_type == "ping":
                    # Respond to ping
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                elif msg_type == "clear_unread":
                    # Clear unread count
                    events_manager.clear_unread(user_id)
                    await websocket.send_json({
                        "type": "unread_cleared",
                        "count": 0
                    })
                
                elif msg_type == "get_unread":
                    # Get unread count
                    count = events_manager.get_unread_count(user_id)
                    await websocket.send_json({
                        "type": "unread_count",
                        "count": count
                    })
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from user {user_id}: {data}")
    
    except WebSocketDisconnect:
        events_manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"Events WebSocket error for user {user_id}: {e}")
        events_manager.disconnect(user_id)


@router.get("/api/ai/events/status")
async def get_events_status():
    """Get events connection status"""
    return {
        "connected_users": events_manager.get_connected_users(),
        "connection_count": events_manager.get_connection_count()
    }


@router.get("/api/ai/events/unread/{user_id}")
async def get_unread_count(user_id: str):
    """Get unread event count for a user"""
    return {
        "user_id": user_id,
        "unread_count": events_manager.get_unread_count(user_id)
    }


@router.post("/api/ai/events/test/{user_id}")
async def send_test_event(user_id: str, event_type: str = "deal_found"):
    """Send a test event to a user (for debugging)"""
    event = EventMessage(
        event_type=event_type,
        title="Test Event",
        message="This is a test notification",
        payload={"test": True},
        timestamp=datetime.utcnow().isoformat()
    )
    await events_manager.send_to_user(user_id, event)
    return {"status": "sent", "user_id": user_id, "event_type": event_type}


# Alias for main.py import
websocket_endpoint = events_websocket


# ============================================
# Aliases and Additional Methods for main.py
# ============================================

# Alias for main.py import
websocket_endpoint = events_websocket

# Add shutdown method to EventsConnectionManager
async def _shutdown(self):
    """Close all connections on shutdown"""
    for user_id in list(self.active_connections.keys()):
        try:
            await self.active_connections[user_id].close()
        except:
            pass
        self.disconnect(user_id)
    logger.info("All WebSocket connections closed")

EventsConnectionManager.shutdown = _shutdown

# Add handle_watch_triggered for callback registration
async def _handle_watch_triggered(self, watch_event):
    """Handle watch triggered callback from watch_store"""
    user_id = watch_event.get("user_id") if isinstance(watch_event, dict) else watch_event.user_id
    event_data = watch_event if isinstance(watch_event, dict) else watch_event.model_dump()
    await self.send_watch_triggered(user_id, event_data)

EventsConnectionManager.handle_watch_triggered = _handle_watch_triggered
