# ai/models/database.py
"""
SQLite Database Connection and Initialization.
Satisfies assignment requirement: "SQLite locally"
"""

import os
from sqlmodel import SQLModel, create_engine, Session
from typing import Generator
from loguru import logger

# SQLite database path - mounted volume in Docker
# Host: data/kayak_ai.db -> Container: /data/kayak_ai.db
SQLITE_PATH = os.getenv("SQLITE_PATH", "/data/kayak_ai.db")
SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

# For local development (outside Docker)
if not os.path.exists("/data") and not os.getenv("DOCKER_ENV"):
    # Use local path for development
    LOCAL_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "kayak_ai.db")
    os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
    SQLITE_URL = f"sqlite:///{LOCAL_PATH}"
    logger.info(f"Using local SQLite path: {LOCAL_PATH}")

# Create engine with SQLite-specific settings
engine = create_engine(
    SQLITE_URL,
    echo=False,  # Set to True for SQL debugging
    connect_args={"check_same_thread": False}  # Required for SQLite with FastAPI
)


def get_engine():
    """Get SQLAlchemy engine"""
    return engine


def get_session() -> Generator[Session, None, None]:
    """
    Get a database session.
    Usage:
        with get_session() as session:
            session.add(entity)
            session.commit()
    """
    with Session(engine) as session:
        yield session


def init_db():
    """
    Initialize database - create all tables.
    Call this at application startup.
    """
    # Import all models to ensure they are registered
    from .deals_entities import FlightDeal, HotelDeal, Airport
    from .concierge_entities import BundleRecord, QuoteRecord, BookingRecord, WatchRecord
    
    logger.info(f"Initializing SQLite database at: {SQLITE_URL}")
    SQLModel.metadata.create_all(engine)
    logger.info("SQLite database initialized successfully")


def drop_all_tables():
    """Drop all tables - use with caution!"""
    SQLModel.metadata.drop_all(engine)
    logger.warning("All SQLite tables dropped")


def get_db_stats() -> dict:
    """Get database statistics"""
    from .deals_entities import FlightDeal, HotelDeal, Airport
    from .concierge_entities import BundleRecord, QuoteRecord, BookingRecord, WatchRecord
    
    with Session(engine) as session:
        stats = {
            "flights": session.query(FlightDeal).count(),
            "hotels": session.query(HotelDeal).count(),
            "airports": session.query(Airport).count(),
            "bundles": session.query(BundleRecord).count(),
            "quotes": session.query(QuoteRecord).count(),
            "bookings": session.query(BookingRecord).count(),
            "watches": session.query(WatchRecord).count(),
        }
    return stats
