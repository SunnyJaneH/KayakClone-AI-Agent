# api/quotes.py
"""
Quotes API
Implements "Book or hand off cleanly" functionality.

Generates complete, itemized quotes for bundles with all fees,
policies, and important notes so users can book with confidence.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

# Import services
try:
    from llm.quote_generator import quote_generator
except ImportError:
    quote_generator = None

try:
    from interfaces.policy_store import policy_store
except ImportError:
    policy_store = None

try:
    from interfaces.session_store import session_store
except ImportError:
    session_store = None


router = APIRouter(prefix="/api/ai/quotes", tags=["quotes"])


# ============================================
# Models
# ============================================

class FlightPricing(BaseModel):
    """Itemized flight pricing"""
    base_fare: float
    taxes: float
    carrier_fee: float
    baggage_fee: float = 0
    seat_selection_fee: float = 0
    total: float


class FlightQuoteDetail(BaseModel):
    """Detailed flight quote"""
    flight_id: str
    airline: str
    route: str  # e.g., "SFO → MIA"
    departure: str
    arrival: str
    duration: str
    stops: int
    cabin_class: str = "Economy"
    
    pricing: FlightPricing
    
    baggage_policy: str
    cancellation_policy: str
    change_fee: float
    refundable: bool


class HotelPricing(BaseModel):
    """Itemized hotel pricing"""
    rate_per_night: float
    nights: int
    subtotal: float
    resort_fee: float = 0
    taxes: float
    total: float


class HotelQuoteDetail(BaseModel):
    """Detailed hotel quote"""
    hotel_id: str
    name: str
    address: str
    star_rating: float
    
    check_in: str
    check_out: str
    room_type: str = "Standard Room"
    
    pricing: HotelPricing
    
    amenities: List[str] = []
    cancellation_policy: str
    cancellation_deadline: Optional[str] = None
    refundable: bool


class QuoteSummary(BaseModel):
    """Quote summary with totals"""
    flight_total: float
    hotel_total: float
    grand_total: float
    separate_booking_total: float
    bundle_savings: float
    savings_percent: float


class FullQuoteResponse(BaseModel):
    """Complete quote response"""
    quote_id: str
    bundle_id: str
    
    flight_quote: FlightQuoteDetail
    hotel_quote: HotelQuoteDetail
    summary: QuoteSummary
    
    # Combined policies
    cancellation_summary: str
    important_notes: List[str]
    
    # Validity
    quote_valid_until: str
    terms_url: str = "https://kayak.example.com/terms"
    
    # Metadata
    generated_at: str
    travelers: int = 1


class QuoteRequest(BaseModel):
    """Request for generating a quote"""
    bundle_id: Optional[str] = None
    flight_id: Optional[str] = None
    hotel_id: Optional[str] = None
    
    # Travel details
    origin: str = "SFO"
    destination: str = "MIA"
    departure_date: str
    return_date: str
    travelers: int = Field(1, ge=1, le=10)
    
    # User context
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class SimpleQuoteResponse(BaseModel):
    """Simplified quote for quick display"""
    quote_id: str
    total_price: float
    flight_price: float
    hotel_price: float
    savings: float
    valid_until: str
    book_url: str


# ============================================
# Helper Functions
# ============================================

def calculate_flight_pricing(
    base_fare: float,
    is_international: bool = False,
    airline: str = "Unknown"
) -> FlightPricing:
    """Calculate itemized flight pricing"""
    
    # Tax rates
    tax_rate = 0.10 if is_international else 0.075
    taxes = base_fare * tax_rate
    
    # Carrier fees vary by airline
    carrier_fees = {
        "American Airlines": 35,
        "United": 35,
        "Delta": 30,
        "Southwest": 0,  # No carrier fee
        "JetBlue": 25,
        "Alaska": 25
    }
    carrier_fee = carrier_fees.get(airline, 30)
    
    total = base_fare + taxes + carrier_fee
    
    return FlightPricing(
        base_fare=base_fare,
        taxes=round(taxes, 2),
        carrier_fee=carrier_fee,
        baggage_fee=0,  # Not included by default
        seat_selection_fee=0,
        total=round(total, 2)
    )


def calculate_hotel_pricing(
    rate_per_night: float,
    nights: int,
    star_rating: float = 3.0
) -> HotelPricing:
    """Calculate itemized hotel pricing"""
    
    subtotal = rate_per_night * nights
    
    # Resort fee based on star rating
    resort_fee = 0
    if star_rating >= 4.5:
        resort_fee = 45 * nights
    elif star_rating >= 4.0:
        resort_fee = 30 * nights
    elif star_rating >= 3.5:
        resort_fee = 15 * nights
    
    # Tax rate (typically 12-15%)
    tax_rate = 0.125
    taxes = (subtotal + resort_fee) * tax_rate
    
    total = subtotal + resort_fee + taxes
    
    return HotelPricing(
        rate_per_night=rate_per_night,
        nights=nights,
        subtotal=subtotal,
        resort_fee=resort_fee,
        taxes=round(taxes, 2),
        total=round(total, 2)
    )


def generate_cancellation_summary(
    flight_refundable: bool,
    flight_change_fee: float,
    hotel_refundable: bool,
    hotel_deadline: Optional[str]
) -> str:
    """Generate combined cancellation policy summary"""
    parts = []
    
    # Flight policy
    if flight_refundable:
        parts.append("Flight: Refundable with no fee up to 24 hours before departure")
    else:
        parts.append(f"Flight: Non-refundable. Changes allowed with ${flight_change_fee} fee")
    
    # Hotel policy
    if hotel_refundable:
        if hotel_deadline:
            parts.append(f"Hotel: Free cancellation until {hotel_deadline}")
        else:
            parts.append("Hotel: Free cancellation up to 24 hours before check-in")
    else:
        parts.append("Hotel: Non-refundable")
    
    return " | ".join(parts)


def generate_important_notes(
    flight: dict,
    hotel: dict,
    travelers: int
) -> List[str]:
    """Generate important notes for the quote"""
    notes = []
    
    # Flight notes
    if flight.get("stops", 0) > 0:
        notes.append(f"Flight has {flight['stops']} stop(s)")
    
    if not flight.get("refundable", False):
        notes.append("Flight ticket is non-refundable")
    
    if flight.get("change_fee", 0) > 0:
        notes.append(f"Flight changes incur ${flight['change_fee']} fee")
    
    # Baggage note
    notes.append("Checked baggage not included - first bag typically $30-35")
    
    # Hotel notes
    if hotel.get("resort_fee", 0) > 0:
        notes.append(f"Resort fee of ${hotel['resort_fee']}/night included")
    
    if hotel.get("cancellation_deadline"):
        notes.append(f"Hotel: cancel by {hotel['cancellation_deadline']} for full refund")
    
    # General notes
    if travelers > 1:
        notes.append(f"Quote is for {travelers} traveler(s)")
    
    notes.append("Prices may change until booking is confirmed")
    notes.append("Valid ID required at check-in")
    
    return notes


# ============================================
# API Endpoints
# ============================================

@router.post("/generate", response_model=FullQuoteResponse)
async def generate_quote(request: QuoteRequest):
    """
    Generate a complete quote for booking.
    
    Returns itemized pricing, all fees, and policies.
    Implements "Book or hand off cleanly" user journey.
    """
    logger.info(f"Generating quote: {request.destination}, {request.departure_date}")
    
    # Calculate nights
    try:
        dep_date = datetime.fromisoformat(request.departure_date)
        ret_date = datetime.fromisoformat(request.return_date)
        nights = max(1, (ret_date - dep_date).days)
    except:
        nights = 3
        dep_date = datetime.utcnow() + timedelta(days=30)
        ret_date = dep_date + timedelta(days=3)
    
    # Generate quote ID
    quote_id = f"Q{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    # Flight details (would fetch from cache/API in production)
    is_international = request.destination not in ["MIA", "LAX", "NYC", "ORD", "DFW", "SEA", "BOS"]
    base_fare = 350 if not is_international else 650
    airline = "American Airlines"
    
    flight_pricing = calculate_flight_pricing(base_fare, is_international, airline)
    
    flight_quote = FlightQuoteDetail(
        flight_id=request.flight_id or f"FL{quote_id}",
        airline=airline,
        route=f"{request.origin} → {request.destination}",
        departure=dep_date.strftime("%Y-%m-%d %H:%M"),
        arrival=(dep_date + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M"),
        duration="5h 15m",
        stops=0,
        cabin_class="Economy",
        pricing=flight_pricing,
        baggage_policy="Personal item free. Carry-on $35. Checked bag $40.",
        cancellation_policy="Non-refundable. Changes allowed with fee.",
        change_fee=200,
        refundable=False
    )
    
    # Hotel details
    rate_per_night = 180
    star_rating = 4.0
    
    hotel_pricing = calculate_hotel_pricing(rate_per_night, nights, star_rating)
    
    cancel_deadline = (dep_date - timedelta(days=2)).strftime("%Y-%m-%d")
    
    hotel_quote = HotelQuoteDetail(
        hotel_id=request.hotel_id or f"HT{quote_id}",
        name=f"{request.destination} Grand Hotel",
        address=f"123 Beach Blvd, {request.destination}",
        star_rating=star_rating,
        check_in=dep_date.strftime("%Y-%m-%d") + " 15:00",
        check_out=ret_date.strftime("%Y-%m-%d") + " 11:00",
        room_type="Deluxe King Room",
        pricing=hotel_pricing,
        amenities=["WiFi", "Pool", "Gym", "Restaurant", "Parking"],
        cancellation_policy=f"Free cancellation until {cancel_deadline}",
        cancellation_deadline=cancel_deadline,
        refundable=True
    )
    
    # Calculate summary
    grand_total = flight_pricing.total + hotel_pricing.total
    separate_total = grand_total * 1.10  # 10% more if booked separately
    savings = separate_total - grand_total
    
    summary = QuoteSummary(
        flight_total=flight_pricing.total,
        hotel_total=hotel_pricing.total,
        grand_total=grand_total,
        separate_booking_total=round(separate_total, 2),
        bundle_savings=round(savings, 2),
        savings_percent=round((savings / separate_total) * 100, 1)
    )
    
    # Generate combined policies
    cancellation_summary = generate_cancellation_summary(
        flight_refundable=flight_quote.refundable,
        flight_change_fee=flight_quote.change_fee,
        hotel_refundable=hotel_quote.refundable,
        hotel_deadline=hotel_quote.cancellation_deadline
    )
    
    # Generate important notes
    important_notes = generate_important_notes(
        flight={
            "stops": flight_quote.stops,
            "refundable": flight_quote.refundable,
            "change_fee": flight_quote.change_fee
        },
        hotel={
            "resort_fee": hotel_pricing.resort_fee / nights if nights > 0 else 0,
            "cancellation_deadline": hotel_quote.cancellation_deadline
        },
        travelers=request.travelers
    )
    
    # Quote validity (30 minutes)
    valid_until = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    
    return FullQuoteResponse(
        quote_id=quote_id,
        bundle_id=request.bundle_id or f"B{quote_id}",
        flight_quote=flight_quote,
        hotel_quote=hotel_quote,
        summary=summary,
        cancellation_summary=cancellation_summary,
        important_notes=important_notes,
        quote_valid_until=valid_until,
        generated_at=datetime.utcnow().isoformat(),
        travelers=request.travelers
    )


@router.get("/simple/{bundle_id}", response_model=SimpleQuoteResponse)
async def get_simple_quote(
    bundle_id: str,
    departure_date: str = Query(...),
    return_date: str = Query(...),
    travelers: int = Query(1, ge=1, le=10)
):
    """
    Get simplified quote for quick display.
    
    Returns totals without full itemization.
    """
    # Calculate
    try:
        dep = datetime.fromisoformat(departure_date)
        ret = datetime.fromisoformat(return_date)
        nights = max(1, (ret - dep).days)
    except:
        nights = 3
    
    flight_price = 385  # Base + taxes + fees
    hotel_price = 180 * nights * 1.125  # Rate + taxes
    total = flight_price + hotel_price
    savings = total * 0.10
    
    quote_id = f"Q{datetime.utcnow().strftime('%H%M%S')}"
    valid_until = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    
    return SimpleQuoteResponse(
        quote_id=quote_id,
        total_price=round(total, 2),
        flight_price=round(flight_price, 2),
        hotel_price=round(hotel_price, 2),
        savings=round(savings, 2),
        valid_until=valid_until,
        book_url=f"https://kayak.example.com/book/{bundle_id}?quote={quote_id}"
    )


@router.get("/{quote_id}", response_model=FullQuoteResponse)
async def get_quote(quote_id: str):
    """
    Retrieve a previously generated quote.
    
    Quotes are valid for 30 minutes.
    """
    # In production, would fetch from cache/database
    raise HTTPException(
        status_code=404,
        detail=f"Quote {quote_id} not found or expired"
    )


@router.post("/{quote_id}/refresh", response_model=FullQuoteResponse)
async def refresh_quote(quote_id: str):
    """
    Refresh an expired quote with current prices.
    
    Returns new quote ID with updated pricing.
    """
    # In production, would fetch original params and regenerate
    raise HTTPException(
        status_code=404,
        detail=f"Quote {quote_id} not found"
    )


@router.post("/{quote_id}/book")
async def initiate_booking(
    quote_id: str,
    user_id: Optional[str] = Query(None)
):
    """
    Initiate booking from quote.
    
    Returns booking session URL or hands off to booking service.
    """
    # In production, would:
    # 1. Validate quote is still valid
    # 2. Lock prices
    # 3. Create booking session
    # 4. Return redirect URL to booking flow
    
    booking_session_id = f"BS{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    return {
        "status": "initiated",
        "booking_session_id": booking_session_id,
        "quote_id": quote_id,
        "redirect_url": f"https://kayak.example.com/checkout/{booking_session_id}",
        "expires_in_minutes": 15,
        "message": "Redirecting to secure checkout..."
    }


@router.get("/policies/{listing_type}/{listing_id}")
async def get_policies(listing_type: str, listing_id: str):
    """
    Get detailed policies for a listing.
    
    Returns cancellation, change, and other policies.
    """
    # Get from policy store if available
    if policy_store:
        policy = policy_store.get_policy(listing_id)
        if policy:
            return policy_store.format_policy_summary(policy)
    
    # Return default policies based on listing type
    if listing_type == "flight":
        return {
            "listing_id": listing_id,
            "listing_type": listing_type,
            "cancellation": {
                "refundable": False,
                "fee": 200,
                "policy": "Non-refundable. Changes allowed with $200 fee."
            },
            "baggage": {
                "personal_item": "Free",
                "carry_on": "$35",
                "checked_first": "$40",
                "checked_second": "$45"
            },
            "changes": {
                "allowed": True,
                "fee": 200,
                "deadline": "Up to 24 hours before departure"
            }
        }
    else:  # hotel
        return {
            "listing_id": listing_id,
            "listing_type": listing_type,
            "cancellation": {
                "refundable": True,
                "deadline": "24 hours before check-in",
                "policy": "Free cancellation up to 24 hours before check-in"
            },
            "check_in": {
                "time": "15:00",
                "early_check_in": "Subject to availability, $50 fee"
            },
            "check_out": {
                "time": "11:00",
                "late_check_out": "Subject to availability, $50 fee"
            },
            "policies": {
                "pets": "Not allowed",
                "smoking": "Non-smoking property",
                "parking": "$25/night self-parking"
            }
        }
