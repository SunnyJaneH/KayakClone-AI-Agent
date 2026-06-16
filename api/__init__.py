# api/__init__.py
"""
API Endpoints Package

Contains all FastAPI routers for the AI service:
- chat: Conversational AI interface
- bundles: Bundle recommendations
- watches: Price/availability alerts
- price_analysis: Deal validation
- quotes: Booking quotes
- events_websocket: Real-time WebSocket events
"""

from typing import TYPE_CHECKING

# Lazy imports to avoid circular dependencies
if TYPE_CHECKING:
    from .chat import router as chat_router
    from .bundles import router as bundles_router
    from .watches import router as watches_router
    from .price_analysis import router as price_analysis_router
    from .quotes import router as quotes_router
    from .events_websocket import events_manager

__all__ = [
    "chat_router",
    "bundles_router", 
    "watches_router",
    "price_analysis_router",
    "quotes_router",
    "events_manager"
]
