# ai/models/__init__.py
"""
SQLModel entities for AI Service persistence.
Satisfies assignment requirement: "Persist normalized entities with SQLModel (SQLite locally)"
"""

from .database import get_engine, get_session, init_db, SQLITE_URL
from .deals_entities import FlightDeal, HotelDeal, Airport
from .concierge_entities import BundleRecord, QuoteRecord, BookingRecord, WatchRecord

__all__ = [
    # Database
    "get_engine",
    "get_session", 
    "init_db",
    "SQLITE_URL",
    # Deals entities
    "FlightDeal",
    "HotelDeal",
    "Airport",
    # Concierge entities
    "BundleRecord",
    "QuoteRecord",
    "BookingRecord",
    "WatchRecord",
]
