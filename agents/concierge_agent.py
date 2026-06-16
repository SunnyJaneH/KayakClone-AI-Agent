# agents/concierge_agent.py
"""
Concierge Agent - Multi-Agent Conversational AI for Travel Planning

Assignment Requirements Satisfied:
1. Pydantic v2 models for request/response
2. SQLModel persistence (SQLite locally)
3. Intent understanding with max 1 clarifying question
4. Fit Score: price vs budget + amenity match + location flag
5. "Why this" (≤25 words) + "What to watch" (≤12 words)
6. Watch with price/inventory thresholds
7. Quote generation with fare class, baggage, fees, cancellation policy
8. WebSocket async updates
9. Semantic Cache with embeddings for similar query detection

5 User Journeys:
1. "Tell me what I should book" → search_bundles
2. "Refine without starting over" → intent merging
3. "Keep an eye on it" → watch_creator
4. "Decide with confidence" → price_analyzer
5. "Book or hand off cleanly" → quote_generator + booking_confirmer
"""

import os
import re
import json
import uuid
import random
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple, Union
from loguru import logger

# Pydantic v2 - Assignment requirement
from pydantic import BaseModel, Field

# Numpy for cosine similarity
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available - semantic cache disabled")

# SQLModel persistence - Assignment requirement
try:
    from sqlmodel import Session, select
    from models.database import get_engine
    from models.concierge_entities import BundleRecord, QuoteRecord, BookingRecord, WatchRecord
    SQLMODEL_AVAILABLE = True
except ImportError:
    SQLMODEL_AVAILABLE = False
    logger.warning("SQLModel not available for persistence")

# LLM imports
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from ollama import Client as OllamaClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

# Redis for Semantic Cache
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - semantic cache will use memory")

# Internal imports
try:
    from interfaces.deals_cache import deals_cache, Deal
except ImportError:
    deals_cache = None
    Deal = None

# Watch store for Redis persistence
try:
    from api.watches import watch_store, WatchCreate as WatchCreateRequest
    WATCH_STORE_AVAILABLE = True
except ImportError:
    watch_store = None
    WatchCreateRequest = None
    WATCH_STORE_AVAILABLE = False


# ============================================
# Pydantic Models (Assignment Requirement)
# ============================================

class FlightInfo(BaseModel):
    """Flight information in a bundle"""
    flight_id: str
    airline: str
    flight_number: Optional[str] = None
    origin: str
    destination: str
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    duration: float = 0
    stops: int = 0
    flight_class: str = "Economy"
    price: float
    available_seats: int = 50
    deal_score: int = 50
    tags: List[str] = Field(default_factory=list)


class HotelInfo(BaseModel):
    """Hotel information in a bundle"""
    hotel_id: str
    name: str
    city: str
    city_code: str
    neighbourhood: str  # Assignment requirement!
    star_rating: int = 3
    price_per_night: float
    available_rooms: int = 10
    amenities: List[str] = Field(default_factory=list)
    is_refundable: bool = True
    pet_friendly: bool = False
    breakfast_included: bool = False
    near_transit: bool = False  # Assignment requirement!
    deal_score: int = 50
    tags: List[str] = Field(default_factory=list)


class Bundle(BaseModel):
    """Flight + Hotel bundle - Assignment requirement"""
    bundle_id: str
    flight: FlightInfo
    hotel: HotelInfo
    total_price: float
    savings: float = 0
    deal_score: int = 50
    fit_score: int = 50  # Assignment: price vs budget + amenity + location
    why_this: str = ""   # Assignment: ≤25 words
    what_to_watch: str = ""  # Assignment: ≤12 words


class Watch(BaseModel):
    """Active watch"""
    watch_id: str
    user_id: str
    listing_type: str
    listing_id: str
    listing_name: str
    watch_type: str
    price_threshold: Optional[float] = None
    inventory_threshold: Optional[int] = None
    current_price: Optional[float] = None
    current_inventory: Optional[int] = None
    is_active: bool = True
    created_at: str


class QuoteBreakdown(BaseModel):
    """Quote pricing breakdown - Assignment requirements"""
    flight_base: float
    flight_taxes: float
    flight_fees: float
    hotel_base: float
    hotel_taxes: float
    hotel_fees: float
    subtotal: float
    total_taxes: float
    total_fees: float
    grand_total: float
    fare_class: str = "Economy"
    baggage: str = "1 carry-on included"
    cancellation_policy: str = "Contact provider for details"


class FullQuote(BaseModel):
    """Full quote with breakdown - Assignment requirement"""
    quote_id: str
    bundle_id: str
    travelers: int = 1
    nights: int = 3
    breakdown: QuoteBreakdown
    valid_until: str
    status: str = "pending"


class ChatResponse(BaseModel):
    """Chat response"""
    message: str
    bundles: Optional[List[Bundle]] = None
    quote: Optional[FullQuote] = None
    watch: Optional[Watch] = None
    booking_reference: Optional[str] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    intent: Optional[Dict[str, Any]] = None


# ============================================
# City/Airport Mappings
# ============================================

CITY_TO_AIRPORT = {
    "delhi": "DEL",
    "mumbai": "BOM",
    "bangalore": "BLR",
    "bengaluru": "BLR",
    "chennai": "MAA",
    "kolkata": "CCU",
    "hyderabad": "HYD",
    "new delhi": "DEL",
}

AIRPORT_TO_CITY = {v: k.title() for k, v in CITY_TO_AIRPORT.items()}


# ============================================
# MRKL Tools
# ============================================

class MRKLTools:
    """
    MRKL-style tools for Concierge Agent.
    6 tools as specified in assignment.
    """

    def __init__(self, user_id: str = "anonymous", session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self._user_bundles_cache: Dict[str, List[Bundle]] = {}
        self._quotes_cache: Dict[str, FullQuote] = {}

    def get_tools_schema(self) -> List[Dict]:
        """Get OpenAI-compatible tool schemas"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_bundles",
                    "description": "Search for flight + hotel bundles based on user preferences.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "destination": {"type": "string", "description": "Destination city or airport code"},
                            "origin": {"type": "string", "description": "Origin city or airport code"},
                            "budget": {"type": "number", "description": "Maximum total budget"},
                            "preferences": {"type": "array", "items": {"type": "string"}, "description": "Preferences like pet-friendly, breakfast"}
                        },
                        "required": ["destination"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "price_analyzer",
                    "description": "Analyze if current price is good compared to 30-day average.",
                    "parameters": {
                        "type": "object",
                        "properties": {"bundle_id": {"type": "string"}},
                        "required": ["bundle_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "watch_creator",
                    "description": "Create a price/inventory watch for a bundle.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bundle_id": {"type": "string"},
                            "price_threshold": {"type": "number"},
                            "inventory_threshold": {"type": "integer"}
                        },
                        "required": ["bundle_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "quote_generator",
                    "description": "Generate detailed quote with fare class, baggage, fees, and cancellation policy.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bundle_id": {"type": "string"},
                            "travelers": {"type": "integer", "default": 1},
                            "nights": {"type": "integer", "default": 3}
                        },
                        "required": ["bundle_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "policy_lookup",
                    "description": "Look up cancellation, baggage, or pet policies.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bundle_id": {"type": "string"},
                            "policy_type": {"type": "string", "enum": ["cancellation", "baggage", "pet", "all"]}
                        },
                        "required": ["bundle_id", "policy_type"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "booking_confirmer",
                    "description": "Confirm booking and generate booking reference.",
                    "parameters": {
                        "type": "object",
                        "properties": {"quote_id": {"type": "string"}},
                        "required": ["quote_id"]
                    }
                }
            }
        ]

    # ----------------------------------------
    # Tool 1: search_bundles
    # ----------------------------------------
    def search_bundles(
        self,
        destination: str,
        origin: Optional[str] = None,
        budget: Optional[float] = None,
        preferences: Optional[List[str]] = None
    ) -> List[Bundle]:
        """Search for flight + hotel bundles. Journey 1: Tell me what I should book"""
        logger.info(f"search_bundles: dest={destination}, origin={origin}, budget={budget}")
        
        dest_code = self._normalize_city(destination)
        origin_code = self._normalize_city(origin) if origin else None
        
        if not dest_code:
            return []
        
        # Get deals from cache
        flights, hotels = [], []
        if deals_cache:
            try:
                deals_result = deals_cache.get_deals_for_bundle(
                    destination=dest_code,
                    origin=origin_code,
                    max_flight_price=budget * 0.6 if budget else None,
                    max_hotel_price=budget * 0.4 / 3 if budget else None,
                    tags=preferences
                )
                # Handle both dict and other return types
                if isinstance(deals_result, dict):
                    flights = deals_result.get("flights", [])
                    hotels = deals_result.get("hotels", [])
                else:
                    logger.warning(f"Unexpected deals_result type: {type(deals_result)}")
            except Exception as e:
                logger.error(f"Error getting deals: {e}")
        
        bundles = self._build_bundles(flights, hotels, budget, preferences or [], 3)
        self._user_bundles_cache[self.user_id] = bundles
        self._persist_bundles(bundles, origin_code, dest_code, budget)
        
        return bundles

    def _build_bundles(self, flights: List, hotels: List, budget: Optional[float], 
                       preferences: List[str], nights: int = 3) -> List[Bundle]:
        """Build bundle combinations from flights and hotels"""
        bundles = []
        if not flights or not hotels:
            return []
        
        for i, (flight, hotel) in enumerate(zip(flights[:3], hotels[:3])):
            bundle_id = f"BDL-{uuid.uuid4().hex[:8].upper()}"
            
            # Convert to Pydantic models
            flight_info = self._to_flight_info(flight)
            hotel_info = self._to_hotel_info(hotel)
            
            total_price = flight_info.price + (hotel_info.price_per_night * nights)
            avg_deal_score = (flight_info.deal_score + hotel_info.deal_score) // 2
            
            # Calculate Fit Score (Assignment: price vs budget + amenity + location)
            fit_score = self._calculate_fit_score(flight_info, hotel_info, total_price, budget, preferences)
            
            # Generate explanations (Assignment: ≤25 words, ≤12 words)
            why_this, what_to_watch = self._generate_explanation(flight_info, hotel_info, fit_score, avg_deal_score)
            
            bundle = Bundle(
                bundle_id=bundle_id,
                flight=flight_info,
                hotel=hotel_info,
                total_price=round(total_price, 2),
                savings=0,
                deal_score=avg_deal_score,
                fit_score=fit_score,
                why_this=why_this,
                what_to_watch=what_to_watch
            )
            bundles.append(bundle)
        
        bundles.sort(key=lambda b: b.fit_score, reverse=True)
        return bundles

    def _to_flight_info(self, flight) -> FlightInfo:
        """Convert Deal or dict to FlightInfo"""
        if hasattr(flight, 'listing_id'):  # Deal object
            return FlightInfo(
                flight_id=flight.listing_id,
                airline=flight.metadata.get("airline", "Unknown"),
                flight_number=flight.metadata.get("flight_number"),
                origin=flight.origin or "",
                destination=flight.destination,
                departure_time=flight.metadata.get("departure_time"),
                arrival_time=flight.metadata.get("arrival_time"),
                duration=flight.metadata.get("duration", 0),
                stops=flight.metadata.get("stops", 0),
                flight_class=flight.metadata.get("class", "Economy"),
                price=flight.current_price,
                available_seats=flight.availability,
                deal_score=flight.deal_score,
                tags=flight.tags
            )
        else:  # dict
            meta = flight.get("metadata", {})
            return FlightInfo(
                flight_id=flight.get("listing_id", flight.get("flight_id", "")),
                airline=meta.get("airline", flight.get("airline", "Unknown")),
                flight_number=meta.get("flight_number"),
                origin=flight.get("origin", ""),
                destination=flight.get("destination", ""),
                duration=meta.get("duration", 0),
                stops=meta.get("stops", 0),
                flight_class=meta.get("class", "Economy"),
                price=flight.get("current_price", flight.get("price", 0)),
                available_seats=flight.get("availability", 50),
                deal_score=flight.get("deal_score", 50),
                tags=flight.get("tags", [])
            )

    def _to_hotel_info(self, hotel) -> HotelInfo:
        """Convert Deal or dict to HotelInfo"""
        if hasattr(hotel, 'listing_id'):  # Deal object
            return HotelInfo(
                hotel_id=hotel.listing_id,
                name=hotel.name,
                city=hotel.metadata.get("city", ""),
                city_code=hotel.metadata.get("city_code", hotel.destination),
                neighbourhood=hotel.metadata.get("neighbourhood", "City Center"),
                star_rating=hotel.metadata.get("star_rating", 3),
                price_per_night=hotel.current_price,
                available_rooms=hotel.availability,
                amenities=hotel.metadata.get("amenities", []),
                is_refundable=hotel.metadata.get("is_refundable", True),
                pet_friendly=hotel.metadata.get("pet_friendly", False),
                breakfast_included=hotel.metadata.get("breakfast_included", False),
                near_transit=hotel.metadata.get("near_transit", False),
                deal_score=hotel.deal_score,
                tags=hotel.tags
            )
        else:  # dict
            meta = hotel.get("metadata", {})
            return HotelInfo(
                hotel_id=hotel.get("listing_id", hotel.get("hotel_id", "")),
                name=hotel.get("name", "Hotel"),
                city=meta.get("city", hotel.get("city", "")),
                city_code=meta.get("city_code", hotel.get("destination", "")),
                neighbourhood=meta.get("neighbourhood", "City Center"),
                star_rating=meta.get("star_rating", 3),
                price_per_night=hotel.get("current_price", hotel.get("price_per_night", 0)),
                available_rooms=hotel.get("availability", 10),
                amenities=meta.get("amenities", []),
                is_refundable=meta.get("is_refundable", True),
                pet_friendly=meta.get("pet_friendly", False),
                breakfast_included=meta.get("breakfast_included", False),
                near_transit=meta.get("near_transit", False),
                deal_score=hotel.get("deal_score", 50),
                tags=hotel.get("tags", [])
            )

    def _calculate_fit_score(self, flight: FlightInfo, hotel: HotelInfo, 
                             total_price: float, budget: Optional[float], 
                             preferences: List[str]) -> int:
        """Calculate Fit Score. Assignment: price vs budget + amenity match + location flag"""
        score = 50
        
        # 1. Price vs Budget (up to 30 points)
        if budget:
            if total_price <= budget * 0.7:
                score += 30
            elif total_price <= budget * 0.9:
                score += 20
            elif total_price <= budget:
                score += 10
            else:
                score -= 10
        
        # 2. Amenity Match (up to 25 points)
        matched = 0
        all_tags = set(flight.tags + hotel.tags + hotel.amenities)
        for pref in preferences:
            if pref.lower().replace(" ", "-") in str(all_tags).lower():
                matched += 1
        if preferences:
            score += int((matched / len(preferences)) * 25)
        else:
            score += 15
        
        # 3. Location Flag (up to 15 points) - Assignment requirement!
        if hotel.near_transit:
            score += 10
        if hotel.neighbourhood and hotel.neighbourhood != "City Center":
            score += 5
        
        # 4. Deal Score Bonus (up to 15 points)
        avg_deal = (flight.deal_score + hotel.deal_score) / 2
        score += int(avg_deal * 0.15)
        
        # 5. Quality Bonus
        if hotel.star_rating >= 4:
            score += 10
        if flight.stops == 0:
            score += 5
        
        return min(100, max(0, score))

    def _generate_explanation(self, flight: FlightInfo, hotel: HotelInfo, 
                              fit_score: int, deal_score: int) -> Tuple[str, str]:
        """Generate explanations. Assignment: why_this ≤25 words, what_to_watch ≤12 words"""
        # why_this
        parts = []
        if flight.stops == 0:
            parts.append("Direct flight")
        else:
            parts.append(f"{flight.stops}-stop flight")
        parts.append(f"with {flight.airline}")
        parts.append(f"+ {hotel.star_rating}-star hotel in {hotel.neighbourhood}")
        if hotel.breakfast_included:
            parts.append("with breakfast")
        if deal_score >= 70:
            parts.append(f"({deal_score}% deal)")
        
        why_this = " ".join(parts)
        words = why_this.split()
        if len(words) > 25:
            why_this = " ".join(words[:25])
        
        # what_to_watch
        watch_parts = []
        if flight.available_seats < 10:
            watch_parts.append(f"Only {flight.available_seats} seats left")
        if hotel.available_rooms < 5:
            watch_parts.append(f"Only {hotel.available_rooms} rooms left")
        if not watch_parts:
            watch_parts.append("Good deal - prices may increase" if deal_score >= 70 else "Check for price drops")
        
        what_to_watch = ". ".join(watch_parts)
        words = what_to_watch.split()
        if len(words) > 12:
            what_to_watch = " ".join(words[:12])
        
        return why_this, what_to_watch

    def _normalize_city(self, city: Optional[str]) -> Optional[str]:
        """Normalize city name to airport code"""
        if not city:
            return None
        city_lower = city.lower().strip()
        if len(city_lower) == 3 and city_lower.upper() in AIRPORT_TO_CITY:
            return city_lower.upper()
        if city_lower in CITY_TO_AIRPORT:
            return CITY_TO_AIRPORT[city_lower]
        for name, code in CITY_TO_AIRPORT.items():
            if name in city_lower or city_lower in name:
                return code
        return city.upper()[:3]

    def _persist_bundles(self, bundles: List[Bundle], origin: Optional[str], 
                         destination: str, budget: Optional[float]):
        """Persist bundles to SQLite (Assignment requirement)"""
        if not SQLMODEL_AVAILABLE:
            return
        try:
            engine = get_engine()
            with Session(engine) as session:
                for bundle in bundles:
                    record = BundleRecord(
                        bundle_id=bundle.bundle_id,
                        user_id=self.user_id,
                        session_id=self.session_id,
                        origin=origin or "",
                        destination=destination,
                        budget=budget,
                        flight_id=bundle.flight.flight_id,
                        flight_price=bundle.flight.price,
                        hotel_id=bundle.hotel.hotel_id,
                        hotel_price=bundle.hotel.price_per_night,
                        total_price=bundle.total_price,
                        savings=bundle.savings,
                        deal_score=bundle.deal_score,
                        fit_score=bundle.fit_score,
                        explanation_json=json.dumps({"why_this": bundle.why_this, "what_to_watch": bundle.what_to_watch}),
                        bundle_data_json=bundle.model_dump_json()
                    )
                    session.add(record)
                session.commit()
            logger.info(f"Persisted {len(bundles)} bundles to SQLite")
        except Exception as e:
            logger.error(f"Error persisting bundles: {e}")

    # ----------------------------------------
    # Tool 2: price_analyzer
    # ----------------------------------------
    def price_analyzer(self, bundle_id: str) -> Dict[str, Any]:
        """Analyze price vs 30-day average. Journey 4: Decide with confidence"""
        bundle = self._get_bundle(bundle_id)
        if not bundle:
            return {"error": f"Bundle {bundle_id} not found"}
        
        flight = bundle.flight
        hotel = bundle.hotel
        
        # Calculate discount percentages vs 30-day average (simulated)
        # In real system, this would come from avg_30d_price field
        flight_avg_30d = flight.price * (1 + random.uniform(0.10, 0.25))  # Simulate avg is 10-25% higher
        hotel_avg_30d = hotel.price_per_night * (1 + random.uniform(0.12, 0.28))
        
        flight_discount_pct = ((flight_avg_30d - flight.price) / flight_avg_30d) * 100
        hotel_discount_pct = ((hotel_avg_30d - hotel.price_per_night) / hotel_avg_30d) * 100
        
        # Simulate similar hotels in area (slightly higher priced)
        similar_hotel_low = hotel.price_per_night + random.uniform(15, 35)
        similar_hotel_high = hotel.price_per_night + random.uniform(45, 80)
        
        return {
            "bundle_id": bundle_id,
            "current_total": bundle.total_price,
            "flight": {
                "price": flight.price,
                "avg_30d_price": round(flight_avg_30d, 2),
                "discount_percent": round(flight_discount_pct, 1),
                "deal_score": flight.deal_score,
                "recommendation": "Good price" if flight.deal_score >= 60 else "Wait for better deal"
            },
            "hotel": {
                "price_per_night": hotel.price_per_night,
                "avg_30d_price": round(hotel_avg_30d, 2),
                "discount_percent": round(hotel_discount_pct, 1),
                "deal_score": hotel.deal_score,
                "star_rating": hotel.star_rating,
                "similar_hotels_range": [round(similar_hotel_low, 2), round(similar_hotel_high, 2)],
                "recommendation": "Good price" if hotel.deal_score >= 60 else "Wait for better deal"
            },
            "overall": {
                "deal_score": bundle.deal_score,
                "avg_discount_percent": round((flight_discount_pct + hotel_discount_pct) / 2, 1),
                "recommendation": "Book now" if bundle.deal_score >= 65 else "Consider watching for drops"
            }
        }

    # ----------------------------------------
    # Tool 3: watch_creator
    # ----------------------------------------
    def watch_creator(self, bundle_id: str, price_threshold: Optional[float] = None,
                      inventory_threshold: Optional[int] = None) -> Watch:
        """Create price/inventory watch. Journey 3: Keep an eye on it"""
        bundle = self._get_bundle(bundle_id)
        if not bundle:
            return Watch(watch_id="error", user_id=self.user_id, listing_type="bundle",
                        listing_id=bundle_id, listing_name="Unknown", watch_type="error",
                        is_active=False, created_at=datetime.utcnow().isoformat())
        
        if price_threshold is None:
            price_threshold = bundle.total_price * 0.9
        if inventory_threshold is None:
            inventory_threshold = 5
        
        watch_id = f"W-{uuid.uuid4().hex[:8].upper()}"
        watch = Watch(
            watch_id=watch_id,
            user_id=self.user_id,
            listing_type="bundle",
            listing_id=bundle_id,
            listing_name=f"{bundle.flight.origin}→{bundle.flight.destination} + {bundle.hotel.name}",
            watch_type="both",
            price_threshold=price_threshold,
            inventory_threshold=inventory_threshold,
            current_price=bundle.total_price,
            current_inventory=min(bundle.flight.available_seats, bundle.hotel.available_rooms),
            is_active=True,
            created_at=datetime.utcnow().isoformat()
        )
        
        # Save to Redis watch_store (for WebSocket notifications)
        if WATCH_STORE_AVAILABLE and watch_store:
            try:
                watch_data = WatchCreateRequest(
                    user_id=self.user_id,
                    listing_type="bundle",
                    listing_id=bundle_id,
                    listing_name=watch.listing_name,
                    watch_type="price",
                    threshold=price_threshold,
                    current_value=bundle.total_price
                )
                redis_watch = watch_store.create_watch(watch_data)
                watch.watch_id = redis_watch.watch_id  # Use Redis watch ID
                logger.info(f"Watch saved to Redis: {redis_watch.watch_id}")
            except Exception as e:
                logger.error(f"Error saving watch to Redis: {e}")
        
        # Also persist to SQLite for backup
        if SQLMODEL_AVAILABLE:
            try:
                engine = get_engine()
                with Session(engine) as session:
                    record = WatchRecord(
                        watch_id=watch.watch_id, user_id=self.user_id, listing_type="bundle",
                        listing_id=bundle_id, listing_name=watch.listing_name,
                        watch_type="both", price_threshold=price_threshold,
                        inventory_threshold=inventory_threshold,
                        current_price=bundle.total_price,
                        current_inventory=min(bundle.flight.available_seats, bundle.hotel.available_rooms),
                        is_active=True
                    )
                    session.add(record)
                    session.commit()
            except Exception as e:
                logger.error(f"Error persisting watch to SQLite: {e}")
        
        return watch

    # ----------------------------------------
    # Tool 4: quote_generator
    # ----------------------------------------
    def quote_generator(self, bundle_id: str, travelers: int = 1, nights: int = 3) -> FullQuote:
        """Generate detailed quote. Assignment: fare class, baggage, fees, cancellation policy"""
        bundle = self._get_bundle(bundle_id)
        if not bundle:
            return FullQuote(
                quote_id="error", bundle_id=bundle_id,
                breakdown=QuoteBreakdown(
                    flight_base=0, flight_taxes=0, flight_fees=0,
                    hotel_base=0, hotel_taxes=0, hotel_fees=0,
                    subtotal=0, total_taxes=0, total_fees=0, grand_total=0
                ),
                valid_until=datetime.utcnow().isoformat(), status="error"
            )
        
        flight = bundle.flight
        hotel = bundle.hotel
        
        flight_base = flight.price * travelers
        flight_taxes = round(flight_base * 0.12, 2)
        flight_fees = round(25 * travelers, 2)
        
        hotel_base = hotel.price_per_night * nights
        hotel_taxes = round(hotel_base * 0.18, 2)
        hotel_fees = round(15 * nights, 2)
        
        subtotal = flight_base + hotel_base
        total_taxes = flight_taxes + hotel_taxes
        total_fees = flight_fees + hotel_fees
        grand_total = subtotal + total_taxes + total_fees
        
        cancellation = "Free cancellation up to 24 hours before check-in." if hotel.is_refundable else "Non-refundable."
        baggage = "2 checked bags included." if flight.flight_class.lower() == "business" else "1 carry-on + 1 personal item. Checked bag: $35."
        
        breakdown = QuoteBreakdown(
            flight_base=round(flight_base, 2), flight_taxes=round(flight_taxes, 2), flight_fees=round(flight_fees, 2),
            hotel_base=round(hotel_base, 2), hotel_taxes=round(hotel_taxes, 2), hotel_fees=round(hotel_fees, 2),
            subtotal=round(subtotal, 2), total_taxes=round(total_taxes, 2), total_fees=round(total_fees, 2),
            grand_total=round(grand_total, 2),
            fare_class=flight.flight_class, baggage=baggage, cancellation_policy=cancellation
        )
        
        quote_id = f"Q-{uuid.uuid4().hex[:8].upper()}"
        valid_until = datetime.utcnow() + timedelta(hours=24)
        
        quote = FullQuote(
            quote_id=quote_id, bundle_id=bundle_id, travelers=travelers, nights=nights,
            breakdown=breakdown, valid_until=valid_until.isoformat(), status="pending"
        )
        
        self._quotes_cache[quote_id] = quote
        
        # Persist to SQLite
        if SQLMODEL_AVAILABLE:
            try:
                engine = get_engine()
                with Session(engine) as session:
                    record = QuoteRecord(
                        quote_id=quote_id, user_id=self.user_id, bundle_id=bundle_id,
                        travelers=travelers, nights=nights,
                        flight_total=flight_base + flight_taxes + flight_fees,
                        hotel_total=hotel_base + hotel_taxes + hotel_fees,
                        subtotal=subtotal, taxes=total_taxes, fees=total_fees, grand_total=grand_total,
                        fare_class=flight.flight_class, baggage=baggage, cancellation_policy=cancellation,
                        breakdown_json=breakdown.model_dump_json(), valid_until=valid_until, status="pending"
                    )
                    session.add(record)
                    session.commit()
            except Exception as e:
                logger.error(f"Error persisting quote: {e}")
        
        return quote

    # ----------------------------------------
    # Tool 5: policy_lookup
    # ----------------------------------------
    def policy_lookup(self, bundle_id: str, policy_type: str = "all") -> Dict[str, str]:
        """Look up policies from listing metadata. Assignment requirement."""
        bundle = self._get_bundle(bundle_id)
        if not bundle:
            return {"error": f"Bundle {bundle_id} not found"}
        
        hotel = bundle.hotel
        flight = bundle.flight
        policies = {}
        
        if policy_type in ["cancellation", "all"]:
            policies["cancellation"] = f"Hotel: {'Free cancellation up to 24 hours before check-in.' if hotel.is_refundable else 'Non-refundable.'} Flight: Contact {flight.airline} for terms."
        
        if policy_type in ["baggage", "all"]:
            policies["baggage"] = "2 checked bags included." if flight.flight_class.lower() == "business" else "1 carry-on + 1 personal item. Checked bags: $35 each way."
        
        if policy_type in ["pet", "all"]:
            policies["pet"] = f"{hotel.name} {'is pet-friendly. Pet fee may apply.' if hotel.pet_friendly else 'does not allow pets.'}"
        
        return policies

    # ----------------------------------------
    # Tool 6: booking_confirmer
    # ----------------------------------------
    def booking_confirmer(self, quote_id: str) -> Dict[str, Any]:
        """Confirm booking. Journey 5: Book or hand off cleanly"""
        booking_ref = f"BK{random.randint(10000, 99999)}{uuid.uuid4().hex[:3].upper()}"
        booking_id = f"BOOK-{uuid.uuid4().hex[:8].upper()}"
        
        # Persist to SQLite
        if SQLMODEL_AVAILABLE:
            try:
                engine = get_engine()
                with Session(engine) as session:
                    stmt = select(QuoteRecord).where(QuoteRecord.quote_id == quote_id)
                    quote_record = session.exec(stmt).first()
                    
                    if quote_record:
                        quote_record.status = "confirmed"
                        record = BookingRecord(
                            booking_id=booking_id, booking_reference=booking_ref,
                            user_id=self.user_id, quote_id=quote_id, bundle_id=quote_record.bundle_id,
                            total_price=quote_record.grand_total, travelers=quote_record.travelers,
                            status="confirmed",
                            booking_data_json=json.dumps({"quote_id": quote_id, "confirmed_at": datetime.utcnow().isoformat()})
                        )
                        session.add(record)
                        session.commit()
            except Exception as e:
                logger.error(f"Error persisting booking: {e}")
        
        return {
            "success": True,
            "booking_reference": booking_ref,
            "booking_id": booking_id,
            "quote_id": quote_id,
            "status": "confirmed",
            "message": f"Booking confirmed! Reference: {booking_ref}"
        }

    def _get_bundle(self, bundle_id: str) -> Optional[Bundle]:
        """Get bundle from cache or database"""
        for bundles in self._user_bundles_cache.values():
            for bundle in bundles:
                if bundle.bundle_id == bundle_id:
                    return bundle
        
        if SQLMODEL_AVAILABLE:
            try:
                engine = get_engine()
                with Session(engine) as session:
                    stmt = select(BundleRecord).where(BundleRecord.bundle_id == bundle_id)
                    record = session.exec(stmt).first()
                    if record:
                        return Bundle.model_validate_json(record.bundle_data_json)
            except Exception as e:
                logger.error(f"Error getting bundle: {e}")
        return None


# ============================================
# Concierge Agent
# ============================================

class ConciergeAgent:
    """Main Concierge Agent with LLM integration and Semantic Cache."""
    
    # Semantic cache configuration
    SEMANTIC_CACHE_TTL = 300  # 5 minutes
    SIMILARITY_THRESHOLD = 0.85  # Cosine similarity threshold for cache hit
    SEMANTIC_CACHE_PREFIX = "semantic_cache:"  # Redis key prefix

    def __init__(self, user_id: str = "anonymous", session_id: str = None):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.tools = MRKLTools(user_id, self.session_id)
        self._intent_cache: Dict[str, Any] = {}
        self._asked_clarification = False
        self._previous_bundles: List[Bundle] = []  # For tracking changes
        self._previous_preferences: List[str] = []  # For tracking refinements
        
        # Redis for Semantic Cache
        self.redis_client = None
        self._init_redis()
        
        # LLM client
        self.llm_client = None
        self.llm_model = None
        self.embedding_model = None
        self._init_llm()
    
    def _init_redis(self):
        """Initialize Redis connection for Semantic Cache"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available for semantic cache")
            return
        
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=False  # We'll handle encoding ourselves for embeddings
            )
            self.redis_client.ping()
            logger.info(f"Semantic Cache connected to Redis at {redis_host}:{redis_port}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self.redis_client = None

    def _init_llm(self):
        """Initialize LLM client and embedding model"""
        self.llm_type = None
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if OPENAI_AVAILABLE and openai_key:
            try:
                self.llm_client = OpenAI(api_key=openai_key)
                self.llm_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
                self.embedding_model = "text-embedding-3-small"  # OpenAI embedding model
                self.llm_type = "openai"
                logger.info(f"Using OpenAI: {self.llm_model}, Embeddings: {self.embedding_model}")
                return
            except Exception as e:
                logger.warning(f"OpenAI init failed: {e}")
        
        if OLLAMA_AVAILABLE:
            try:
                ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                self.llm_client = OllamaClient(host=ollama_url)
                self.llm_model = os.getenv("OLLAMA_MODEL", "llama3.2")
                self.embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
                self.llm_type = "ollama"
                logger.info(f"Using Ollama: {self.llm_model}, Embeddings: {self.embedding_model}")
                return
            except Exception as e:
                logger.warning(f"Ollama init failed: {e}")
        
        logger.warning("No LLM available, using rule-based fallback")

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding vector for text using OpenAI or Ollama"""
        if not self.llm_client or not NUMPY_AVAILABLE:
            return None
        
        try:
            if self.llm_type == "openai":
                response = self.llm_client.embeddings.create(
                    model=self.embedding_model,
                    input=text
                )
                return response.data[0].embedding
            
            elif self.llm_type == "ollama":
                response = self.llm_client.embeddings(
                    model=self.embedding_model,
                    prompt=text
                )
                return response['embedding']
        
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if not NUMPY_AVAILABLE:
            return 0.0
        
        try:
            a = np.array(vec1)
            b = np.array(vec2)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
        except Exception as e:
            logger.warning(f"Cosine similarity calculation failed: {e}")
            return 0.0
    
    def _check_semantic_cache(self, query: str) -> Optional[Dict[str, Any]]:
        """Check if similar query exists in Redis semantic cache"""
        if not NUMPY_AVAILABLE or not self.llm_client or not self.redis_client:
            return None
        
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return None
        
        best_match = None
        best_similarity = 0.0
        
        try:
            # Get all semantic cache keys from Redis
            pattern = f"{self.SEMANTIC_CACHE_PREFIX}*"
            keys = self.redis_client.keys(pattern)
            
            for key in keys:
                try:
                    cached_data = self.redis_client.get(key)
                    if not cached_data:
                        continue
                    
                    cached = json.loads(cached_data.decode('utf-8'))
                    cached_embedding = cached.get("embedding", [])
                    
                    similarity = self._cosine_similarity(query_embedding, cached_embedding)
                    if similarity > best_similarity and similarity >= self.SIMILARITY_THRESHOLD:
                        best_similarity = similarity
                        best_match = cached["intent"]
                        
                except Exception as e:
                    logger.warning(f"Error reading cache key {key}: {e}")
                    continue
            
            if best_match:
                logger.info(f"Semantic cache HIT from Redis (similarity: {best_similarity:.3f})")
                return best_match
            
        except Exception as e:
            logger.warning(f"Redis semantic cache check failed: {e}")
        
        return None
    
    def _update_semantic_cache(self, query: str, intent: Dict[str, Any]):
        """Update Redis semantic cache with new query and intent"""
        if not NUMPY_AVAILABLE or not self.llm_client or not self.redis_client:
            return
        
        embedding = self._get_embedding(query)
        if not embedding:
            return
        
        try:
            # Use hash of query as key
            query_hash = hashlib.md5(query.lower().strip().encode()).hexdigest()
            redis_key = f"{self.SEMANTIC_CACHE_PREFIX}{query_hash}"
            
            cache_data = {
                "embedding": embedding,
                "intent": intent,
                "query": query
            }
            
            # Store in Redis with TTL
            self.redis_client.setex(
                redis_key,
                self.SEMANTIC_CACHE_TTL,
                json.dumps(cache_data)
            )
            
            # Get current cache size
            cache_size = len(self.redis_client.keys(f"{self.SEMANTIC_CACHE_PREFIX}*"))
            logger.info(f"Semantic cache updated in Redis, total entries: {cache_size}")
            
        except Exception as e:
            logger.warning(f"Redis semantic cache update failed: {e}")

    def _call_llm(self, prompt: str, system_prompt: str = None) -> Optional[str]:
        """Call LLM for intent parsing or response generation"""
        if not self.llm_client:
            return None
        
        try:
            if self.llm_type == "openai":
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                response = self.llm_client.chat.completions.create(
                    model=self.llm_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=500
                )
                return response.choices[0].message.content
            
            elif self.llm_type == "ollama":
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                response = self.llm_client.chat(
                    model=self.llm_model,
                    messages=messages
                )
                return response['message']['content']
        
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return None
    
    def _llm_parse_intent(self, message: str) -> Optional[Dict[str, Any]]:
        """Use LLM to parse user intent"""
        system_prompt = """You are a travel intent parser. Extract structured information from user queries.
Return ONLY valid JSON with these fields:
{
  "action": "search" | "watch" | "quote" | "analyze" | "policy" | "confirm" | null,
  "destination": "city name" | null,
  "origin": "city name" | null,
  "budget": number | null,
  "preferences": ["pet-friendly", "breakfast", "direct", "near-transit"],
  "option_number": 1 | 2 | 3 | null
}

Action meanings:
- search: find flights/hotels/bundles
- watch: create price alert
- quote: get full booking quote  
- analyze: check if price is good
- policy: ask about cancellation/pets/baggage
- confirm: proceed with booking

Examples:
"Find trips from Delhi to Mumbai with breakfast" -> {"action": "search", "destination": "Mumbai", "origin": "Delhi", "budget": null, "preferences": ["breakfast"], "option_number": null}
"Is this a good deal?" -> {"action": "analyze", "destination": null, "origin": null, "budget": null, "preferences": [], "option_number": null}
"Watch option 1 if price drops below $2000" -> {"action": "watch", "destination": null, "origin": null, "budget": 2000, "preferences": [], "option_number": 1}
"Can I bring pets?" -> {"action": "policy", "destination": null, "origin": null, "budget": null, "preferences": ["pet-friendly"], "option_number": null}
"Book it" -> {"action": "confirm", "destination": null, "origin": null, "budget": null, "preferences": [], "option_number": null}"""

        response = self._call_llm(message, system_prompt)
        if not response:
            return None
        
        try:
            import json
            # Handle markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
            
            intent = json.loads(response.strip())
            logger.info(f"LLM parsed intent: {intent}")
            return intent
        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None

    def chat(self, message: str, context: Optional[Dict] = None) -> ChatResponse:
        """Process user message and return response."""
        logger.info(f"Chat: {message[:100]}...")
        
        intent = self._parse_intent(message)
        merged_intent = self._merge_intent(intent)
        
        # Check if clarification needed (Assignment: max 1)
        if not merged_intent.get("destination") and not self._asked_clarification:
            self._asked_clarification = True
            return ChatResponse(
                message="I'd love to help you find the perfect trip! Which city would you like to visit?",
                needs_clarification=True,
                clarification_question="destination",
                intent=merged_intent
            )
        
        return self._execute_intent(merged_intent, message)

    def _parse_intent(self, message: str) -> Dict[str, Any]:
        """Parse user intent from message - Semantic Cache → LLM → Rule-based fallback"""
        
        # 1. Check Semantic Cache first
        cached_intent = self._check_semantic_cache(message)
        if cached_intent:
            logger.info(f"Using cached intent from semantic cache")
            return cached_intent
        
        # 2. Try LLM parsing
        llm_intent = self._llm_parse_intent(message)
        if llm_intent:
            # Normalize LLM output
            intent = {
                "action": llm_intent.get("action"),
                "destination": llm_intent.get("destination"),
                "origin": llm_intent.get("origin"),
                "budget": llm_intent.get("budget"),
                "preferences": llm_intent.get("preferences", []),
                "bundle_id": None,
                "quote_id": None,
                "option_number": llm_intent.get("option_number")
            }
            # Update semantic cache with new intent
            self._update_semantic_cache(message, intent)
            return intent
        
        # 3. Fallback to rule-based parsing
        logger.info("Using rule-based intent parsing (LLM unavailable)")
        intent = {"action": None, "destination": None, "origin": None, "budget": None, "preferences": [], "bundle_id": None, "quote_id": None, "option_number": None}
        msg_lower = message.lower()
        
        # Detect action - order matters! More specific first
        if any(w in msg_lower for w in ["watch", "alert", "notify", "track", "monitor"]):
            intent["action"] = "watch"
        elif any(w in msg_lower for w in ["confirm", "book it", "yes proceed", "complete booking"]):
            intent["action"] = "confirm"
        elif any(w in msg_lower for w in ["full quote", "total cost", "how much total", "get quote"]):
            intent["action"] = "quote"
        elif any(w in msg_lower for w in ["analyze", "good deal", "worth it", "should i book"]):
            intent["action"] = "analyze"
        elif any(w in msg_lower for w in ["policy", "cancel", "refund", "baggage rules", "can i bring", "bring pet", "pet allowed", "pets allowed", "pet-friendly policy", "cancellation"]):
            intent["action"] = "policy"
        elif any(w in msg_lower for w in ["search", "find", "trip", "travel", "fly", "hotel", "show me", "get me"]):
            intent["action"] = "search"
        
        # Special case: questions about pets without search intent
        if "can i" in msg_lower and "pet" in msg_lower:
            intent["action"] = "policy"
        
        # Build list of all known cities and codes
        all_locations = list(CITY_TO_AIRPORT.keys()) + [c.lower() for c in AIRPORT_TO_CITY.keys()]
        
        # Try to extract "from X to Y" pattern first
        from_to_pattern = r'(?:from|leaving|departing)\s+(\w+(?:\s+\w+)?)\s+(?:to|for|going to|heading to)\s+(\w+(?:\s+\w+)?)'
        from_to_match = re.search(from_to_pattern, msg_lower)
        
        if from_to_match:
            origin_text = from_to_match.group(1).strip()
            dest_text = from_to_match.group(2).strip()
            
            # Match origin
            for loc in all_locations:
                if loc in origin_text or origin_text in loc:
                    intent["origin"] = loc.upper() if len(loc) == 3 else loc.title()
                    break
            
            # Match destination
            for loc in all_locations:
                if loc in dest_text or dest_text in loc:
                    intent["destination"] = loc.upper() if len(loc) == 3 else loc.title()
                    break
        
        # Try "to X" pattern if no destination yet
        if not intent["destination"]:
            to_pattern = r'(?:to|for|visit|visiting)\s+(\w+(?:\s+\w+)?)'
            to_match = re.search(to_pattern, msg_lower)
            if to_match:
                dest_text = to_match.group(1).strip()
                for loc in all_locations:
                    if loc in dest_text or dest_text in loc:
                        intent["destination"] = loc.upper() if len(loc) == 3 else loc.title()
                        break
        
        # Fallback: find any city mentioned
        if not intent["destination"]:
            for city in CITY_TO_AIRPORT.keys():
                if city in msg_lower:
                    intent["destination"] = city.title()
                    break
        
        # Also check IATA codes (DEL, BOM, etc.)
        if not intent["destination"]:
            for code in AIRPORT_TO_CITY.keys():
                if code.lower() in msg_lower.split():
                    intent["destination"] = code
                    break
        
        # Extract budget - only if explicitly mentioned
        budget_match = re.search(r'(?:under|below|budget|max|less than)\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)', message, re.IGNORECASE)
        if budget_match:
            intent["budget"] = float(budget_match.group(1).replace(",", ""))
        
        # Extract preferences
        if "pet" in msg_lower:
            intent["preferences"].append("pet-friendly")
        if "breakfast" in msg_lower:
            intent["preferences"].append("breakfast")
        if "direct" in msg_lower:
            intent["preferences"].append("direct-flight")
        if "transit" in msg_lower:
            intent["preferences"].append("near-transit")
        
        # Extract IDs
        bundle_match = re.search(r'BDL-[A-Z0-9]+', message, re.IGNORECASE)
        if bundle_match:
            intent["bundle_id"] = bundle_match.group(0).upper()
        
        quote_match = re.search(r'Q-[A-Z0-9]+', message, re.IGNORECASE)
        if quote_match:
            intent["quote_id"] = quote_match.group(0).upper()
        
        # Extract option number (option 1, option 2, first, second, etc.)
        option_match = re.search(r'option\s*(\d+)|(\d+)(?:st|nd|rd|th)\s*option|(?:first|1st)\s*(?:option|one)?|(?:second|2nd)\s*(?:option|one)?|(?:third|3rd)\s*(?:option|one)?', msg_lower)
        if option_match:
            if option_match.group(1):
                intent["option_number"] = int(option_match.group(1))
            elif option_match.group(2):
                intent["option_number"] = int(option_match.group(2))
            elif 'first' in msg_lower or '1st' in msg_lower:
                intent["option_number"] = 1
            elif 'second' in msg_lower or '2nd' in msg_lower:
                intent["option_number"] = 2
            elif 'third' in msg_lower or '3rd' in msg_lower:
                intent["option_number"] = 3
        
        return intent

    def _merge_intent(self, new_intent: Dict) -> Dict:
        """Merge new intent with cached intent. Journey 2: Refine without starting over"""
        merged = self._intent_cache.copy()
        
        # Handle action:
        # - If new action is explicit, use it
        # - If no new action but adding preferences (refinement), keep search action
        # - Otherwise, use None (will trigger default behavior)
        if new_intent.get("action"):
            merged["action"] = new_intent["action"]
        elif new_intent.get("preferences") and merged.get("destination"):
            # Refinement case: adding preferences to existing search
            merged["action"] = "search"
        else:
            merged["action"] = new_intent.get("action")
        
        for key, value in new_intent.items():
            if key == "action":
                continue  # Already handled above
            if value is not None and (value or key == "preferences"):
                if key == "preferences" and merged.get(key):
                    merged[key] = list(set(merged[key] + value))
                else:
                    merged[key] = value
        
        self._intent_cache = merged
        return merged

    def _get_bundle_id_from_option(self, option_num: int) -> Optional[str]:
        """Get bundle_id from option number (1-indexed)"""
        bundles = self.tools._user_bundles_cache.get(self.user_id, [])
        if bundles and 1 <= option_num <= len(bundles):
            return bundles[option_num - 1].bundle_id
        return None

    def _execute_intent(self, intent: Dict, message: str) -> ChatResponse:
        """Execute based on intent"""
        action = intent.get("action", "search")
        
        if action == "search" or (not action and intent.get("destination")):
            # Check if this is a refinement (has previous bundles and adding new preferences)
            is_refinement = bool(self._previous_bundles) and bool(intent.get("preferences"))
            new_prefs = [p for p in intent.get("preferences", []) if p not in self._previous_preferences]
            
            bundles = self.tools.search_bundles(
                destination=intent.get("destination", "Mumbai"),
                origin=intent.get("origin"),
                budget=intent.get("budget"),
                preferences=intent.get("preferences")
            )
            if bundles:
                # Build response message
                if is_refinement and new_prefs:
                    msg = f"✨ **Refined with: {', '.join(new_prefs)}**\n\n"
                    
                    # Calculate price changes
                    if self._previous_bundles:
                        old_avg = sum(b.total_price for b in self._previous_bundles) / len(self._previous_bundles)
                        new_avg = sum(b.total_price for b in bundles) / len(bundles)
                        price_diff = new_avg - old_avg
                        if abs(price_diff) > 10:
                            if price_diff > 0:
                                msg += f"📈 Average price: +${price_diff:.0f} (for {', '.join(new_prefs)})\n\n"
                            else:
                                msg += f"📉 Average price: -${abs(price_diff):.0f}\n\n"
                else:
                    msg = f"I found {len(bundles)} great options for you:\n\n"
                
                for i, b in enumerate(bundles, 1):
                    msg += f"{i}. **{b.flight.origin}→{b.flight.destination}** + {b.hotel.name}\n"
                    msg += f"   Total: ${b.total_price:.2f} | Fit Score: {b.fit_score}/100\n"
                    msg += f"   {b.why_this}\n\n"
                
                # Save for next refinement comparison
                self._previous_bundles = bundles
                self._previous_preferences = intent.get("preferences", []).copy()
                
                return ChatResponse(message=msg, bundles=bundles, intent=intent)
            return ChatResponse(message="Sorry, I couldn't find matching options. Try a different destination.", intent=intent)
        
        elif action == "watch":
            bundle_id = intent.get("bundle_id")
            option_num = intent.get("option_number")
            
            # Try to get bundle_id from option number
            if not bundle_id and option_num:
                bundle_id = self._get_bundle_id_from_option(option_num)
            
            # Default to first option if user just says "watch" with previous results
            if not bundle_id:
                bundle_id = self._get_bundle_id_from_option(1)
            
            if not bundle_id:
                return ChatResponse(message="Please search for trips first, then I can watch the price for you.", intent=intent)
            
            price_threshold = intent.get("budget")  # Use budget as threshold if specified
            watch = self.tools.watch_creator(bundle_id, price_threshold=price_threshold)
            msg = f"✅ Watch created! ID: {watch.watch_id}\n"
            msg += f"Watching: {watch.listing_name}\n"
            msg += f"Current price: ${watch.current_price:.2f}\n"
            if watch.price_threshold:
                msg += f"Alert when: price drops below ${watch.price_threshold:.2f}"
            return ChatResponse(message=msg, watch=watch, intent=intent)
        
        elif action == "quote":
            bundle_id = intent.get("bundle_id")
            option_num = intent.get("option_number")
            
            if not bundle_id and option_num:
                bundle_id = self._get_bundle_id_from_option(option_num)
            if not bundle_id:
                bundle_id = self._get_bundle_id_from_option(1)
            
            if not bundle_id:
                return ChatResponse(message="Please search for trips first, then I can generate a quote.", intent=intent)
            
            quote = self.tools.quote_generator(bundle_id)
            msg = f"**Quote {quote.quote_id}**\n\n"
            msg += f"Flight: ${quote.breakdown.flight_base:.2f} + ${quote.breakdown.flight_taxes:.2f} taxes\n"
            msg += f"Hotel: ${quote.breakdown.hotel_base:.2f} + ${quote.breakdown.hotel_taxes:.2f} taxes\n"
            msg += f"**Grand Total: ${quote.breakdown.grand_total:.2f}**\n\n"
            msg += f"Fare Class: {quote.breakdown.fare_class}\n"
            msg += f"Baggage: {quote.breakdown.baggage}\n"
            msg += f"Cancellation: {quote.breakdown.cancellation_policy}"
            return ChatResponse(message=msg, quote=quote, intent=intent)
        
        elif action == "confirm":
            quote_id = intent.get("quote_id")
            # Try to get latest quote if not specified
            if not quote_id and self.tools._quotes_cache:
                quote_id = list(self.tools._quotes_cache.keys())[-1] if self.tools._quotes_cache else None
            
            if not quote_id:
                return ChatResponse(message="Please get a quote first, then you can confirm the booking.", intent=intent)
            result = self.tools.booking_confirmer(quote_id)
            return ChatResponse(message=result["message"], booking_reference=result["booking_reference"], intent=intent)
        
        elif action == "analyze":
            bundle_id = intent.get("bundle_id")
            option_num = intent.get("option_number")
            
            if not bundle_id and option_num:
                bundle_id = self._get_bundle_id_from_option(option_num)
            if not bundle_id:
                bundle_id = self._get_bundle_id_from_option(1)
            
            if not bundle_id:
                return ChatResponse(message="Please search for trips first, then I can analyze the price.", intent=intent)
            
            analysis = self.tools.price_analyzer(bundle_id)
            
            # Build detailed response like assignment example
            flight = analysis['flight']
            hotel = analysis['hotel']
            overall = analysis['overall']
            
            msg = f"**📊 Price Analysis**\n\n"
            msg += f"✅ **Verdict: {overall['recommendation']}**\n\n"
            
            # Flight analysis
            msg += f"**Flight:** ${flight['price']:.0f}\n"
            msg += f"   • {flight['discount_percent']:.0f}% below 30-day average (${flight['avg_30d_price']:.0f})\n"
            msg += f"   • Deal score: {flight['deal_score']}/100\n\n"
            
            # Hotel analysis
            msg += f"**Hotel:** ${hotel['price_per_night']:.0f}/night ({hotel['star_rating']}-star)\n"
            msg += f"   • {hotel['discount_percent']:.0f}% below 30-day average (${hotel['avg_30d_price']:.0f})\n"
            msg += f"   • Similar {hotel['star_rating']}-star hotels nearby: ${hotel['similar_hotels_range'][0]:.0f}-${hotel['similar_hotels_range'][1]:.0f}/night\n\n"
            
            msg += f"💡 This price is **{overall['avg_discount_percent']:.0f}% below average** - {overall['recommendation'].lower()}!"
            
            return ChatResponse(message=msg, intent=intent)
        
        elif action == "policy":
            bundle_id = intent.get("bundle_id")
            option_num = intent.get("option_number")
            
            if not bundle_id and option_num:
                bundle_id = self._get_bundle_id_from_option(option_num)
            if not bundle_id:
                bundle_id = self._get_bundle_id_from_option(1)
            
            if not bundle_id:
                return ChatResponse(message="Please search for trips first, then I can show policies.", intent=intent)
            
            # Determine which policy type based on message
            msg_lower = message.lower()
            if "pet" in msg_lower:
                policy_type = "pet"
            elif "cancel" in msg_lower or "refund" in msg_lower:
                policy_type = "cancellation"
            elif "bag" in msg_lower or "luggage" in msg_lower:
                policy_type = "baggage"
            else:
                policy_type = "all"
            
            policies = self.tools.policy_lookup(bundle_id, policy_type)
            
            if policy_type == "all":
                msg = "**📋 Policies:**\n\n"
                for ptype, text in policies.items():
                    msg += f"• **{ptype.title()}:** {text}\n"
            else:
                msg = f"**{policy_type.title()} Policy:**\n\n"
                if policy_type in policies:
                    msg += policies[policy_type]
                else:
                    msg += "Policy information not available."
            
            return ChatResponse(message=msg, intent=intent)
        
        return ChatResponse(message="I can help you search for trips, get quotes, or set up price watches. What would you like to do?", intent=intent)


# ============================================
# Factory function
# ============================================

def create_agent(user_id: str = "anonymous", session_id: str = None) -> ConciergeAgent:
    """Create a new ConciergeAgent instance"""
    return ConciergeAgent(user_id=user_id, session_id=session_id)


# ============================================
# API Compatibility Layer
# ============================================

def _convert_bundles_to_api_format(bundles: Optional[List[Bundle]]) -> List[Dict[str, Any]]:
    """Convert Bundle objects to API-expected format"""
    if not bundles:
        return []
    
    result = []
    for b in bundles:
        result.append({
            "bundle_id": b.bundle_id,
            "name": f"{b.hotel.name} + {b.flight.airline} Flight",
            "total_price": b.total_price,
            "deal_score": b.deal_score,
            "fit_score": b.fit_score,
            "savings": b.savings,
            "explanation": {
                "why_this": b.why_this,
                "what_to_watch": b.what_to_watch
            },
            "flight": b.flight.model_dump(),
            "hotel": b.hotel.model_dump()
        })
    return result


def _determine_response_type(response: ChatResponse) -> str:
    """Determine response type for API"""
    if response.needs_clarification:
        return "clarification"
    if response.bundles:
        return "recommendations"
    if response.quote:
        return "quote"
    if response.watch:
        return "watch_created"
    if response.booking_reference:
        return "booking"
    return "response"


async def process_chat(
    query: str,
    user_id: str = "anonymous",
    session_id: Optional[str] = None,
    context: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Process chat request - API compatibility function.
    This is called by api/chat.py as fallback.
    
    Args:
        query: User's message
        user_id: User identifier
        session_id: Session ID for context
        context: Additional context
    
    Returns:
        Dict with response, bundles, session_id, etc.
    """
    try:
        # Create agent for this request
        agent = ConciergeAgent(user_id=user_id, session_id=session_id)
        
        # Process the message (synchronous)
        response = agent.chat(query, context)
        
        # Convert to API format
        return {
            "response": response.message,
            "session_id": agent.session_id,
            "user_id": user_id,
            "type": _determine_response_type(response),
            "confidence": 0.9,
            "bundles": _convert_bundles_to_api_format(response.bundles),
            "parsed_intent": response.intent or {},
            "changes": None,
            "tool_used": response.intent.get("action") if response.intent else None,
            "quote": response.quote.model_dump() if response.quote else None,
            "watch": response.watch.model_dump() if response.watch else None,
            "booking_reference": response.booking_reference
        }
        
    except Exception as e:
        logger.error(f"process_chat error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "response": f"I encountered an error processing your request. Please try again.",
            "session_id": session_id,
            "user_id": user_id,
            "type": "error",
            "confidence": 0.0,
            "bundles": [],
            "parsed_intent": {},
            "changes": None,
            "tool_used": None
        }


class ConciergeAgentWrapper:
    """
    Wrapper class that provides async process_message method.
    This is what api/chat.py imports as concierge_agent.
    """
    
    def __init__(self):
        self._agents: Dict[str, ConciergeAgent] = {}
        self._session_to_key: Dict[str, str] = {}  # Map session_id to agent key
    
    def _get_or_create_agent(self, user_id: str, session_id: Optional[str]) -> ConciergeAgent:
        """Get existing agent or create new one"""
        # If we have a session_id, try to find existing agent
        if session_id and session_id in self._session_to_key:
            key = self._session_to_key[session_id]
            if key in self._agents:
                return self._agents[key]
        
        # Create new agent
        key = f"{user_id}:{session_id or uuid.uuid4().hex[:8]}"
        if key not in self._agents:
            agent = ConciergeAgent(user_id=user_id, session_id=session_id)
            self._agents[key] = agent
            # Register the session_id for future lookups
            self._session_to_key[agent.session_id] = key
        
        return self._agents[key]
    
    async def process_message(
        self,
        user_id: str,
        query: str,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a chat message - async API expected by api/chat.py
        
        Args:
            user_id: User identifier
            query: User's message
            session_id: Session ID for context
        
        Returns:
            Dict with response, bundles, session_id, etc.
        """
        try:
            agent = self._get_or_create_agent(user_id, session_id)
            
            # Process the message (synchronous internally)
            response = agent.chat(query)
            
            # Convert to API format
            return {
                "response": response.message,
                "session_id": agent.session_id,
                "user_id": user_id,
                "type": _determine_response_type(response),
                "confidence": 0.9,
                "bundles": _convert_bundles_to_api_format(response.bundles),
                "parsed_intent": response.intent or {},
                "changes": None,
                "tool_used": response.intent.get("action") if response.intent else None,
                "quote": response.quote.model_dump() if response.quote else None,
                "watch": response.watch.model_dump() if response.watch else None,
                "booking_reference": response.booking_reference
            }
            
        except Exception as e:
            logger.error(f"process_message error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "response": "I encountered an error processing your request. Please try again.",
                "session_id": session_id,
                "user_id": user_id,
                "type": "error",
                "confidence": 0.0,
                "bundles": [],
                "parsed_intent": {},
                "changes": None,
                "tool_used": None
            }


# Default instance for import compatibility
# This is what api/chat.py imports: from agents.concierge_agent import concierge_agent, process_chat
concierge_agent = ConciergeAgentWrapper()
