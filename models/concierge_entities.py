# ai/models/concierge_entities.py
"""
SQLModel entities for Concierge Agent persistence.
Satisfies assignment requirement: "Persist normalized entities with SQLModel (SQLite locally)"

These entities store:
- BundleRecord: Search results (flight + hotel bundles)
- QuoteRecord: Generated quotes
- BookingRecord: Confirmed bookings
- WatchRecord: Price/inventory watches
"""

from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class BundleRecord(SQLModel, table=True):
    """
    Persisted bundle (flight + hotel combination).
    Created when user searches for travel options.
    """
    __tablename__ = "bundles"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    bundle_id: str = Field(index=True, unique=True, max_length=64)
    
    # User context
    user_id: str = Field(index=True, max_length=64)
    session_id: str = Field(max_length=64)
    
    # Search parameters
    origin: str = Field(max_length=3)
    destination: str = Field(max_length=3)
    date_from: Optional[str] = Field(default=None, max_length=10)
    date_to: Optional[str] = Field(default=None, max_length=10)
    budget: Optional[float] = Field(default=None)
    
    # Flight reference
    flight_id: str = Field(max_length=20)
    flight_price: float = Field(default=0.0)
    
    # Hotel reference
    hotel_id: str = Field(max_length=20)
    hotel_price: float = Field(default=0.0)
    
    # Bundle pricing
    total_price: float = Field(index=True)
    savings: float = Field(default=0.0)
    
    # Scores
    deal_score: int = Field(default=50)
    fit_score: int = Field(default=50)
    
    # Explanation (JSON)
    explanation_json: str = Field(default="{}")  # {"why_this": "...", "what_to_watch": "..."}
    
    # Full bundle data (JSON) - for quick retrieval
    bundle_data_json: str = Field(default="{}")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QuoteRecord(SQLModel, table=True):
    """
    Persisted quote with pricing breakdown.
    Assignment: fare class, baggage, fees, cancellation policy.
    """
    __tablename__ = "quotes"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    quote_id: str = Field(index=True, unique=True, max_length=64)
    
    # References
    user_id: str = Field(index=True, max_length=64)
    bundle_id: str = Field(max_length=64)
    
    # Travelers
    travelers: int = Field(default=1)
    nights: int = Field(default=3)
    
    # Pricing breakdown
    flight_total: float = Field(default=0.0)
    hotel_total: float = Field(default=0.0)
    subtotal: float = Field(default=0.0)
    taxes: float = Field(default=0.0)
    fees: float = Field(default=0.0)
    grand_total: float = Field(index=True)
    
    # Flight details - Assignment requirements
    fare_class: str = Field(default="Economy", max_length=20)
    baggage: str = Field(default="1 carry-on included", max_length=64)
    
    # Cancellation policy - Assignment requirement
    cancellation_policy: str = Field(default="Contact provider for details", max_length=256)
    
    # Full breakdown (JSON)
    breakdown_json: str = Field(default="{}")
    
    # Validity
    valid_until: datetime = Field(default_factory=lambda: datetime.utcnow())
    
    # Status
    status: str = Field(default="pending", max_length=20)  # pending, accepted, expired
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BookingRecord(SQLModel, table=True):
    """
    Persisted booking after user confirms.
    """
    __tablename__ = "bookings_ai"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    booking_id: str = Field(index=True, unique=True, max_length=64)
    booking_reference: str = Field(max_length=20)  # e.g., "BK12345ABC"
    
    # References
    user_id: str = Field(index=True, max_length=64)
    quote_id: str = Field(max_length=64)
    bundle_id: str = Field(max_length=64)
    
    # Booking details
    total_price: float = Field(default=0.0)
    travelers: int = Field(default=1)
    
    # Status
    status: str = Field(default="confirmed", max_length=20)  # confirmed, cancelled, completed
    
    # Full booking data (JSON)
    booking_data_json: str = Field(default="{}")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WatchRecord(SQLModel, table=True):
    """
    Persisted price/inventory watch.
    Assignment: Set price/inventory threshold, async WebSocket updates.
    """
    __tablename__ = "watches"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    watch_id: str = Field(index=True, unique=True, max_length=64)
    
    # User
    user_id: str = Field(index=True, max_length=64)
    
    # What to watch
    listing_type: str = Field(max_length=20)  # "bundle", "flight", "hotel"
    listing_id: str = Field(max_length=64)
    listing_name: str = Field(max_length=256)
    
    # Watch type and thresholds - Assignment: price/inventory threshold
    watch_type: str = Field(default="price", max_length=20)  # "price", "inventory", "both"
    price_threshold: Optional[float] = Field(default=None)
    inventory_threshold: Optional[int] = Field(default=None)
    
    # Current values (for comparison)
    current_price: Optional[float] = Field(default=None)
    current_inventory: Optional[int] = Field(default=None)
    
    # Status
    is_active: bool = Field(default=True)
    triggered: bool = Field(default=False)
    triggered_at: Optional[datetime] = Field(default=None)
    trigger_reason: Optional[str] = Field(default=None, max_length=256)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)
