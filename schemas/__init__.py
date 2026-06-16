# schemas/__init__.py
"""
Pydantic Schemas Package

Contains all Pydantic v2 models for:
- API requests/responses
- Internal data structures
- Kafka message schemas
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ai_schemas import (
        # Enums
        ListingType, WatchType, DealQuality, AlertType,
        # Intent & Session
        ParsedIntent, SessionState,
        # Explanations
        Explanation, PriceComparison,
        # Policy
        PolicyInfo,
        # Listings
        FlightInfo, HotelInfo,
        # Bundle
        Bundle, BundleRecommendations, RefinedRecommendations,
        # Watches
        Watch, WatchCreate, WatchList,
        # Events
        Alert, EventMessage,
        # Quotes
        FlightQuote, HotelQuote, FullQuote,
        # API
        ChatRequest, ChatResponse, ScoreRequest, ScoreResponse, HealthResponse
    )

__all__ = [
    # Enums
    "ListingType", "WatchType", "DealQuality", "AlertType",
    # Intent & Session
    "ParsedIntent", "SessionState",
    # Explanations
    "Explanation", "PriceComparison",
    # Policy
    "PolicyInfo",
    # Listings
    "FlightInfo", "HotelInfo",
    # Bundle
    "Bundle", "BundleRecommendations", "RefinedRecommendations",
    # Watches
    "Watch", "WatchCreate", "WatchList",
    # Events
    "Alert", "EventMessage",
    # Quotes
    "FlightQuote", "HotelQuote", "FullQuote",
    # API
    "ChatRequest", "ChatResponse", "ScoreRequest", "ScoreResponse", "HealthResponse"
]
