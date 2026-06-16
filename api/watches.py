# api/watches.py
"""
Watches API for 'Keep an eye on it' user journey
Allows users to set price/inventory thresholds and get alerts
"""

import json
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


# ============================================
# Pydantic Models
# ============================================

class WatchCreate(BaseModel):
    """Request to create a watch"""
    user_id: str
    listing_type: str  # "flight", "hotel"
    listing_id: str
    listing_name: str
    watch_type: str  # "price", "inventory"
    threshold: float  # Price threshold or inventory count
    current_value: float


class Watch(BaseModel):
    """Watch record"""
    watch_id: str
    user_id: str
    listing_type: str
    listing_id: str
    listing_name: str
    watch_type: str
    threshold: float
    current_value: float
    created_at: str
    triggered: bool = False
    triggered_at: Optional[str] = None
    trigger_value: Optional[float] = None


class WatchList(BaseModel):
    """User's watches list"""
    watches: List[Watch]
    active_count: int
    triggered_count: int


class WatchTriggerEvent(BaseModel):
    """Event when a watch is triggered"""
    watch_id: str
    user_id: str
    listing_type: str
    listing_id: str
    listing_name: str
    watch_type: str
    threshold: float
    previous_value: float
    new_value: float
    triggered_at: str
    message: str


# ============================================
# Watch Store
# ============================================

class WatchStore:
    """
    Manages price/inventory watches.
    Supports Redis for persistence, falls back to in-memory.
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        self.redis_client = None
        self._memory_store: Dict[str, Dict] = {}
        self._user_index: Dict[str, List[str]] = {}  # user_id -> list of watch_ids
        self._listing_index: Dict[str, List[str]] = {}  # listing_id -> list of watch_ids
        
        # Callback for triggered watches (to push via WebSocket)
        self._trigger_callbacks: List[callable] = []
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info(f"WatchStore connected to Redis at {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"Redis connection failed for WatchStore: {e}")
                self.redis_client = None
    
    def _get_key(self, watch_id: str) -> str:
        return f"watch:{watch_id}"
    
    def _get_user_key(self, user_id: str) -> str:
        return f"user_watches:{user_id}"
    
    def _get_listing_key(self, listing_id: str) -> str:
        return f"listing_watches:{listing_id}"
    
    def register_trigger_callback(self, callback: callable):
        """Register callback to be called when a watch is triggered"""
        self._trigger_callbacks.append(callback)
    
    def create_watch(self, watch_data: WatchCreate) -> Watch:
        """Create a new watch"""
        watch_id = f"watch_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        
        watch = Watch(
            watch_id=watch_id,
            user_id=watch_data.user_id,
            listing_type=watch_data.listing_type,
            listing_id=watch_data.listing_id,
            listing_name=watch_data.listing_name,
            watch_type=watch_data.watch_type,
            threshold=watch_data.threshold,
            current_value=watch_data.current_value,
            created_at=now,
            triggered=False
        )
        
        self._save_watch(watch)
        
        logger.info(f"Created watch {watch_id} for user {watch_data.user_id}: "
                   f"{watch_data.watch_type} on {watch_data.listing_name} "
                   f"threshold={watch_data.threshold}")
        
        return watch
    
    def _save_watch(self, watch: Watch):
        """Save watch to storage"""
        watch_dict = watch.model_dump()
        
        if self.redis_client:
            try:
                # Save watch data
                self.redis_client.set(
                    self._get_key(watch.watch_id),
                    json.dumps(watch_dict)
                )
                # Index by user
                self.redis_client.sadd(self._get_user_key(watch.user_id), watch.watch_id)
                # Index by listing
                self.redis_client.sadd(self._get_listing_key(watch.listing_id), watch.watch_id)
            except Exception as e:
                logger.error(f"Redis save error for watch: {e}")
                self._save_to_memory(watch)
        else:
            self._save_to_memory(watch)
    
    def _save_to_memory(self, watch: Watch):
        """Save to in-memory store"""
        self._memory_store[watch.watch_id] = watch.model_dump()
        
        # Index by user
        if watch.user_id not in self._user_index:
            self._user_index[watch.user_id] = []
        if watch.watch_id not in self._user_index[watch.user_id]:
            self._user_index[watch.user_id].append(watch.watch_id)
        
        # Index by listing
        if watch.listing_id not in self._listing_index:
            self._listing_index[watch.listing_id] = []
        if watch.watch_id not in self._listing_index[watch.listing_id]:
            self._listing_index[watch.listing_id].append(watch.watch_id)
    
    def get_watch(self, watch_id: str) -> Optional[Watch]:
        """Get a watch by ID"""
        if self.redis_client:
            try:
                data = self.redis_client.get(self._get_key(watch_id))
                if data:
                    return Watch(**json.loads(data))
            except Exception as e:
                logger.error(f"Redis get error: {e}")
        
        if watch_id in self._memory_store:
            return Watch(**self._memory_store[watch_id])
        
        return None
    
    def get_user_watches(self, user_id: str) -> WatchList:
        """Get all watches for a user"""
        watches = []
        
        if self.redis_client:
            try:
                watch_ids = self.redis_client.smembers(self._get_user_key(user_id))
                for watch_id in watch_ids:
                    watch = self.get_watch(watch_id)
                    if watch:
                        watches.append(watch)
            except Exception as e:
                logger.error(f"Redis get user watches error: {e}")
        else:
            watch_ids = self._user_index.get(user_id, [])
            for watch_id in watch_ids:
                watch = self.get_watch(watch_id)
                if watch:
                    watches.append(watch)
        
        active_count = sum(1 for w in watches if not w.triggered)
        triggered_count = sum(1 for w in watches if w.triggered)
        
        return WatchList(
            watches=watches,
            active_count=active_count,
            triggered_count=triggered_count
        )
    
    def delete_watch(self, watch_id: str, user_id: str) -> bool:
        """Delete a watch"""
        watch = self.get_watch(watch_id)
        
        if not watch:
            return False
        
        if watch.user_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this watch")
        
        if self.redis_client:
            try:
                self.redis_client.delete(self._get_key(watch_id))
                self.redis_client.srem(self._get_user_key(user_id), watch_id)
                self.redis_client.srem(self._get_listing_key(watch.listing_id), watch_id)
            except Exception as e:
                logger.error(f"Redis delete error: {e}")
        
        if watch_id in self._memory_store:
            del self._memory_store[watch_id]
        if user_id in self._user_index and watch_id in self._user_index[user_id]:
            self._user_index[user_id].remove(watch_id)
        if watch.listing_id in self._listing_index and watch_id in self._listing_index[watch.listing_id]:
            self._listing_index[watch.listing_id].remove(watch_id)
        
        logger.info(f"Deleted watch {watch_id}")
        return True
    
    def check_and_trigger(self, listing_id: str, new_price: Optional[float] = None, 
                          new_inventory: Optional[int] = None) -> List[WatchTriggerEvent]:
        """
        Check if any watches should be triggered for a listing.
        Called when prices/inventory change.
        Returns list of triggered events.
        """
        triggered_events = []
        
        # Get watches for this listing
        watch_ids = []
        if self.redis_client:
            try:
                watch_ids = list(self.redis_client.smembers(self._get_listing_key(listing_id)))
            except Exception as e:
                logger.error(f"Redis get listing watches error: {e}")
        else:
            watch_ids = self._listing_index.get(listing_id, [])
        
        for watch_id in watch_ids:
            watch = self.get_watch(watch_id)
            if not watch or watch.triggered:
                continue
            
            should_trigger = False
            new_value = None
            
            # Check price threshold
            if watch.watch_type == "price" and new_price is not None:
                if new_price <= watch.threshold:
                    should_trigger = True
                    new_value = new_price
            
            # Check inventory threshold
            elif watch.watch_type == "inventory" and new_inventory is not None:
                if new_inventory <= watch.threshold:
                    should_trigger = True
                    new_value = new_inventory
            
            if should_trigger and new_value is not None:
                event = self._trigger_watch(watch, new_value)
                triggered_events.append(event)
        
        return triggered_events
    
    def _trigger_watch(self, watch: Watch, new_value: float) -> WatchTriggerEvent:
        """Trigger a watch and create event"""
        now = datetime.utcnow().isoformat()
        
        # Update watch as triggered
        watch.triggered = True
        watch.triggered_at = now
        watch.trigger_value = new_value
        self._save_watch(watch)
        
        # Create message
        if watch.watch_type == "price":
            message = f"Price dropped to ${new_value:.0f}! (Your alert: ${watch.threshold:.0f})"
        else:
            message = f"Only {int(new_value)} left! (Your alert: {int(watch.threshold)})"
        
        event = WatchTriggerEvent(
            watch_id=watch.watch_id,
            user_id=watch.user_id,
            listing_type=watch.listing_type,
            listing_id=watch.listing_id,
            listing_name=watch.listing_name,
            watch_type=watch.watch_type,
            threshold=watch.threshold,
            previous_value=watch.current_value,
            new_value=new_value,
            triggered_at=now,
            message=message
        )
        
        logger.info(f"Watch triggered: {watch.watch_id} - {message}")
        
        # Call registered callbacks (for WebSocket push)
        for callback in self._trigger_callbacks:
            try:
                # Handle both sync and async callbacks
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event))
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in trigger callback: {e}")
        
        return event
    
    def get_watches_for_listing(self, listing_id: str) -> List[Watch]:
        """Get all watches for a listing"""
        watches = []
        
        watch_ids = []
        if self.redis_client:
            try:
                watch_ids = list(self.redis_client.smembers(self._get_listing_key(listing_id)))
            except Exception as e:
                logger.error(f"Redis error: {e}")
        else:
            watch_ids = self._listing_index.get(listing_id, [])
        
        for watch_id in watch_ids:
            watch = self.get_watch(watch_id)
            if watch:
                watches.append(watch)
        
        return watches


# ============================================
# Global Instance
# ============================================

from config import settings
watch_store = WatchStore(
    redis_host=settings.REDIS_HOST,
    redis_port=settings.REDIS_PORT
)


# ============================================
# FastAPI Router
# ============================================

router = APIRouter(prefix="/api/ai/watches", tags=["AI Watches"])


@router.post("", response_model=Watch)
async def create_watch(watch_data: WatchCreate):
    """
    Create a price or inventory watch.
    User will be notified when threshold is met.
    
    Example: Watch Miami package, alert if price drops below $850
    """
    return watch_store.create_watch(watch_data)


@router.get("/{user_id}", response_model=WatchList)
async def get_user_watches(user_id: str):
    """Get all watches for a user"""
    return watch_store.get_user_watches(user_id)


@router.delete("/{watch_id}")
async def delete_watch(watch_id: str, user_id: str):
    """Delete a watch"""
    success = watch_store.delete_watch(watch_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Watch not found")
    return {"status": "deleted", "watch_id": watch_id}


@router.get("/{user_id}/active", response_model=List[Watch])
async def get_active_watches(user_id: str):
    """Get only active (non-triggered) watches for a user"""
    watch_list = watch_store.get_user_watches(user_id)
    return [w for w in watch_list.watches if not w.triggered]


@router.get("/{user_id}/triggered", response_model=List[Watch])
async def get_triggered_watches(user_id: str):
    """Get only triggered watches for a user"""
    watch_list = watch_store.get_user_watches(user_id)
    return [w for w in watch_list.watches if w.triggered]

# ============================================
# Test/Simulate Endpoints
# ============================================

class PriceChangeSimulation(BaseModel):
    """Simulate a price change to trigger watches"""
    listing_id: str
    new_price: Optional[float] = None
    new_inventory: Optional[int] = None


@router.post("/simulate/price-change", response_model=List[WatchTriggerEvent])
async def simulate_price_change(data: PriceChangeSimulation):
    """
    Simulate a price or inventory change to test watch triggers.
    
    This endpoint is for testing the 'Keep an eye on it' user journey.
    In production, this would be called by a price monitoring service.
    
    Example: Simulate Miami package price dropping to $800
    """
    if data.new_price is None and data.new_inventory is None:
        raise HTTPException(
            status_code=400, 
            detail="Must provide either new_price or new_inventory"
        )
    
    triggered_events = watch_store.check_and_trigger(
        listing_id=data.listing_id,
        new_price=data.new_price,
        new_inventory=data.new_inventory
    )
    
    # Directly push to WebSocket for each triggered event
    try:
        from api.events_websocket import events_manager
        for event in triggered_events:
            await events_manager.send_watch_triggered(event.user_id, event.model_dump())
            logger.info(f"WebSocket push sent for user {event.user_id}")
    except Exception as e:
        logger.error(f"WebSocket push error: {e}")
    
    logger.info(f"Price change simulation: listing={data.listing_id}, "
                f"new_price={data.new_price}, new_inventory={data.new_inventory}, "
                f"triggered={len(triggered_events)} watches")
    
    return triggered_events


@router.get("/listing/{listing_id}", response_model=List[Watch])
async def get_watches_for_listing(listing_id: str):
    """Get all watches monitoring a specific listing"""
    return watch_store.get_watches_for_listing(listing_id)