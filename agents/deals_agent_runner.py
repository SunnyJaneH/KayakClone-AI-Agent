# agents/deals_agent_runner.py
"""
Deals Agent Background Runner
Runs the Kafka pipeline for deal processing:
1. Consume from raw_supplier_feeds
2. Normalize data
3. Score deals
4. Tag deals
5. Emit events

This implements the Deals Agent (backend worker) requirements.
"""

import os
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from loguru import logger

# Import existing kafka client
try:
    from kafka_client.kafka_producer import KafkaProducerWrapper
    from kafka_client.kafka_consumer import KafkaConsumerWrapper
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("Kafka client not available")

# Import algorithms
try:
    from algorithms.deal_scorer import calculate_deal_score, get_deal_quality
except ImportError:
    logger.warning("deal_scorer not available, using mock")
    def calculate_deal_score(current_price, avg_30d_price, availability=10, rating=4.0, has_promotion=False):
        if avg_30d_price <= 0:
            return 50
        discount = (avg_30d_price - current_price) / avg_30d_price
        return min(100, max(0, int(discount * 100 + 50)))
    def get_deal_quality(score):
        if score >= 80: return "excellent"
        if score >= 60: return "great"
        if score >= 40: return "good"
        return "fair"

# Import cache
try:
    from interfaces.deals_cache import deals_cache, Deal
except ImportError:
    deals_cache = None
    logger.warning("deals_cache not available")

# Import watch store for triggering alerts
try:
    from api.watches import watch_store
except ImportError:
    watch_store = None

# Import events manager for WebSocket push
try:
    from api.events_websocket import events_manager
except ImportError:
    events_manager = None


# Topic names from environment
KAFKA_RAW_TOPIC = os.getenv("KAFKA_DEALS_RAW_TOPIC", "raw_supplier_feeds")
KAFKA_NORMALIZED_TOPIC = os.getenv("KAFKA_DEALS_NORMALIZED_TOPIC", "deals.normalized")
KAFKA_SCORED_TOPIC = os.getenv("KAFKA_DEALS_SCORED_TOPIC", "deals.scored")
KAFKA_TAGGED_TOPIC = os.getenv("KAFKA_DEALS_TAGGED_TOPIC", "deals.tagged")
KAFKA_EVENTS_TOPIC = os.getenv("KAFKA_DEAL_EVENTS_TOPIC", "deal.events")


class DealsAgentRunner:
    """
    Background runner for the Deals Agent pipeline.
    Processes deals through: normalize -> score -> tag -> emit
    """
    
    def __init__(self):
        self.producer: Optional[KafkaProducerWrapper] = None
        self.consumer: Optional[KafkaConsumerWrapper] = None
        self.running = False
        self._tasks: List[asyncio.Task] = []
        
        # Deal detection rules
        self.rules = {
            "price_drop_threshold": 0.15,  # 15% below average
            "low_inventory_threshold": 5,   # Less than 5 available
            "high_score_threshold": 70      # Score >= 70 is a deal
        }
        
        # Tag mappings from amenities
        self.amenity_tags = {
            "pet": "pet-friendly",
            "dog": "pet-friendly",
            "cat": "pet-friendly",
            "parking": "parking",
            "wifi": "wifi",
            "breakfast": "breakfast",
            "pool": "pool",
            "gym": "gym",
            "spa": "spa",
            "beach": "beach",
            "refund": "refundable",
            "cancel": "refundable"
        }
    
    async def start(self):
        """Start the Deals Agent"""
        if not KAFKA_AVAILABLE:
            logger.warning("Kafka not available, Deals Agent running in mock mode")
            self.running = True
            return
        
        try:
            # Initialize producer
            self.producer = KafkaProducerWrapper(client_id="deals-agent-producer")
            await self.producer.start()
            
            # Initialize consumer for raw feeds
            self.consumer = KafkaConsumerWrapper(
                topics=[KAFKA_RAW_TOPIC],
                group_id="deals-agent-processor"
            )
            await self.consumer.start()
            
            self.running = True
            
            # Start processing loop
            self._tasks.append(asyncio.create_task(self._process_loop()))
            
            logger.info("Deals Agent started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Deals Agent: {e}")
            self.running = False
    
    async def stop(self):
        """Stop the Deals Agent"""
        self.running = False
        
        # Cancel tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        self._tasks = []
        
        # Stop producer/consumer
        if self.producer:
            await self.producer.stop()
        if self.consumer:
            await self.consumer.stop()
        
        logger.info("Deals Agent stopped")
    
    async def _process_loop(self):
        """Main processing loop"""
        logger.info("Deals Agent processing loop started")
        
        while self.running:
            try:
                if self.consumer:
                    # Consume messages
                    messages = await self.consumer.consume_batch(max_records=10, timeout_ms=1000)
                    
                    for message in messages:
                        await self._process_message(message)
                else:
                    # Mock mode - just wait
                    await asyncio.sleep(5)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(1)
    
    async def _process_message(self, message: Dict[str, Any]):
        """Process a single raw feed message"""
        try:
            # Step 1: Normalize
            normalized = self._normalize(message)
            if not normalized:
                return
            
            # Send to normalized topic
            if self.producer:
                await self.producer.send(KAFKA_NORMALIZED_TOPIC, normalized, key=normalized.get("deal_id"))
            
            # Step 2: Score
            scored = self._score(normalized)
            
            # Send to scored topic
            if self.producer:
                await self.producer.send_scored_deal(
                    key=scored["deal_id"],
                    score=scored["deal_score"],
                    reason=scored.get("score_reason", ""),
                    attrs=scored
                )
            
            # Step 3: Tag
            tagged = self._tag(scored)
            
            # Send to tagged topic
            if self.producer:
                await self.producer.send_tagged_deal(
                    key=tagged["deal_id"],
                    tags=tagged["tags"],
                    attrs=tagged
                )
            
            # Step 4: Check if it's a deal and emit event
            if tagged["deal_score"] >= self.rules["high_score_threshold"]:
                await self._emit_deal_event(tagged)
            
            # Step 5: Update cache
            if deals_cache:
                deal = Deal(
                    deal_id=tagged["deal_id"],
                    listing_type=tagged["listing_type"],
                    listing_id=tagged.get("listing_id", tagged["deal_id"]),
                    name=tagged["name"],
                    destination=tagged.get("destination", ""),
                    origin=tagged.get("origin"),
                    current_price=tagged["current_price"],
                    original_price=tagged.get("original_price", tagged["current_price"]),
                    avg_30d_price=tagged.get("avg_30d_price", tagged["current_price"]),
                    discount_percent=tagged.get("discount_percent", 0),
                    availability=tagged.get("availability", 10),
                    deal_score=tagged["deal_score"],
                    tags=tagged["tags"],
                    discovered_at=datetime.utcnow().isoformat(),
                    metadata=tagged.get("metadata", {})
                )
                deals_cache.add_deal(deal)
            
            # Step 6: Check watches and trigger alerts
            await self._check_watches(tagged)
            
            logger.debug(f"Processed deal: {tagged['deal_id']} score={tagged['deal_score']}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _normalize(self, raw_message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize raw feed data.
        Standardizes currency, dates, field names.
        """
        try:
            data = raw_message.get("data", raw_message)
            listing_type = raw_message.get("listing_type", "hotel")
            
            # Generate deal ID
            deal_id = data.get("id") or data.get("listing_id") or data.get("flight_id") or data.get("hotel_id")
            if not deal_id:
                deal_id = f"{listing_type}_{datetime.utcnow().timestamp()}"
            
            normalized = {
                "deal_id": str(deal_id),
                "listing_type": listing_type,
                "listing_id": str(deal_id),
                "source": raw_message.get("source", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Normalize price fields
            price_fields = ["price", "current_price", "pricePerNight", "price_per_night", "ticketPrice"]
            for field in price_fields:
                if field in data:
                    normalized["current_price"] = float(data[field])
                    break
            else:
                normalized["current_price"] = 0
            
            # Average price
            avg_fields = ["avg_30d_price", "average_price", "avgPrice"]
            for field in avg_fields:
                if field in data:
                    normalized["avg_30d_price"] = float(data[field])
                    break
            else:
                normalized["avg_30d_price"] = normalized["current_price"] * 1.15  # Assume 15% higher
            
            # Original price
            orig_fields = ["original_price", "originalPrice", "listPrice"]
            for field in orig_fields:
                if field in data:
                    normalized["original_price"] = float(data[field])
                    break
            else:
                normalized["original_price"] = normalized["avg_30d_price"]
            
            # Availability
            avail_fields = ["availability", "rooms_left", "seats_left", "stock"]
            for field in avail_fields:
                if field in data:
                    normalized["availability"] = int(data[field])
                    break
            else:
                normalized["availability"] = 10
            
            # Name
            name_fields = ["name", "hotelName", "hotel_name", "airline", "title"]
            for field in name_fields:
                if field in data:
                    normalized["name"] = data[field]
                    break
            else:
                normalized["name"] = f"Deal {deal_id}"
            
            # Location
            if listing_type == "flight":
                normalized["origin"] = data.get("origin", data.get("departure_airport", ""))
                normalized["destination"] = data.get("destination", data.get("arrival_airport", ""))
            else:
                normalized["destination"] = data.get("city", data.get("location", ""))
                normalized["origin"] = None
            
            # Rating
            rating_fields = ["rating", "starRating", "star_rating", "score"]
            for field in rating_fields:
                if field in data:
                    normalized["rating"] = float(data[field])
                    break
            else:
                normalized["rating"] = 4.0
            
            # Amenities (for tagging)
            normalized["amenities"] = data.get("amenities", [])
            if isinstance(normalized["amenities"], str):
                normalized["amenities"] = [a.strip() for a in normalized["amenities"].split(",")]
            
            # Keep original metadata
            normalized["metadata"] = {
                k: v for k, v in data.items() 
                if k not in ["id", "price", "name"]
            }
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing message: {e}")
            return None
    
    def _score(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        """
        Score a normalized deal.
        Applies scoring rules: price drop, scarcity, rating, promotion.
        """
        current_price = normalized.get("current_price", 0)
        avg_price = normalized.get("avg_30d_price", current_price)
        availability = normalized.get("availability", 10)
        rating = normalized.get("rating", 4.0)
        
        # Check for promotion (price significantly below original)
        original_price = normalized.get("original_price", avg_price)
        has_promotion = current_price < original_price * 0.9
        
        # Calculate score
        score_result = calculate_deal_score(
            current_price=current_price,
            avg_30d_price=avg_price,
            availability=availability,
            rating=rating,
            has_promotion=has_promotion
        )
        
        # Handle both int (mock) and DealScoreBreakdown (real)
        if hasattr(score_result, "total_score"):
            score = score_result.total_score
        else:
            score = score_result
        
        # Calculate discount percent
        discount_percent = 0
        if original_price > 0:
            discount_percent = ((original_price - current_price) / original_price) * 100
        
        # Build score reason
        reasons = []
        if avg_price > 0 and current_price < avg_price * 0.85:
            reasons.append(f"{int((1 - current_price/avg_price) * 100)}% below average")
        if availability <= self.rules["low_inventory_threshold"]:
            reasons.append(f"Only {availability} left")
        if rating >= 4.5:
            reasons.append(f"{rating} rating")
        if has_promotion:
            reasons.append("Limited-time offer")
        
        scored = {
            **normalized,
            "deal_score": score,
            "deal_quality": get_deal_quality(score),
            "discount_percent": discount_percent,
            "is_deal": score >= self.rules["high_score_threshold"],
            "score_reason": ", ".join(reasons) if reasons else "Standard pricing"
        }
        
        return scored
    
    def _tag(self, scored: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tag a scored deal.
        Adds tags based on amenities and deal characteristics.
        """
        tags = []
        
        # Tag based on amenities
        amenities = scored.get("amenities", [])
        amenities_lower = " ".join(amenities).lower() if amenities else ""
        
        for keyword, tag in self.amenity_tags.items():
            if keyword in amenities_lower and tag not in tags:
                tags.append(tag)
        
        # Tag based on deal quality
        if scored["deal_score"] >= 80:
            tags.append("excellent-deal")
        elif scored["deal_score"] >= 60:
            tags.append("great-deal")
        
        # Tag based on availability
        if scored.get("availability", 10) <= self.rules["low_inventory_threshold"]:
            tags.append("limited-availability")
        
        # Tag based on listing type specifics
        if scored.get("listing_type") == "flight":
            if scored.get("metadata", {}).get("stops", 1) == 0:
                tags.append("direct-flight")
            if scored.get("metadata", {}).get("flight_class") == "Business":
                tags.append("business-class")
        
        tagged = {
            **scored,
            "tags": tags
        }
        
        return tagged
    
    async def _emit_deal_event(self, tagged: Dict[str, Any]):
        """Emit a deal event for downstream consumers"""
        event = {
            "event_type": "deal_found",
            "deal_id": tagged["deal_id"],
            "listing_type": tagged["listing_type"],
            "name": tagged["name"],
            "destination": tagged.get("destination", ""),
            "current_price": tagged["current_price"],
            "deal_score": tagged["deal_score"],
            "tags": tagged["tags"],
            "message": f"New deal: {tagged['name']} - Score {tagged['deal_score']}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if self.producer:
            await self.producer.send_deal_event(
                key=tagged["deal_id"],
                event_type="deal_found",
                payload=event,
                score=tagged["deal_score"],
                tags=tagged["tags"]
            )
        
        # Also broadcast via WebSocket if available
        if events_manager:
            await events_manager.broadcast_deal(event)
    
    async def _check_watches(self, tagged: Dict[str, Any]):
        """Check if any watches should be triggered"""
        if not watch_store:
            return
        
        listing_id = tagged.get("listing_id", tagged["deal_id"])
        new_price = tagged.get("current_price")
        new_inventory = tagged.get("availability")
        
        # Check and trigger watches
        triggered = watch_store.check_and_trigger(
            listing_id=listing_id,
            new_price=new_price,
            new_inventory=new_inventory
        )
        
        # Push notifications for triggered watches
        if triggered and events_manager:
            for event in triggered:
                await events_manager.send_watch_triggered(
                    user_id=event.user_id,
                    watch_event=event.model_dump()
                )
    
    async def process_csv_feed(self, csv_data: List[Dict[str, Any]], 
                               listing_type: str, source: str = "csv"):
        """
        Process a CSV feed directly (for scheduled scans).
        Called by scheduler or API endpoint.
        """
        logger.info(f"Processing CSV feed: {len(csv_data)} records, type={listing_type}")
        
        for row in csv_data:
            message = {
                "feed_id": f"csv_{datetime.utcnow().timestamp()}",
                "source": source,
                "listing_type": listing_type,
                "data": row,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self._process_message(message)
        
        logger.info(f"Processed {len(csv_data)} records from CSV feed")


# ============================================
# Global Instance
# ============================================

deals_agent = DealsAgentRunner()


# ============================================
# Lifecycle Functions
# ============================================

async def start_deals_agent():
    """Start the deals agent (call on app startup)"""
    await deals_agent.start()


async def stop_deals_agent():
    """Stop the deals agent (call on app shutdown)"""
    await deals_agent.stop()
