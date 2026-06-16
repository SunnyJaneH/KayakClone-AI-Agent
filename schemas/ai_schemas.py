# schemas/ai_schemas.py
"""
Complete Pydantic v2 schemas for AI Recommendation Service
Covers all 5 user journeys and API requirements
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ============================================
# Enums
# ============================================

class ListingType(str, Enum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    CAR = "car"


class WatchType(str, Enum):
    PRICE = "price"
    INVENTORY = "inventory"


class DealQuality(str, Enum):
    EXCELLENT = "excellent"  # 80+
    GREAT = "great"          # 60-79
    GOOD = "good"            # 40-59
    FAIR = "fair"            # <40


class AlertType(str, Enum):
    PRICE_DROP = "price_drop"
    INVENTORY_LOW = "inventory_low"
    DEAL_FOUND = "deal_found"
    WATCH_TRIGGERED = "watch_triggered"


# ============================================
# Intent & Session (Refine without starting over)
# ============================================

class ParsedIntent(BaseModel):
    """Structured intent extracted from natural language"""
    origin: Optional[str] = None
    destination: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    budget: Optional[float] = None
    travelers: int = 1
    constraints: List[str] = Field(default_factory=list)  # ["pet-friendly", "no-redeye"]
    raw_query: str = ""
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class SessionState(BaseModel):
    """Session state for multi-turn conversations"""
    session_id: str
    user_id: str
    
    # Accumulated search parameters
    origin: Optional[str] = None
    destination: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    budget: Optional[float] = None
    travelers: int = 1
    constraints: List[str] = Field(default_factory=list)
    
    # Previous recommendations for comparison
    previous_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Conversation history
    conversation_turns: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# Explanations (Why this + What to watch)
# ============================================

class Explanation(BaseModel):
    """Structured explanation for recommendations"""
    why_this: str = Field(..., max_length=150)  # ≤25 words
    what_to_watch: str = Field(..., max_length=75)  # ≤12 words


class PriceComparison(BaseModel):
    """Price analysis for 'Decide with confidence'"""
    current_price: float
    avg_30d_price: float
    avg_60d_price: Optional[float] = None
    price_vs_avg_percent: float  # e.g., -19 means 19% below average
    similar_options: List[Dict[str, Any]] = Field(default_factory=list)
    verdict: str  # "EXCELLENT DEAL", "GREAT DEAL", "FAIR PRICE", "OVERPRICED"


# ============================================
# Policy Info (Policy Answers)
# ============================================

class PolicyInfo(BaseModel):
    """Structured policy information"""
    refundable: bool = False
    refund_window: Optional[str] = None  # "24 hours before", "Oct 23, 6:00 PM"
    cancellation_fee: Optional[float] = None
    pet_friendly: bool = False
    pet_fee: Optional[float] = None
    parking: Optional[str] = None  # "Free", "$20/night", "Not available"
    breakfast: bool = False
    breakfast_fee: Optional[float] = None
    wifi: bool = True
    wifi_fee: Optional[float] = None


# ============================================
# Flight & Hotel Models
# ============================================

class FlightInfo(BaseModel):
    """Flight details"""
    flight_id: str
    airline: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    stops: int = 0
    flight_class: str = "Economy"
    price: float
    avg_30d_price: Optional[float] = None
    seats_left: Optional[int] = None
    baggage_included: str = "1 carry-on"
    checked_bag_fee: Optional[float] = None
    seat_selection_fee: Optional[float] = None
    change_fee: Optional[float] = None
    rating: Optional[float] = None


class HotelInfo(BaseModel):
    """Hotel details"""
    hotel_id: str
    name: str
    city: str
    star_rating: int
    room_type: str = "Standard"
    price_per_night: float
    avg_30d_price: Optional[float] = None
    total_nights: int = 1
    total_price: float
    rooms_left: Optional[int] = None
    amenities: List[str] = Field(default_factory=list)
    rating: Optional[float] = None
    review_count: Optional[int] = None
    neighborhood: Optional[str] = None
    policy: Optional[PolicyInfo] = None
    resort_fee: Optional[float] = None
    taxes: Optional[float] = None


# ============================================
# Bundle (Tell me what I should book)
# ============================================

class Bundle(BaseModel):
    """Flight + Hotel bundle"""
    bundle_id: str
    flight: FlightInfo
    hotel: HotelInfo
    
    # Pricing
    total_price: float
    separate_price: float  # If booked separately
    savings: float
    savings_percent: float
    
    # Scores
    deal_score: int = Field(..., ge=0, le=100)
    fit_score: int = Field(..., ge=0, le=100)
    
    # Explanations
    explanation: Explanation
    
    # Price analysis
    price_analysis: Optional[PriceComparison] = None


class BundleRecommendations(BaseModel):
    """Response for 'Tell me what I should book'"""
    bundles: List[Bundle]
    query_understood: str  # Echo back what we understood
    session_id: str
    total_options_found: int


# ============================================
# Change Highlight (Refine without starting over)
# ============================================

class ChangeItem(BaseModel):
    """Single change from previous recommendation"""
    field: str  # "price", "flight_time", "hotel"
    previous_value: str
    new_value: str
    change_type: str  # "increase", "decrease", "added", "removed"
    change_amount: Optional[str] = None  # "+$38", "-2 hours"
    is_improvement: bool


class RefinedRecommendations(BaseModel):
    """Response for 'Refine without starting over'"""
    bundles: List[Bundle]
    changes_summary: str  # "Updated based on: pet-friendly, no red-eye"
    changes: List[ChangeItem]
    constraints_applied: List[str]
    session_id: str


# ============================================
# Watches (Keep an eye on it)
# ============================================

class WatchCreate(BaseModel):
    """Request to create a watch"""
    user_id: str
    listing_type: ListingType
    listing_id: str
    listing_name: str
    watch_type: WatchType
    threshold: float  # Price threshold or inventory count
    current_value: float


class Watch(BaseModel):
    """Watch record"""
    watch_id: str
    user_id: str
    listing_type: ListingType
    listing_id: str
    listing_name: str
    watch_type: WatchType
    threshold: float
    current_value: float
    created_at: datetime
    triggered: bool = False
    triggered_at: Optional[datetime] = None


class WatchList(BaseModel):
    """User's watches"""
    watches: List[Watch]
    active_count: int
    triggered_count: int


# ============================================
# Alerts & Events (WebSocket push)
# ============================================

class Alert(BaseModel):
    """Real-time alert pushed via WebSocket"""
    alert_id: str
    alert_type: AlertType
    user_id: str
    title: str
    message: str
    listing_type: Optional[ListingType] = None
    listing_id: Optional[str] = None
    previous_value: Optional[float] = None
    new_value: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    read: bool = False


class EventMessage(BaseModel):
    """WebSocket event message"""
    event_type: str  # "alert", "deal", "watch_triggered"
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# Full Quote (Book or hand off cleanly)
# ============================================

class FlightQuote(BaseModel):
    """Detailed flight quote"""
    flight: FlightInfo
    base_fare: float
    taxes: float
    baggage_fee: float = 0
    seat_selection_fee: float = 0
    total: float
    cancellation_policy: str
    change_policy: str


class HotelQuote(BaseModel):
    """Detailed hotel quote"""
    hotel: HotelInfo
    room_rate: float
    nights: int
    subtotal: float
    resort_fee: float = 0
    taxes: float
    total: float
    cancellation_policy: str
    cancellation_deadline: Optional[datetime] = None


class FullQuote(BaseModel):
    """Complete quote for 'Book or hand off cleanly'"""
    quote_id: str
    bundle_id: str
    
    flight_quote: FlightQuote
    hotel_quote: HotelQuote
    
    grand_total: float
    bundle_savings: float
    
    # Policies summary
    cancellation_summary: str
    important_notes: List[str]
    
    # Valid until
    quote_valid_until: datetime
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# Chat Request/Response
# ============================================

class ChatRequest(BaseModel):
    """Chat API request"""
    query: str
    user_id: str
    session_id: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """Chat API response"""
    response: str
    session_id: str
    user_id: str
    
    # Parsed intent
    parsed_intent: Optional[ParsedIntent] = None
    
    # Recommendations (if applicable)
    recommendations: Optional[BundleRecommendations] = None
    
    # Changes (if refining)
    changes: Optional[List[ChangeItem]] = None
    
    # Clarification needed
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================
# Score Request/Response
# ============================================

class ScoreRequest(BaseModel):
    """Deal score request"""
    current_price: float
    avg_30d_price: float
    availability: Optional[int] = None
    rating: Optional[float] = None
    has_promotion: bool = False


class ScoreResponse(BaseModel):
    """Deal score response"""
    deal_score: int
    quality: DealQuality
    breakdown: Dict[str, int]
    explanation: Explanation


# ============================================
# Health Check
# ============================================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    llm_provider: str
    llm_model: str
    components: Dict[str, str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
