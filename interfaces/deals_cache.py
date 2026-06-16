# interfaces/deals_cache.py
"""
Deals Cache for storing and retrieving processed deals.
Now reads from SQLite (SQLModel) - Assignment requirement.
Falls back to MongoDB if SQLite not available.
"""

import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from loguru import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    from pymongo import MongoClient
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False

# SQLModel imports - Primary data source (Assignment requirement)
try:
    from sqlmodel import Session, select
    from models.database import get_engine, init_db
    from models.deals_entities import FlightDeal, HotelDeal
    SQLMODEL_AVAILABLE = True
except ImportError:
    SQLMODEL_AVAILABLE = False
    FlightDeal = None  # Define as None to avoid NameError in type hints
    HotelDeal = None
    logger.warning("SQLModel not available, will use MongoDB as fallback")


@dataclass
class Deal:
    """A scored and tagged deal"""
    deal_id: str
    listing_type: str  # "flight", "hotel"
    listing_id: str

    # Basic info
    name: str
    origin: Optional[str] = None  # For flights
    destination: str = ""

    # Pricing
    current_price: float = 0
    original_price: float = 0
    avg_30d_price: float = 0
    discount_percent: float = 0

    # Availability
    availability: int = 0  # Rooms/seats left

    # Scores
    deal_score: int = 0  # 0-100

    # Tags
    tags: List[str] = field(default_factory=list)

    # Timestamps
    discovered_at: str = ""
    expires_at: Optional[str] = None
    
    # Promo info
    has_promo: bool = False
    promo_end_date: Optional[str] = None

    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Deal':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DealsCache:
    """
    Cache for storing and querying deals.
    Primary: SQLite via SQLModel (Assignment requirement)
    Fallback: MongoDB
    """

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379,
                 mongo_uri: str = "mongodb://mongodb:27017", mongo_db: str = "kayak_doc",
                 ttl_hours: int = 24):
        self.ttl_seconds = ttl_hours * 3600
        self.redis_client = None
        self.mongo_client = None
        self.mongo_db = None
        self.use_sqlite = SQLMODEL_AVAILABLE

        # In-memory storage
        self._deals: Dict[str, Deal] = {}
        self._by_destination: Dict[str, List[str]] = {}
        self._by_type: Dict[str, List[str]] = {}
        self._by_tag: Dict[str, List[str]] = {}

        # Connect to Redis (for caching)
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info(f"DealsCache connected to Redis")
            except Exception as e:
                logger.warning(f"DealsCache Redis connection failed: {e}")
                self.redis_client = None

        # Connect to MongoDB (fallback)
        if MONGO_AVAILABLE:
            try:
                self.mongo_client = MongoClient(mongo_uri)
                self.mongo_db = self.mongo_client[mongo_db]
                self.mongo_db.list_collection_names()
                logger.info(f"DealsCache connected to MongoDB: {mongo_uri}/{mongo_db}")
            except Exception as e:
                logger.warning(f"DealsCache MongoDB connection failed: {e}")
                self.mongo_client = None
                self.mongo_db = None

        # Load deals - prefer SQLite (Assignment requirement)
        if self.use_sqlite:
            logger.info("Loading deals from SQLite (SQLModel) - Assignment requirement")
            self._load_deals_from_sqlite()
        else:
            logger.info("Loading deals from MongoDB (SQLite not available)")
            self._load_deals_from_mongo()

    def _load_deals_from_sqlite(self):
        """Load flights and hotels from SQLite and convert to deals"""
        try:
            # Initialize database first (create tables if not exist)
            from models.database import init_db
            init_db()
            
            engine = get_engine()
            
            with Session(engine) as session:
                # Load flights
                flights = session.exec(select(FlightDeal)).all()
                logger.info(f"Loading {len(flights)} flights from SQLite")
                
                for flight in flights:
                    deal = self._sqlite_flight_to_deal(flight)
                    if deal:
                        self.add_deal(deal)
                
                # Load hotels
                hotels = session.exec(select(HotelDeal)).all()
                logger.info(f"Loading {len(hotels)} hotels from SQLite")
                
                for hotel in hotels:
                    deal = self._sqlite_hotel_to_deal(hotel)
                    if deal:
                        self.add_deal(deal)
            
            logger.info(f"Loaded {len(self._deals)} deals from SQLite")
            
        except Exception as e:
            logger.error(f"Error loading deals from SQLite: {e}")
            # Fallback to MongoDB
            if self.mongo_db is not None:
                logger.info("Falling back to MongoDB")
                self._load_deals_from_mongo()
            else:
                self._init_sample_deals()

    def _sqlite_flight_to_deal(self, flight) -> Optional[Deal]:
        """Convert SQLModel FlightDeal to Deal"""
        try:
            tags = json.loads(flight.tags) if flight.tags else []
            
            return Deal(
                deal_id=f"flight_{flight.flight_id}",
                listing_type="flight",
                listing_id=flight.flight_id,
                name=f"{flight.origin} → {flight.destination} ({flight.airline})",
                origin=flight.origin,
                destination=flight.destination,
                current_price=flight.price,
                original_price=flight.avg_30d_price,
                avg_30d_price=flight.avg_30d_price,
                discount_percent=flight.discount_percent,
                availability=flight.available_seats,
                deal_score=flight.deal_score,
                tags=tags,
                has_promo=flight.has_promo,
                promo_end_date=flight.promo_end_date,
                discovered_at=datetime.utcnow().isoformat(),
                metadata={
                    "airline": flight.airline,
                    "flight_number": flight.flight_number,
                    "stops": flight.stops,
                    "duration": flight.duration,
                    "class": flight.flight_class,
                    "origin_city": flight.origin_city,
                    "destination_city": flight.destination_city
                }
            )
        except Exception as e:
            logger.error(f"Error converting SQLite flight to deal: {e}")
            return None

    def _sqlite_hotel_to_deal(self, hotel) -> Optional[Deal]:
        """Convert SQLModel HotelDeal to Deal"""
        try:
            tags = json.loads(hotel.tags) if hotel.tags else []
            amenities = json.loads(hotel.amenities) if hotel.amenities else []
            
            return Deal(
                deal_id=f"hotel_{hotel.hotel_id}",
                listing_type="hotel",
                listing_id=hotel.hotel_id,
                name=hotel.name,
                origin=None,
                destination=hotel.city_code,  # Use city_code for matching
                current_price=hotel.price_per_night,
                original_price=hotel.avg_30d_price,
                avg_30d_price=hotel.avg_30d_price,
                discount_percent=hotel.discount_percent,
                availability=hotel.available_rooms,
                deal_score=hotel.deal_score,
                tags=tags,
                has_promo=hotel.has_promo,
                promo_end_date=hotel.promo_end_date,
                discovered_at=datetime.utcnow().isoformat(),
                metadata={
                    "hotel_type": hotel.hotel_type,
                    "star_rating": hotel.star_rating,
                    "city": hotel.city,
                    "city_code": hotel.city_code,
                    "neighbourhood": hotel.neighbourhood,  # Assignment requirement!
                    "amenities": amenities,
                    "rating": hotel.rating,
                    "is_refundable": hotel.is_refundable,
                    "pet_friendly": hotel.pet_friendly,
                    "breakfast_included": hotel.breakfast_included,
                    "near_transit": hotel.near_transit,  # Assignment requirement!
                    "parking_available": hotel.parking_available
                }
            )
        except Exception as e:
            logger.error(f"Error converting SQLite hotel to deal: {e}")
            return None

    def _load_deals_from_mongo(self):
        """Load flights and hotels from MongoDB and convert to deals (fallback)"""
        if self.mongo_db is None:
            logger.warning("MongoDB not available, using sample deals")
            self._init_sample_deals()
            return

        try:
            # Load flights
            flights_collection = self.mongo_db["flights"]
            flights_count = flights_collection.count_documents({})
            logger.info(f"Loading {flights_count} flights from MongoDB")

            for flight in flights_collection.find():
                deal = self._flight_to_deal(flight)
                if deal:
                    self.add_deal(deal)

            # Load hotels
            hotels_collection = self.mongo_db["hotels"]
            hotels_count = hotels_collection.count_documents({})
            logger.info(f"Loading {hotels_count} hotels from MongoDB")

            for hotel in hotels_collection.find():
                deal = self._hotel_to_deal(hotel)
                if deal:
                    self.add_deal(deal)

            logger.info(f"Loaded {len(self._deals)} deals from MongoDB")

        except Exception as e:
            logger.error(f"Error loading deals from MongoDB: {e}")
            self._init_sample_deals()

    def _flight_to_deal(self, flight: Dict) -> Optional[Deal]:
        """Convert MongoDB flight document to Deal"""
        try:
            price = float(flight.get("price", 0))
            avg_30d_price = float(flight.get("avg_30d_price", price * 1.15))
            discount_percent = float(flight.get("discount_percent", 13))
            deal_score = int(flight.get("deal_score", 50))
            available_seats = int(flight.get("available_seats", 50))
            has_promo = flight.get("has_promo", False)
            promo_end_date = flight.get("promo_end_date")

            tags = flight.get("tags", [])
            if isinstance(tags, str):
                tags = json.loads(tags)
            if not tags:
                tags = []
                if flight.get("stops", 0) == 0:
                    tags.append("direct-flight")
                if has_promo:
                    tags.append("promo")

            return Deal(
                deal_id=f"flight_{flight.get('flight_id', '')}",
                listing_type="flight",
                listing_id=flight.get("flight_id", ""),
                name=f"{flight.get('origin', 'XXX')} → {flight.get('destination', 'XXX')} ({flight.get('airline', 'Airline')})",
                origin=flight.get("origin", ""),
                destination=flight.get("destination", ""),
                current_price=price,
                original_price=avg_30d_price,
                avg_30d_price=avg_30d_price,
                discount_percent=discount_percent,
                availability=available_seats,
                deal_score=deal_score,
                tags=tags,
                has_promo=has_promo,
                promo_end_date=promo_end_date,
                discovered_at=datetime.utcnow().isoformat(),
                metadata={
                    "airline": flight.get("airline", ""),
                    "flight_number": flight.get("flight_number", ""),
                    "stops": flight.get("stops", 0),
                    "duration": flight.get("duration", 0),
                    "class": flight.get("class", "Economy"),
                    "origin_city": flight.get("origin_city", ""),
                    "destination_city": flight.get("destination_city", "")
                }
            )
        except Exception as e:
            logger.error(f"Error converting flight to deal: {e}")
            return None

    def _hotel_to_deal(self, hotel: Dict) -> Optional[Deal]:
        """Convert MongoDB hotel document to Deal"""
        try:
            price = float(hotel.get("price_per_night", 0))
            avg_30d_price = float(hotel.get("avg_30d_price", price * 1.15))
            discount_percent = float(hotel.get("discount_percent", 13))
            deal_score = int(hotel.get("deal_score", 50))
            available_rooms = int(hotel.get("available_rooms", 10))
            has_promo = hotel.get("has_promo", False)
            promo_end_date = hotel.get("promo_end_date")

            tags = hotel.get("tags", [])
            if isinstance(tags, str):
                tags = json.loads(tags)

            amenities = hotel.get("amenities", [])
            if isinstance(amenities, str):
                amenities = json.loads(amenities)

            return Deal(
                deal_id=f"hotel_{hotel.get('hotel_id', '')}",
                listing_type="hotel",
                listing_id=hotel.get("hotel_id", ""),
                name=hotel.get("name", "Hotel"),
                origin=None,
                destination=hotel.get("city_code", hotel.get("city", "")),
                current_price=price,
                original_price=avg_30d_price,
                avg_30d_price=avg_30d_price,
                discount_percent=discount_percent,
                availability=available_rooms,
                deal_score=deal_score,
                tags=tags,
                has_promo=has_promo,
                promo_end_date=promo_end_date,
                discovered_at=datetime.utcnow().isoformat(),
                metadata={
                    "hotel_type": hotel.get("hotel_type", "Hotel"),
                    "star_rating": hotel.get("star_rating", 3),
                    "city": hotel.get("city", ""),
                    "city_code": hotel.get("city_code", ""),
                    "neighbourhood": hotel.get("neighbourhood", ""),
                    "amenities": amenities,
                    "rating": hotel.get("rating", 4.0),
                    "is_refundable": hotel.get("is_refundable", True),
                    "pet_friendly": hotel.get("pet_friendly", False),
                    "breakfast_included": hotel.get("breakfast_included", False),
                    "near_transit": hotel.get("near_transit", False),
                    "parking_available": hotel.get("parking_available", False)
                }
            )
        except Exception as e:
            logger.error(f"Error converting hotel to deal: {e}")
            return None

    def _init_sample_deals(self):
        """Initialize with sample deals if no database available"""
        logger.warning("Initializing with sample deals (no database)")
        
        sample_flights = [
            Deal(
                deal_id="flight_sample_1",
                listing_type="flight",
                listing_id="FL_SAMPLE_1",
                name="DEL → BOM (Sample Airline)",
                origin="DEL",
                destination="BOM",
                current_price=5000,
                avg_30d_price=6000,
                discount_percent=17,
                availability=20,
                deal_score=75,
                tags=["direct-flight"],
                metadata={"airline": "Sample Airline", "stops": 0, "duration": 2.0}
            )
        ]
        
        sample_hotels = [
            Deal(
                deal_id="hotel_sample_1",
                listing_type="hotel",
                listing_id="HT_SAMPLE_1",
                name="Sample Hotel - Mumbai",
                destination="BOM",
                current_price=100,
                avg_30d_price=120,
                discount_percent=17,
                availability=5,
                deal_score=70,
                tags=["wifi", "breakfast"],
                metadata={
                    "city": "Mumbai",
                    "city_code": "BOM",
                    "neighbourhood": "Bandra",
                    "star_rating": 4
                }
            )
        ]
        
        for deal in sample_flights + sample_hotels:
            self.add_deal(deal)

    def _get_key(self, deal_id: str) -> str:
        """Get Redis key for deal"""
        return f"deal:{deal_id}"

    def add_deal(self, deal: Deal):
        """Add a deal to cache"""
        # Add to memory
        self._deals[deal.deal_id] = deal

        # Index by destination
        if deal.destination:
            if deal.destination not in self._by_destination:
                self._by_destination[deal.destination] = []
            if deal.deal_id not in self._by_destination[deal.destination]:
                self._by_destination[deal.destination].append(deal.deal_id)

        # Index by type
        if deal.listing_type not in self._by_type:
            self._by_type[deal.listing_type] = []
        if deal.deal_id not in self._by_type[deal.listing_type]:
            self._by_type[deal.listing_type].append(deal.deal_id)

        # Index by tags
        for tag in deal.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            if deal.deal_id not in self._by_tag[tag]:
                self._by_tag[tag].append(deal.deal_id)

        # Add to Redis
        if self.redis_client:
            try:
                self.redis_client.setex(
                    self._get_key(deal.deal_id),
                    self.ttl_seconds,
                    json.dumps(deal.to_dict())
                )
                if deal.destination:
                    self.redis_client.sadd(f"deals:dest:{deal.destination}", deal.deal_id)
                self.redis_client.sadd(f"deals:type:{deal.listing_type}", deal.deal_id)
                for tag in deal.tags:
                    self.redis_client.sadd(f"deals:tag:{tag}", deal.deal_id)
            except Exception as e:
                logger.error(f"Redis add deal error: {e}")

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        """Get a deal by ID"""
        if deal_id in self._deals:
            return self._deals[deal_id]

        if self.redis_client:
            try:
                data = self.redis_client.get(self._get_key(deal_id))
                if data:
                    return Deal.from_dict(json.loads(data))
            except Exception as e:
                logger.error(f"Redis get deal error: {e}")

        return None

    def get_deals_by_type(self, listing_type: str) -> List[Deal]:
        """Get all deals of a type"""
        deal_ids = self._by_type.get(listing_type, [])
        return [self._deals[did] for did in deal_ids if did in self._deals]

    def get_best_deals(self, limit: int = 10) -> List[Deal]:
        """Get top deals by score"""
        all_deals = list(self._deals.values())
        all_deals.sort(key=lambda d: d.deal_score, reverse=True)
        return all_deals[:limit]

    def search_deals(
        self,
        destination: Optional[str] = None,
        origin: Optional[str] = None,
        listing_type: Optional[str] = None,
        max_price: Optional[float] = None,
        min_score: int = 0,
        tags: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Deal]:
        """Search deals with filters"""
        candidates = set(self._deals.keys())

        # Filter by destination
        if destination:
            dest_deals = set(self._by_destination.get(destination, []))
            candidates = candidates.intersection(dest_deals) if dest_deals else set()

        # Filter by type
        if listing_type:
            type_deals = set(self._by_type.get(listing_type, []))
            candidates = candidates.intersection(type_deals)

        # Filter by tags
        if tags:
            for tag in tags:
                tag_deals = set(self._by_tag.get(tag, []))
                if tag_deals:
                    candidates = candidates.intersection(tag_deals)

        # Get deal objects and apply remaining filters
        results = []
        for deal_id in candidates:
            deal = self._deals.get(deal_id)
            if not deal:
                continue

            # Filter by origin (for flights)
            if origin and deal.listing_type == "flight":
                if deal.origin != origin:
                    continue

            # Filter by price
            if max_price and deal.current_price > max_price:
                continue

            # Filter by score
            if deal.deal_score < min_score:
                continue

            results.append(deal)

        # Sort by deal score
        results.sort(key=lambda d: d.deal_score, reverse=True)
        return results[:limit]

    def get_deals_for_bundle(
        self,
        destination: str,
        origin: Optional[str] = None,
        max_flight_price: Optional[float] = None,
        max_hotel_price: Optional[float] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, List[Deal]]:
        """
        Get matching flights and hotels for bundle creation.
        Returns diverse options: Best Value, Best Deal, Best Quality
        """
        # Get all matching flights
        all_flights = self.search_deals(
            destination=destination,
            origin=origin,
            listing_type="flight",
            max_price=max_flight_price,
            tags=[t for t in (tags or []) if t in ["direct-flight", "no-redeye"]],
            limit=50
        )
        
        # Get all matching hotels
        all_hotels = self.search_deals(
            destination=destination,
            listing_type="hotel",
            max_price=max_hotel_price,
            tags=[t for t in (tags or []) if t not in ["direct-flight", "no-redeye"]],
            limit=50
        )
        
        # If no hotels for destination, get any hotels with tags
        if not all_hotels:
            hotel_tags = [t for t in (tags or []) if t not in ["direct-flight", "no-redeye"]]
            all_hotels = self.search_deals(
                listing_type="hotel",
                max_price=max_hotel_price,
                tags=hotel_tags if hotel_tags else None,
                limit=50
            )
        
        # Select diverse flights
        flights = self._select_diverse(all_flights, "flight")
        
        # Select diverse hotels
        hotels = self._select_diverse(all_hotels, "hotel")
        
        return {"flights": flights, "hotels": hotels}
    
    def _select_diverse(self, deals: List[Deal], deal_type: str) -> List[Deal]:
        """
        Select 3 diverse options:
        1. Best Value (lowest price)
        2. Best Deal (highest deal_score)
        3. Best Quality (highest rating/stars)
        """
        if not deals:
            return []
        
        if len(deals) <= 3:
            return deals
        
        selected = []
        selected_ids = set()
        
        # 1. Best Value - lowest price
        by_price = sorted(deals, key=lambda d: d.current_price)
        for deal in by_price:
            if deal.deal_id not in selected_ids:
                selected.append(deal)
                selected_ids.add(deal.deal_id)
                break
        
        # 2. Best Deal - highest deal_score
        by_score = sorted(deals, key=lambda d: d.deal_score, reverse=True)
        for deal in by_score:
            if deal.deal_id not in selected_ids:
                selected.append(deal)
                selected_ids.add(deal.deal_id)
                break
        
        # 3. Best Quality
        if deal_type == "hotel":
            by_quality = sorted(deals, key=lambda d: (
                d.metadata.get("star_rating", 0),
                d.metadata.get("rating", 0)
            ), reverse=True)
        else:
            by_quality = sorted(deals, key=lambda d: (
                0 if d.metadata.get("stops", 1) == 0 else 1,
                d.metadata.get("duration", 99)
            ))
        
        for deal in by_quality:
            if deal.deal_id not in selected_ids:
                selected.append(deal)
                selected_ids.add(deal.deal_id)
                break
        
        # Fill remaining
        if len(selected) < 3:
            for deal in by_price:
                if deal.deal_id not in selected_ids:
                    selected.append(deal)
                    selected_ids.add(deal.deal_id)
                    if len(selected) >= 3:
                        break
        
        return selected[:3]

    def remove_deal(self, deal_id: str):
        """Remove a deal from cache"""
        deal = self._deals.get(deal_id)
        if not deal:
            return

        if self.redis_client:
            try:
                self.redis_client.delete(self._get_key(deal_id))
                self.redis_client.srem(f"deals:dest:{deal.destination}", deal_id)
                self.redis_client.srem(f"deals:type:{deal.listing_type}", deal_id)
                for tag in deal.tags:
                    self.redis_client.srem(f"deals:tag:{tag}", deal_id)
            except Exception as e:
                logger.error(f"Redis remove deal error: {e}")

        if deal_id in self._deals:
            del self._deals[deal_id]

        if deal.destination in self._by_destination:
            if deal_id in self._by_destination[deal.destination]:
                self._by_destination[deal.destination].remove(deal_id)

        if deal.listing_type in self._by_type:
            if deal_id in self._by_type[deal.listing_type]:
                self._by_type[deal.listing_type].remove(deal_id)

        for tag in deal.tags:
            if tag in self._by_tag and deal_id in self._by_tag[tag]:
                self._by_tag[tag].remove(deal_id)

    def update_deal_price(self, deal_id: str, new_price: float) -> Optional[Deal]:
        """Update a deal's price"""
        deal = self.get_deal(deal_id)
        if not deal:
            return None

        old_price = deal.current_price
        deal.current_price = new_price

        if deal.original_price > 0:
            deal.discount_percent = ((deal.original_price - new_price) / deal.original_price) * 100

        self.add_deal(deal)
        logger.info(f"Updated deal {deal_id} price: ${old_price} -> ${new_price}")
        return deal

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "total_deals": len(self._deals),
            "by_type": {k: len(v) for k, v in self._by_type.items()},
            "by_destination": {k: len(v) for k, v in self._by_destination.items()},
            "top_tags": {k: len(v) for k, v in sorted(self._by_tag.items(), key=lambda x: -len(x[1]))[:10]},
            "data_source": "SQLite" if self.use_sqlite else "MongoDB"
        }


# ============================================
# Global Instance
# ============================================

try:
    from config import settings
    deals_cache = DealsCache(
        redis_host=settings.REDIS_HOST,
        redis_port=settings.REDIS_PORT,
        mongo_uri=getattr(settings, 'MONGO_URI', 'mongodb://mongodb:27017'),
        mongo_db=getattr(settings, 'MONGO_DB', 'kayak_doc')
    )
except Exception as e:
    logger.warning(f"Could not load settings, using defaults: {e}")
    deals_cache = DealsCache()


# ============================================
# Convenience Functions
# ============================================

def search_deals(
    destination: Optional[str] = None,
    origin: Optional[str] = None,
    listing_type: Optional[str] = None,
    max_price: Optional[float] = None,
    min_score: int = 0,
    tags: Optional[List[str]] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Search deals and return as dicts"""
    deals = deals_cache.search_deals(
        destination=destination,
        origin=origin,
        listing_type=listing_type,
        max_price=max_price,
        min_score=min_score,
        tags=tags,
        limit=limit
    )
    return [d.to_dict() for d in deals]


def get_deals_for_bundle(destination: str, **kwargs) -> Dict[str, List[Dict]]:
    """Get deals for bundle creation"""
    result = deals_cache.get_deals_for_bundle(destination, **kwargs)
    return {
        "flights": [d.to_dict() for d in result["flights"]],
        "hotels": [d.to_dict() for d in result["hotels"]]
    }


def get_best_deals(limit: int = 10) -> List[Dict[str, Any]]:
    """Get best deals as dicts"""
    deals = deals_cache.get_best_deals(limit)
    return [d.to_dict() for d in deals]
