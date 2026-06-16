# ai/models/deals_entities.py
"""
SQLModel entities for Deals (Flights, Hotels, Airports).
Satisfies assignment requirement: "Persist normalized rows with SQLModel"

Fields based on assignment requirements:
- Hotels: listing_id, date, price, availability, amenities, neighbourhood, avg_30d_price, tags
- Flights: origin, dest, airline, stops, duration, price, avg_30d_price, promo, seats_left
- Airports: IATA, coords
"""

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Airport(SQLModel, table=True):
    """
    Airport reference table.
    From Airports/Routes dataset: IATA + coords for location logic.
    """
    __tablename__ = "airports"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    iata: str = Field(index=True, unique=True, max_length=3)
    icao: Optional[str] = Field(default=None, max_length=4)
    name: str = Field(max_length=128)
    city: str = Field(index=True, max_length=64)
    country: str = Field(max_length=64)
    country_code: Optional[str] = Field(default=None, max_length=2)
    timezone: Optional[str] = Field(default=None, max_length=64)
    latitude: float = Field(default=0.0)
    longitude: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FlightDeal(SQLModel, table=True):
    """
    Flight deal entity.
    Assignment requirement: origin, dest, airline, stops, duration, price,
    simulate time series (avg_30d_price + promo dips + seats_left scarcity)
    """
    __tablename__ = "flight_deals"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    flight_id: str = Field(index=True, unique=True, max_length=20)
    
    # Route info
    origin: str = Field(index=True, max_length=3)  # IATA code
    origin_city: str = Field(max_length=64)
    destination: str = Field(index=True, max_length=3)  # IATA code
    destination_city: str = Field(max_length=64)
    
    # Flight details
    airline: str = Field(max_length=64)
    flight_number: Optional[str] = Field(default=None, max_length=20)
    departure_time: Optional[str] = Field(default=None, max_length=20)
    arrival_time: Optional[str] = Field(default=None, max_length=20)
    duration: float = Field(default=0.0)  # hours
    stops: int = Field(default=0)
    flight_class: str = Field(default="Economy", max_length=20)
    
    # Pricing - Assignment: simulate time series
    price: float = Field(index=True)
    avg_30d_price: float = Field(default=0.0)  # For deal calculation
    discount_percent: float = Field(default=0.0)
    
    # Availability - Assignment: seats_left scarcity
    available_seats: int = Field(default=50)
    
    # Promo - Assignment: random promo dips -10% to -25%
    has_promo: bool = Field(default=False)
    promo_end_date: Optional[str] = Field(default=None)
    
    # Deal score (calculated)
    deal_score: int = Field(default=50, index=True)
    
    # Tags (JSON string)
    tags: str = Field(default="[]")  # e.g., '["direct-flight", "promo"]'
    
    # Metadata
    rating: float = Field(default=4.0)
    days_left: int = Field(default=30)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HotelDeal(SQLModel, table=True):
    """
    Hotel deal entity.
    Assignment requirement: listing_id, date, price, availability, amenities, neighbourhood,
    avg_30d_price, deal flag (>=15% below avg), Limited availability (<5), tags
    """
    __tablename__ = "hotel_deals"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    hotel_id: str = Field(index=True, unique=True, max_length=20)
    
    # Basic info
    name: str = Field(max_length=128)
    hotel_type: str = Field(default="Hotel", max_length=32)
    
    # Location - Assignment: neighbourhood required
    city: str = Field(index=True, max_length=64)  # Mapped to Indian cities
    city_code: str = Field(max_length=3)  # IATA code for matching
    country: str = Field(max_length=64)
    neighbourhood: str = Field(max_length=128)  # Assignment requirement!
    
    # Pricing - Assignment: avg_30d_price for deal calculation
    price_per_night: float = Field(index=True)
    avg_30d_price: float = Field(default=0.0)
    discount_percent: float = Field(default=0.0)
    
    # Availability - Assignment: Limited availability (<5)
    available_rooms: int = Field(default=10)
    
    # Promo
    has_promo: bool = Field(default=False)
    promo_end_date: Optional[str] = Field(default=None)
    
    # Deal score (calculated)
    deal_score: int = Field(default=50, index=True)
    
    # Hotel details
    star_rating: int = Field(default=3)
    room_type: str = Field(default="Standard", max_length=32)
    meal_plan: Optional[str] = Field(default=None, max_length=10)
    
    # Amenities and tags (JSON strings)
    amenities: str = Field(default="[]")  # e.g., '["wifi", "pool", "breakfast"]'
    tags: str = Field(default="[]")  # Assignment: Pet-friendly, Near transit, Breakfast
    
    # Policies
    is_refundable: bool = Field(default=True)
    pet_friendly: bool = Field(default=False)
    parking_available: bool = Field(default=False)
    breakfast_included: bool = Field(default=False)
    near_transit: bool = Field(default=False)  # Assignment requirement!
    
    # Ratings
    rating: float = Field(default=4.0)
    total_reviews: int = Field(default=100)
    
    # Timestamps
    listing_date: Optional[str] = Field(default=None)  # Assignment: date field
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
