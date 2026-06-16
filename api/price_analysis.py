# api/price_analysis.py
"""
Price Analysis API
Implements "Decide with confidence" functionality.

Provides price comparisons, historical analysis, and deal verdicts
to help users make informed booking decisions.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

# Import services
try:
    from interfaces.deals_cache import deals_cache
except ImportError:
    deals_cache = None

try:
    from llm.explainer import explainer
except ImportError:
    explainer = None


router = APIRouter(prefix="/api/ai/price-analysis", tags=["price-analysis"])


# ============================================
# Models
# ============================================

class PricePoint(BaseModel):
    """Historical price point"""
    date: str
    price: float
    source: str = "historical"


class SimilarOption(BaseModel):
    """Similar booking option for comparison"""
    name: str
    price: float
    difference: float  # vs current
    difference_percent: float
    pros: List[str] = []
    cons: List[str] = []


class PriceAnalysisResponse(BaseModel):
    """Full price analysis response"""
    listing_id: str
    listing_type: str
    listing_name: str
    
    # Current pricing
    current_price: float
    original_price: Optional[float] = None
    
    # Historical comparison
    avg_30d_price: float
    min_30d_price: float
    max_30d_price: float
    price_vs_avg_percent: float  # negative = below average (good)
    
    # Verdict
    verdict: str  # EXCELLENT_DEAL, GREAT_DEAL, GOOD_DEAL, FAIR_PRICE, ABOVE_AVERAGE
    verdict_explanation: str
    confidence: float = Field(..., ge=0, le=1)
    
    # Comparisons
    similar_options: List[SimilarOption] = []
    price_history: List[PricePoint] = []
    
    # Recommendations
    recommendation: str
    best_time_to_book: Optional[str] = None
    price_trend: str  # rising, falling, stable
    
    # Metadata
    analyzed_at: str
    data_points: int


class QuickAnalysisResponse(BaseModel):
    """Quick verdict without full analysis"""
    listing_id: str
    current_price: float
    avg_price: float
    verdict: str
    is_good_deal: bool
    summary: str


class CompareRequest(BaseModel):
    """Request to compare multiple options"""
    options: List[dict]  # List of {listing_id, listing_type, price}
    user_preferences: dict = {}


class CompareResponse(BaseModel):
    """Comparison of multiple options"""
    best_value: str  # listing_id of best value
    best_value_reason: str
    rankings: List[dict]
    summary: str


# ============================================
# Helper Functions
# ============================================

def calculate_verdict(current_price: float, avg_price: float) -> tuple[str, str]:
    """
    Calculate deal verdict based on price comparison.
    Returns (verdict, explanation)
    """
    if avg_price <= 0:
        return "UNKNOWN", "Unable to determine - no historical data"
    
    diff_percent = ((current_price - avg_price) / avg_price) * 100
    
    if diff_percent <= -20:
        return "EXCELLENT_DEAL", f"This is {abs(diff_percent):.0f}% below the 30-day average - an exceptional price that rarely occurs."
    elif diff_percent <= -10:
        return "GREAT_DEAL", f"At {abs(diff_percent):.0f}% below average, this is a strong deal worth booking."
    elif diff_percent <= -5:
        return "GOOD_DEAL", f"This price is {abs(diff_percent):.0f}% below average - a solid value."
    elif diff_percent <= 5:
        return "FAIR_PRICE", f"This is within {abs(diff_percent):.0f}% of the typical price - reasonable but not exceptional."
    else:
        return "ABOVE_AVERAGE", f"At {diff_percent:.0f}% above average, you might find better deals by waiting or searching alternatives."


def generate_mock_history(current_price: float, days: int = 30) -> List[PricePoint]:
    """Generate mock price history for demo"""
    import random
    
    history = []
    base_price = current_price * 1.1  # Assume current is slightly below base
    
    for i in range(days):
        date = (datetime.utcnow() - timedelta(days=days-i)).strftime("%Y-%m-%d")
        # Random variation +/- 15%
        variation = random.uniform(-0.15, 0.15)
        price = base_price * (1 + variation)
        history.append(PricePoint(date=date, price=round(price, 2)))
    
    return history


def analyze_trend(history: List[PricePoint]) -> str:
    """Analyze price trend from history"""
    if len(history) < 7:
        return "stable"
    
    # Compare last 7 days average to previous 7 days
    recent = sum(p.price for p in history[-7:]) / 7
    previous = sum(p.price for p in history[-14:-7]) / 7
    
    diff_percent = ((recent - previous) / previous) * 100
    
    if diff_percent > 5:
        return "rising"
    elif diff_percent < -5:
        return "falling"
    return "stable"


def generate_recommendation(verdict: str, trend: str, availability: int = 10) -> str:
    """Generate booking recommendation"""
    if verdict in ["EXCELLENT_DEAL", "GREAT_DEAL"]:
        if availability <= 3:
            return "Book now - excellent price with limited availability"
        return "Book soon - this is a strong deal"
    
    if verdict == "GOOD_DEAL":
        if trend == "rising":
            return "Consider booking - prices are trending up"
        return "Good value - safe to book"
    
    if verdict == "FAIR_PRICE":
        if trend == "falling":
            return "Prices dropping - consider waiting a few days"
        return "Reasonable price - book if dates are firm"
    
    # ABOVE_AVERAGE
    if trend == "falling":
        return "Wait if possible - prices are trending down"
    return "Consider alternatives or wait for a better deal"


# ============================================
# API Endpoints
# ============================================

@router.get("/analyze/{listing_type}/{listing_id}", response_model=PriceAnalysisResponse)
async def analyze_price(
    listing_type: str,
    listing_id: str,
    current_price: Optional[float] = Query(None, description="Current price to analyze")
):
    """
    Get full price analysis for a listing.
    
    Provides historical comparison, verdict, and recommendation.
    Implements "Decide with confidence" user journey.
    """
    logger.info(f"Analyzing price: {listing_type}/{listing_id}")
    
    # Try to get from deals cache
    deal = None
    if deals_cache:
        deal = deals_cache.get_deal(listing_id)
    
    # Use provided price or from deal
    if current_price is None:
        if deal:
            current_price = deal.current_price
        else:
            raise HTTPException(
                status_code=400, 
                detail="current_price required when listing not in cache"
            )
    
    # Get historical data
    if deal:
        avg_price = deal.avg_30d_price
        original_price = deal.original_price
        listing_name = deal.name
    else:
        avg_price = current_price * 1.12  # Assume 12% higher average
        original_price = current_price * 1.15
        listing_name = f"{listing_type.title()} {listing_id}"
    
    # Generate price history
    history = generate_mock_history(current_price)
    prices = [p.price for p in history]
    min_price = min(prices)
    max_price = max(prices)
    
    # Calculate verdict
    verdict, explanation = calculate_verdict(current_price, avg_price)
    diff_percent = ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
    
    # Analyze trend
    trend = analyze_trend(history)
    
    # Generate similar options (mock)
    similar_options = [
        SimilarOption(
            name=f"Alternative {listing_type} A",
            price=current_price * 1.05,
            difference=current_price * 0.05,
            difference_percent=5,
            pros=["Free cancellation", "Better location"],
            cons=["5% more expensive"]
        ),
        SimilarOption(
            name=f"Alternative {listing_type} B",
            price=current_price * 0.95,
            difference=-current_price * 0.05,
            difference_percent=-5,
            pros=["5% cheaper"],
            cons=["Lower rating", "No breakfast"]
        )
    ]
    
    # Generate recommendation
    availability = deal.availability if deal else 10
    recommendation = generate_recommendation(verdict, trend, availability)
    
    # Best time to book
    best_time = None
    if trend == "falling":
        best_time = "Prices trending down - wait 2-3 days if possible"
    elif trend == "rising":
        best_time = "Prices rising - book soon"
    
    return PriceAnalysisResponse(
        listing_id=listing_id,
        listing_type=listing_type,
        listing_name=listing_name,
        current_price=current_price,
        original_price=original_price,
        avg_30d_price=avg_price,
        min_30d_price=min_price,
        max_30d_price=max_price,
        price_vs_avg_percent=diff_percent,
        verdict=verdict,
        verdict_explanation=explanation,
        confidence=0.85,  # Mock confidence
        similar_options=similar_options,
        price_history=history[-14:],  # Last 2 weeks
        recommendation=recommendation,
        best_time_to_book=best_time,
        price_trend=trend,
        analyzed_at=datetime.utcnow().isoformat(),
        data_points=len(history)
    )


@router.get("/quick/{listing_type}/{listing_id}", response_model=QuickAnalysisResponse)
async def quick_analysis(
    listing_type: str,
    listing_id: str,
    current_price: float = Query(..., description="Current price")
):
    """
    Get quick verdict without full analysis.
    
    Faster response for UI badges/indicators.
    """
    # Estimate average (in production, would query historical data)
    avg_price = current_price * 1.12
    
    verdict, _ = calculate_verdict(current_price, avg_price)
    is_good = verdict in ["EXCELLENT_DEAL", "GREAT_DEAL", "GOOD_DEAL"]
    
    diff_percent = ((current_price - avg_price) / avg_price) * 100
    
    if diff_percent < 0:
        summary = f"{abs(diff_percent):.0f}% below average"
    else:
        summary = f"{diff_percent:.0f}% above average"
    
    return QuickAnalysisResponse(
        listing_id=listing_id,
        current_price=current_price,
        avg_price=avg_price,
        verdict=verdict,
        is_good_deal=is_good,
        summary=summary
    )


@router.post("/compare", response_model=CompareResponse)
async def compare_options(request: CompareRequest):
    """
    Compare multiple booking options.
    
    Helps users decide between alternatives.
    """
    if not request.options:
        raise HTTPException(status_code=400, detail="At least one option required")
    
    # Analyze each option
    analyzed = []
    for opt in request.options:
        listing_id = opt.get("listing_id", "unknown")
        price = opt.get("price", 0)
        
        # Estimate average
        avg_price = price * 1.1
        verdict, _ = calculate_verdict(price, avg_price)
        diff_percent = ((price - avg_price) / avg_price) * 100 if avg_price > 0 else 0
        
        # Calculate value score (lower price + better verdict = higher score)
        value_score = 100 - (price / 10) + (20 if verdict.startswith("EXCELLENT") else 
                                            10 if verdict.startswith("GREAT") else 
                                            5 if verdict.startswith("GOOD") else 0)
        
        analyzed.append({
            "listing_id": listing_id,
            "price": price,
            "verdict": verdict,
            "diff_percent": diff_percent,
            "value_score": value_score,
            "name": opt.get("name", listing_id)
        })
    
    # Rank by value score
    analyzed.sort(key=lambda x: x["value_score"], reverse=True)
    
    best = analyzed[0]
    best_reason = f"Best value at ${best['price']:.0f}"
    if best["diff_percent"] < -10:
        best_reason += f" ({abs(best['diff_percent']):.0f}% below average)"
    
    # Build rankings
    rankings = []
    for i, opt in enumerate(analyzed):
        rankings.append({
            "rank": i + 1,
            "listing_id": opt["listing_id"],
            "name": opt["name"],
            "price": opt["price"],
            "verdict": opt["verdict"],
            "value_score": round(opt["value_score"], 1)
        })
    
    # Summary
    if len(analyzed) == 1:
        summary = f"Only one option provided. Verdict: {analyzed[0]['verdict']}"
    else:
        price_range = max(a["price"] for a in analyzed) - min(a["price"] for a in analyzed)
        summary = f"Compared {len(analyzed)} options with ${price_range:.0f} price range. {best['name']} offers the best value."
    
    return CompareResponse(
        best_value=best["listing_id"],
        best_value_reason=best_reason,
        rankings=rankings,
        summary=summary
    )


@router.get("/bundle/{bundle_id}", response_model=PriceAnalysisResponse)
async def analyze_bundle_price(bundle_id: str):
    """
    Analyze price for a bundle (flight + hotel).
    
    Combines analysis of both components.
    """
    # In production, would fetch bundle from cache
    # For now, return mock analysis
    
    return PriceAnalysisResponse(
        listing_id=bundle_id,
        listing_type="bundle",
        listing_name=f"Bundle {bundle_id}",
        current_price=1200,
        original_price=1400,
        avg_30d_price=1350,
        min_30d_price=1150,
        max_30d_price=1500,
        price_vs_avg_percent=-11.1,
        verdict="GREAT_DEAL",
        verdict_explanation="This bundle is 11% below the 30-day average - a strong deal worth booking.",
        confidence=0.82,
        similar_options=[],
        price_history=[],
        recommendation="Book soon - this is a strong deal",
        best_time_to_book=None,
        price_trend="stable",
        analyzed_at=datetime.utcnow().isoformat(),
        data_points=30
    )


@router.get("/insights/{destination}")
async def get_destination_insights(
    destination: str,
    days_ahead: int = Query(30, ge=7, le=90)
):
    """
    Get pricing insights for a destination.
    
    Shows trends and best times to book.
    """
    # Mock insights
    return {
        "destination": destination,
        "avg_flight_price": 450,
        "avg_hotel_price_per_night": 180,
        "best_booking_window": "2-3 weeks ahead",
        "cheapest_days": ["Tuesday", "Wednesday"],
        "peak_season": "Dec-Feb" if destination in ["MIA", "CUN", "HNL"] else "Jun-Aug",
        "current_trend": "stable",
        "recommendation": f"Good time to book for {destination}",
        "generated_at": datetime.utcnow().isoformat()
    }
