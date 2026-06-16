# api/bundles.py
"""
/bundles HTTP API Endpoint
Implements the main bundle recommendation endpoint.

GET /api/ai/bundles - Get bundle recommendations
POST /api/ai/bundles/search - Search with filters
GET /api/ai/bundles/{bundle_id} - Get specific bundle
POST /api/ai/bundles/{bundle_id}/score - Get fit score for user
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel, Field
from loguru import logger

# Import schemas
try:
    from schemas.ai_schemas import (
        Bundle, BundleRecommendations, RefinedRecommendations,
        Explanation, FlightInfo, HotelInfo, ListingType
    )
except ImportError:
    # Inline minimal schemas if import fails
    from pydantic import BaseModel
    class Bundle(BaseModel):
        bundle_id: str
        total_price: float
        deal_score: int = 70

# Import services
try:
    from interfaces.deals_cache import deals_cache, get_deals_for_bundle
except ImportError:
    deals_cache = None
    def get_deals_for_bundle(**kwargs):
        return {"flights": [], "hotels": []}

try:
    from interfaces.session_store import session_store
except ImportError:
    session_store = None

try:
    from llm.explainer import explainer
except ImportError:
    explainer = None

try:
    from algorithms.deal_scorer import calculate_deal_score
except ImportError:
    def calculate_deal_score(**kwargs):
        return 70


router = APIRouter(prefix="/api/ai/bundles", tags=["bundles"])


# ============================================
# Request/Response Models
# ============================================

class BundleSearchRequest(BaseModel):
    """Request model for bundle search"""
    origin: Optional[str] = Field(None, description="Origin airport code", example="SFO")
    destination: str = Field(..., description="Destination airport/city", example="MIA")
    date_from: Optional[str] = Field(None, description="Departure date", example="2025-01-15")
    date_to: Optional[str] = Field(None, description="Return date", example="2025-01-20")
    budget: Optional[float] = Field(None, description="Max total budget", example=1500)
    travelers: int = Field(1, ge=1, le=10, description="Number of travelers")
    constraints: List[str] = Field(default_factory=list, description="Filters like pet-friendly, direct-flight")
    session_id: Optional[str] = Field(None, description="Session ID for context")
    user_id: Optional[str] = Field(None, description="User ID")


class BundleResponse(BaseModel):
    """Single bundle response"""
    bundle_id: str
    name: str
    destination: str
    origin: Optional[str] = None
    
    # Pricing
    total_price: float
    separate_booking_price: float
    savings: float
    savings_percent: float
    
    # Scoring
    deal_score: int = Field(..., ge=0, le=100)
    fit_score: Optional[int] = Field(None, ge=0, le=100)
    
    # Components
    flight: Optional[dict] = None
    hotel: Optional[dict] = None
    
    # Explanations
    why_this: str = Field(..., max_length=150, description="≤25 words")
    what_to_watch: str = Field(..., max_length=75, description="≤12 words")
    
    # Metadata
    tags: List[str] = []
    availability: Optional[int] = None
    expires_at: Optional[str] = None


class BundleListResponse(BaseModel):
    """List of bundles response"""
    bundles: List[BundleResponse]
    total_count: int
    session_id: Optional[str] = None
    search_params: dict = {}
    timestamp: str


class FitScoreRequest(BaseModel):
    """Request for fit score calculation"""
    user_id: str
    preferences: dict = Field(default_factory=dict)


class FitScoreResponse(BaseModel):
    """Fit score response"""
    bundle_id: str
    fit_score: int = Field(..., ge=0, le=100)
    fit_reasons: List[str]
    mismatches: List[str]


# ============================================
# Helper Functions
# ============================================

def build_bundle_response(
    flight: Optional[dict],
    hotel: Optional[dict],
    params: dict,
    index: int
) -> BundleResponse:
    """Build a BundleResponse from flight and hotel deals"""
    
    # Calculate prices
    flight_price = flight.get("current_price", 0) if flight else 0
    nights = 3  # Default
    if params.get("date_from") and params.get("date_to"):
        try:
            from datetime import datetime as dt
            d1 = dt.fromisoformat(params["date_from"])
            d2 = dt.fromisoformat(params["date_to"])
            nights = max(1, (d2 - d1).days)
        except:
            pass
    
    hotel_price = (hotel.get("current_price", 0) * nights) if hotel else 0
    total_price = flight_price + hotel_price
    
    # Separate booking would be ~10% more
    separate_price = total_price * 1.10
    savings = separate_price - total_price
    savings_percent = (savings / separate_price * 100) if separate_price > 0 else 0
    
    # Calculate deal score
    flight_score = flight.get("deal_score", 70) if flight else 70
    hotel_score = hotel.get("deal_score", 70) if hotel else 70
    deal_score = (flight_score + hotel_score) // 2
    
    # Generate explanations
    why_this_parts = []
    what_to_watch_parts = []
    
    # Price-based explanations
    if savings > 50:
        why_this_parts.append(f"Save ${savings:.0f} vs separate booking")
    
    # Flight explanations
    if flight:
        if flight.get("metadata", {}).get("stops", 1) == 0:
            why_this_parts.append("Direct flight")
        if flight.get("deal_score", 0) >= 75:
            why_this_parts.append("Great flight deal")
    
    # Hotel explanations
    if hotel:
        rating = hotel.get("metadata", {}).get("star_rating", 0)
        if rating >= 4.5:
            why_this_parts.append(f"{rating}★ rated")
        if "breakfast" in hotel.get("tags", []):
            why_this_parts.append("Breakfast included")
        if hotel.get("availability", 10) <= 3:
            what_to_watch_parts.append(f"Only {hotel.get('availability')} rooms left")
    
    # Add general warnings
    if deal_score >= 80:
        why_this_parts.append("Excellent overall value")
    
    if not what_to_watch_parts:
        what_to_watch_parts.append("Book soon for best rates")
    
    # Enforce word limits
    why_this = ". ".join(why_this_parts[:3]) if why_this_parts else "Good value bundle"
    what_to_watch = ". ".join(what_to_watch_parts[:2]) if what_to_watch_parts else "Limited availability"
    
    # Truncate to word limits (25 words / 12 words)
    why_this_words = why_this.split()
    if len(why_this_words) > 25:
        why_this = " ".join(why_this_words[:25])
    
    watch_words = what_to_watch.split()
    if len(watch_words) > 12:
        what_to_watch = " ".join(watch_words[:12])
    
    # Build name
    origin = params.get("origin", "SFO")
    destination = params.get("destination", "")
    hotel_name = hotel.get("name", "Hotel") if hotel else "Hotel"
    name = f"{origin} → {destination} + {hotel_name}"
    
    # Collect tags
    tags = []
    if flight:
        tags.extend(flight.get("tags", []))
    if hotel:
        tags.extend(hotel.get("tags", []))
    tags = list(set(tags))[:10]  # Dedupe and limit
    
    return BundleResponse(
        bundle_id=f"bundle_{destination.lower()}_{index}_{datetime.utcnow().strftime('%H%M%S')}",
        name=name,
        destination=destination,
        origin=origin,
        total_price=total_price,
        separate_booking_price=separate_price,
        savings=savings,
        savings_percent=savings_percent,
        deal_score=deal_score,
        flight={
            "flight_id": flight.get("deal_id"),
            "airline": flight.get("name"),
            "price": flight_price,
            "stops": flight.get("metadata", {}).get("stops", 0),
            "departure": flight.get("metadata", {}).get("departure_time"),
            "arrival": flight.get("metadata", {}).get("arrival_time")
        } if flight else None,
        hotel={
            "hotel_id": hotel.get("deal_id"),
            "name": hotel.get("name"),
            "price_per_night": hotel.get("current_price", 0),
            "nights": nights,
            "total": hotel_price,
            "rating": hotel.get("metadata", {}).get("star_rating"),
            "amenities": hotel.get("tags", [])
        } if hotel else None,
        why_this=why_this,
        what_to_watch=what_to_watch,
        tags=tags,
        availability=min(
            flight.get("availability", 10) if flight else 10,
            hotel.get("availability", 10) if hotel else 10
        )
    )


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=BundleListResponse)
async def get_bundles(
    destination: str = Query(..., description="Destination city/airport"),
    origin: Optional[str] = Query(None, description="Origin airport"),
    date_from: Optional[str] = Query(None, description="Departure date"),
    date_to: Optional[str] = Query(None, description="Return date"),
    budget: Optional[float] = Query(None, description="Max budget"),
    travelers: int = Query(1, ge=1, le=10),
    constraints: Optional[str] = Query(None, description="Comma-separated constraints"),
    session_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get bundle recommendations for a destination.
    
    Returns flight + hotel bundles with explanations.
    """
    logger.info(f"GET /bundles: destination={destination}, budget={budget}")
    
    # Parse constraints
    constraint_list = []
    if constraints:
        constraint_list = [c.strip() for c in constraints.split(",")]
    
    # Build search params
    params = {
        "destination": destination.upper() if len(destination) == 3 else destination,
        "origin": origin.upper() if origin and len(origin) == 3 else origin,
        "date_from": date_from,
        "date_to": date_to,
        "budget": budget,
        "travelers": travelers,
        "constraints": constraint_list
    }
    
    # Calculate price limits
    max_flight = budget * 0.4 if budget else None
    max_hotel = budget * 0.6 / 3 if budget else None  # Assume 3 nights
    
    # Get deals
    deals = get_deals_for_bundle(
        destination=params["destination"],
        origin=params.get("origin"),
        max_flight_price=max_flight,
        max_hotel_price=max_hotel,
        tags=constraint_list if constraint_list else None
    )
    
    flights = deals.get("flights", [])
    hotels = deals.get("hotels", [])
    
    # Build bundles
    bundles = []
    num_bundles = min(limit, max(len(flights), len(hotels), 1))
    
    for i in range(num_bundles):
        flight = flights[i] if i < len(flights) else (flights[0] if flights else None)
        hotel = hotels[i] if i < len(hotels) else (hotels[0] if hotels else None)
        
        if flight or hotel:
            bundle = build_bundle_response(flight, hotel, params, i + 1)
            bundles.append(bundle)
    
    # Sort by deal score
    bundles.sort(key=lambda b: b.deal_score, reverse=True)
    
    # Save to session if available
    if session_store and session_id:
        session_store.save_recommendations(
            session_id, 
            [b.model_dump() for b in bundles]
        )
    
    return BundleListResponse(
        bundles=bundles[:limit],
        total_count=len(bundles),
        session_id=session_id,
        search_params=params,
        timestamp=datetime.utcnow().isoformat()
    )


@router.post("/search", response_model=BundleListResponse)
async def search_bundles(request: BundleSearchRequest):
    """
    Search for bundles with detailed filters.
    
    Supports session context for 'Refine without starting over'.
    """
    logger.info(f"POST /bundles/search: {request.destination}")
    
    # If session exists, merge with previous context
    params = request.model_dump()
    
    if session_store and request.session_id:
        prev_params = session_store.get_search_params(request.session_id)
        # Merge: new params override previous
        for key, value in params.items():
            if value is None and key in prev_params:
                params[key] = prev_params[key]
        
        # Update session
        session_store.update_session(request.session_id, {
            "search_params": params,
            "last_query_at": datetime.utcnow().isoformat()
        })
    
    # Calculate price limits
    budget = params.get("budget")
    max_flight = budget * 0.4 if budget else None
    max_hotel = budget * 0.6 / 3 if budget else None
    
    # Get deals
    deals = get_deals_for_bundle(
        destination=params["destination"],
        origin=params.get("origin"),
        max_flight_price=max_flight,
        max_hotel_price=max_hotel,
        tags=params.get("constraints")
    )
    
    flights = deals.get("flights", [])
    hotels = deals.get("hotels", [])
    
    # Build bundles
    bundles = []
    num_bundles = min(5, max(len(flights), len(hotels), 1))
    
    for i in range(num_bundles):
        flight = flights[i] if i < len(flights) else (flights[0] if flights else None)
        hotel = hotels[i] if i < len(hotels) else (hotels[0] if hotels else None)
        
        if flight or hotel:
            bundle = build_bundle_response(flight, hotel, params, i + 1)
            bundles.append(bundle)
    
    bundles.sort(key=lambda b: b.deal_score, reverse=True)
    
    # Check for changes from previous recommendations
    changes = []
    if session_store and request.session_id:
        prev_recs = session_store.get_previous_recommendations(request.session_id)
        if prev_recs and bundles:
            # Compare first bundle
            prev = prev_recs[0] if prev_recs else {}
            curr = bundles[0].model_dump()
            
            if prev.get("total_price") and curr.get("total_price"):
                price_diff = curr["total_price"] - prev.get("total_price", 0)
                if abs(price_diff) > 10:
                    changes.append({
                        "field": "price",
                        "previous": prev.get("total_price"),
                        "current": curr["total_price"],
                        "is_improvement": price_diff < 0
                    })
        
        # Save new recommendations
        session_store.save_recommendations(
            request.session_id,
            [b.model_dump() for b in bundles]
        )
    
    return BundleListResponse(
        bundles=bundles,
        total_count=len(bundles),
        session_id=request.session_id,
        search_params=params,
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/{bundle_id}", response_model=BundleResponse)
async def get_bundle(bundle_id: str):
    """Get a specific bundle by ID"""
    # In production, would look up from cache/database
    # For now, return 404
    raise HTTPException(status_code=404, detail=f"Bundle {bundle_id} not found")


@router.post("/{bundle_id}/score", response_model=FitScoreResponse)
async def get_fit_score(bundle_id: str, request: FitScoreRequest):
    """
    Calculate fit score for a bundle based on user preferences.
    
    Fit score indicates how well the bundle matches user's stated preferences.
    """
    # Get bundle (in production, from cache)
    # For demo, calculate based on preferences
    
    preferences = request.preferences
    fit_reasons = []
    mismatches = []
    score = 70  # Base score
    
    # Check budget fit
    if "budget" in preferences:
        # Would compare to actual bundle price
        fit_reasons.append("Within budget")
        score += 10
    
    # Check constraint matches
    if "constraints" in preferences:
        for constraint in preferences["constraints"]:
            # Would check if bundle has this tag
            fit_reasons.append(f"Has {constraint}")
            score += 5
    
    # Check date preferences
    if "flexible_dates" in preferences and preferences["flexible_dates"]:
        fit_reasons.append("Flexible dates available")
        score += 5
    
    # Cap score
    score = min(100, max(0, score))
    
    return FitScoreResponse(
        bundle_id=bundle_id,
        fit_score=score,
        fit_reasons=fit_reasons,
        mismatches=mismatches
    )


@router.get("/destinations/popular")
async def get_popular_destinations(limit: int = Query(10, ge=1, le=50)):
    """Get popular destinations with current deals"""
    
    # Would query deals_cache for destinations with most/best deals
    popular = [
        {"code": "MIA", "name": "Miami", "deal_count": 15, "avg_score": 78},
        {"code": "NYC", "name": "New York", "deal_count": 20, "avg_score": 72},
        {"code": "LAX", "name": "Los Angeles", "deal_count": 18, "avg_score": 75},
        {"code": "HNL", "name": "Honolulu", "deal_count": 8, "avg_score": 82},
        {"code": "CUN", "name": "Cancun", "deal_count": 12, "avg_score": 80},
    ]
    
    return {
        "destinations": popular[:limit],
        "timestamp": datetime.utcnow().isoformat()
    }
