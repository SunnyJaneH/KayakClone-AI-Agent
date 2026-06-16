# interfaces/session_store.py
"""
Session State Management for 'Refine without starting over'
Maintains search context across conversation turns
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from loguru import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class SessionStore:
    """
    Manages session state for multi-turn AI conversations.
    Enables 'Refine without starting over' by preserving context.
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, ttl_hours: int = 24):
        self.ttl_seconds = ttl_hours * 3600
        self.redis_client = None
        self._memory_store: Dict[str, Dict] = {}
        
        # Try to connect to Redis
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info(f"SessionStore connected to Redis at {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"Redis connection failed, using in-memory store: {e}")
                self.redis_client = None
        else:
            logger.warning("Redis not available, using in-memory store")
    
    def _get_key(self, session_id: str) -> str:
        return f"session:{session_id}"
    
    def create_session(self, user_id: str, session_id: Optional[str] = None) -> str:
        """Create a new session"""
        if not session_id:
            session_id = f"sess_{user_id}_{uuid.uuid4().hex[:8]}"
        
        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "origin": None,
            "destination": None,
            "date_from": None,
            "date_to": None,
            "budget": None,
            "travelers": 1,
            "constraints": [],
            "previous_recommendations": [],
            "conversation_turns": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        self._save_session(session_id, session_data)
        logger.info(f"Created new session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        key = self._get_key(session_id)
        
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        
        return self._memory_store.get(session_id)
    
    def _save_session(self, session_id: str, session_data: Dict[str, Any]):
        """Save session to storage"""
        session_data["updated_at"] = datetime.utcnow().isoformat()
        key = self._get_key(session_id)
        
        if self.redis_client:
            try:
                self.redis_client.setex(key, self.ttl_seconds, json.dumps(session_data))
            except Exception as e:
                logger.error(f"Redis save error: {e}")
                self._memory_store[session_id] = session_data
        else:
            self._memory_store[session_id] = session_data
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update session with new data (merge, don't overwrite).
        This enables 'Refine without starting over'.
        """
        session = self.get_session(session_id)
        
        if not session:
            logger.warning(f"Session not found: {session_id}")
            return {}
        
        # Merge updates into existing session
        for key, value in updates.items():
            if value is not None:
                if key == "constraints" and isinstance(value, list):
                    # Append new constraints, don't replace
                    existing = session.get("constraints", [])
                    session["constraints"] = list(set(existing + value))
                else:
                    session[key] = value
        
        session["conversation_turns"] = session.get("conversation_turns", 0) + 1
        
        self._save_session(session_id, session)
        logger.info(f"Updated session {session_id}, turn {session['conversation_turns']}")
        return session
    
    def merge_intent(self, session_id: str, parsed_intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge a parsed intent into the session.
        Only updates fields that are present in the new intent.
        """
        updates = {}
        
        if parsed_intent.get("origin"):
            updates["origin"] = parsed_intent["origin"]
        if parsed_intent.get("destination"):
            updates["destination"] = parsed_intent["destination"]
        if parsed_intent.get("date_from"):
            updates["date_from"] = parsed_intent["date_from"]
        if parsed_intent.get("date_to"):
            updates["date_to"] = parsed_intent["date_to"]
        if parsed_intent.get("budget"):
            updates["budget"] = parsed_intent["budget"]
        if parsed_intent.get("travelers"):
            updates["travelers"] = parsed_intent["travelers"]
        if parsed_intent.get("constraints"):
            updates["constraints"] = parsed_intent["constraints"]
        
        return self.update_session(session_id, updates)
    
    def save_recommendations(self, session_id: str, recommendations: List[Dict[str, Any]]):
        """Save recommendations for later comparison"""
        session = self.get_session(session_id)
        if session:
            session["previous_recommendations"] = recommendations
            self._save_session(session_id, session)
    
    def get_previous_recommendations(self, session_id: str) -> List[Dict[str, Any]]:
        """Get previous recommendations for change comparison"""
        session = self.get_session(session_id)
        if session:
            return session.get("previous_recommendations", [])
        return []
    
    def compare_with_previous(
        self, 
        session_id: str, 
        new_recommendations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Compare new recommendations with previous ones.
        Returns list of changes for 'Refine without starting over'.
        """
        previous = self.get_previous_recommendations(session_id)
        
        if not previous:
            return []
        
        changes = []
        
        # Simple comparison - match by bundle position
        for i, new_rec in enumerate(new_recommendations[:3]):
            if i < len(previous):
                prev_rec = previous[i]
                
                # Compare prices
                prev_price = prev_rec.get("total_price", 0)
                new_price = new_rec.get("total_price", 0)
                if prev_price != new_price:
                    diff = new_price - prev_price
                    changes.append({
                        "field": "price",
                        "previous_value": f"${prev_price:.0f}",
                        "new_value": f"${new_price:.0f}",
                        "change_type": "increase" if diff > 0 else "decrease",
                        "change_amount": f"+${diff:.0f}" if diff > 0 else f"-${abs(diff):.0f}",
                        "is_improvement": diff < 0
                    })
                
                # Compare flight times
                prev_flight = prev_rec.get("flight", {})
                new_flight = new_rec.get("flight", {})
                if prev_flight.get("departure_time") != new_flight.get("departure_time"):
                    changes.append({
                        "field": "flight_time",
                        "previous_value": prev_flight.get("departure_time", "N/A"),
                        "new_value": new_flight.get("departure_time", "N/A"),
                        "change_type": "modified",
                        "change_amount": None,
                        "is_improvement": True  # Assume user requested change is improvement
                    })
                
                # Compare hotels
                prev_hotel = prev_rec.get("hotel", {})
                new_hotel = new_rec.get("hotel", {})
                if prev_hotel.get("name") != new_hotel.get("name"):
                    changes.append({
                        "field": "hotel",
                        "previous_value": prev_hotel.get("name", "N/A"),
                        "new_value": new_hotel.get("name", "N/A"),
                        "change_type": "modified",
                        "change_amount": None,
                        "is_improvement": True
                    })
        
        # Check for new constraints applied
        session = self.get_session(session_id)
        if session:
            constraints = session.get("constraints", [])
            for constraint in constraints:
                changes.append({
                    "field": "constraint",
                    "previous_value": "not applied",
                    "new_value": constraint,
                    "change_type": "added",
                    "change_amount": None,
                    "is_improvement": True
                })
        
        return changes
    
    def get_search_params(self, session_id: str) -> Dict[str, Any]:
        """Get accumulated search parameters from session"""
        session = self.get_session(session_id)
        
        if not session:
            return {}
        
        return {
            "origin": session.get("origin"),
            "destination": session.get("destination"),
            "date_from": session.get("date_from"),
            "date_to": session.get("date_to"),
            "budget": session.get("budget"),
            "travelers": session.get("travelers", 1),
            "constraints": session.get("constraints", [])
        }
    
    def delete_session(self, session_id: str):
        """Delete a session"""
        key = self._get_key(session_id)
        
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
        
        if session_id in self._memory_store:
            del self._memory_store[session_id]
        
        logger.info(f"Deleted session: {session_id}")
    
    def get_or_create_session(self, user_id: str, session_id: Optional[str] = None) -> str:
        """Get existing session or create new one"""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session_id
        
        return self.create_session(user_id, session_id)


# Global instance
from config import settings
session_store = SessionStore(
    redis_host=settings.REDIS_HOST,
    redis_port=settings.REDIS_PORT
)
