"""
Deal Score Algorithm
Calculates a score (0-100) for each listing to identify deals

Algorithm Components:
1. Price Advantage Score (0-40 points) - Based on price drop vs 30-day average
2. Scarcity Score (0-30 points) - Based on availability/inventory
3. Rating Bonus (0-20 points) - Based on user ratings
4. Promotion Bonus (0-10 points) - If listing has active promotion
5. Reliability Score (0-10 points) - Based on historical on-time performance (flights only)

Total: 0-100 points (can exceed 100 with reliability bonus)
Threshold: 40+ is considered a "deal"
"""

from typing import NamedTuple, Optional
from loguru import logger
import os


class DealScoreBreakdown(NamedTuple):
    """
    Breakdown of deal score components for transparency
    """
    price_advantage_score: int
    scarcity_score: int
    rating_score: int
    promotion_score: int
    reliability_score: int
    total_score: int
    is_deal: bool
    
    def __repr__(self) -> str:
        return (
            f"DealScore(total={self.total_score}, "
            f"price={self.price_advantage_score}, "
            f"scarcity={self.scarcity_score}, "
            f"rating={self.rating_score}, "
            f"promo={self.promotion_score}, "
            f"reliability={self.reliability_score}, "
            f"is_deal={self.is_deal})"
        )


def calculate_deal_score(
    current_price: float,
    avg_30d_price: float,
    availability: int,
    rating: float,
    has_promotion: bool = False,
    threshold: int = 40,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    airline: Optional[str] = None
) -> DealScoreBreakdown:
    """
    Calculate comprehensive deal score for a listing
    
    Args:
        current_price: Current listing price
        avg_30d_price: 30-day average price
        availability: Number of items available
        rating: User rating (0-5 scale)
        has_promotion: Whether listing has active promotion
        threshold: Minimum score to be considered a deal (default: 40)
    
    Returns:
        DealScoreBreakdown: Named tuple with score breakdown
    
    Examples:
        >>> # Great deal: 30% off, limited stock, high rating
        >>> score = calculate_deal_score(200, 300, 2, 4.8, True)
        >>> print(score.total_score)  # Should be ~95
        95
        
        >>> # Not a deal: small discount, lots of stock
        >>> score = calculate_deal_score(290, 300, 50, 4.0, False)
        >>> print(score.is_deal)
        False
    """
    
    # ============================================
    # 1. Price Advantage Score (0-40 points)
    # ============================================
    price_advantage_score = _calculate_price_advantage(current_price, avg_30d_price)
    
    # ============================================
    # 2. Scarcity Score (0-30 points)
    # ============================================
    scarcity_score = _calculate_scarcity_score(availability)
    
    # ============================================
    # 3. Rating Bonus (0-20 points)
    # ============================================
    rating_score = _calculate_rating_score(rating)
    
    # ============================================
    # 4. Promotion Bonus (0-10 points)
    # ============================================
    promotion_score = 10 if has_promotion else 0
    
    # ============================================
    # 5. Reliability Score (0-10 points) - Flights only
    # ============================================
    reliability_score = 0
    if origin and destination:
        reliability_score = _calculate_reliability_score(origin, destination, airline)
    
    # ============================================
    # Calculate Total Score
    # ============================================
    total_score = min(
        price_advantage_score + scarcity_score + rating_score + promotion_score + reliability_score,
        100
    )
    
    is_deal_flag = total_score >= threshold
    
    breakdown = DealScoreBreakdown(
        price_advantage_score=price_advantage_score,
        scarcity_score=scarcity_score,
        rating_score=rating_score,
        promotion_score=promotion_score,
        reliability_score=reliability_score,
        total_score=total_score,
        is_deal=is_deal_flag
    )
    
    logger.debug(f"Deal score calculated: {breakdown}")
    
    return breakdown


def _calculate_price_advantage(current_price: float, avg_30d_price: float) -> int:
    """
    Calculate price advantage score (0-40 points)
    
    Logic:
    - 30%+ drop: 40 points (excellent deal)
    - 20-30% drop: 30 points (great deal)
    - 15-20% drop: 20 points (good deal)
    - <15% drop: 0 points (not a deal)
    
    Args:
        current_price: Current price
        avg_30d_price: 30-day average price
    
    Returns:
        int: Price advantage score (0-40)
    """
    if avg_30d_price <= 0:
        return 0
    
    # Calculate price drop percentage
    price_drop_pct = (avg_30d_price - current_price) / avg_30d_price
    
    if price_drop_pct >= 0.30:  # 30%+ drop
        return 40
    elif price_drop_pct >= 0.20:  # 20-30% drop
        return 30
    elif price_drop_pct >= 0.15:  # 15-20% drop (threshold from requirements)
        return 20
    else:  # <15% drop
        return 0


def _calculate_scarcity_score(availability: int) -> int:
    """
    Calculate scarcity score (0-30 points)
    
    Logic:
    - 1 item left: 30 points (extremely scarce)
    - 2 items: 25 points (very scarce)
    - 3-5 items: 15 points (limited)
    - 6+ items: 0 points (plenty available)
    
    Args:
        availability: Number of items available
    
    Returns:
        int: Scarcity score (0-30)
    """
    if availability == 1:
        return 30
    elif availability == 2:
        return 25
    elif 3 <= availability <= 5:
        return 15
    else:  # 6+ items
        return 0


def _calculate_rating_score(rating: float) -> int:
    """
    Calculate rating bonus score (0-20 points)
    
    Logic:
    - 4.8-5.0: 20 points (exceptional)
    - 4.5-4.7: 15 points (excellent)
    - 4.0-4.4: 10 points (good)
    - <4.0: 0 points (below threshold)
    
    Args:
        rating: User rating (0-5 scale)
    
    Returns:
        int: Rating score (0-20)
    """
    if rating >= 4.8:
        return 20
    elif rating >= 4.5:
        return 15
    elif rating >= 4.0:
        return 10
    else:
        return 0


def _calculate_reliability_score(origin: str, destination: str, airline: Optional[str] = None) -> int:
    """
    Calculate reliability score (0-10 points) based on historical on-time performance
    
    Logic:
    - 95%+ on-time: 10 points (excellent)
    - 85-95% on-time: 7 points (good)
    - 75-85% on-time: 5 points (fair)
    - <75% on-time: 0 points (poor)
    - No data: 5 points (neutral)
    
    Args:
        origin: Origin airport code (e.g., "SFO")
        destination: Destination airport code (e.g., "MIA")
        airline: Airline code (optional, for airline-specific reliability)
    
    Returns:
        int: Reliability score (0-10)
    """
    try:
        from pymongo import MongoClient
        
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        mongo_db = os.getenv("MONGO_DB", "kayak_doc")
        
        client = MongoClient(mongo_uri)
        db = client[mongo_db]
        
        # Query route reliability
        query = {
            "origin": origin.upper(),
            "destination": destination.upper()
        }
        
        reliability = db.route_reliability.find_one(query)
        
        if reliability:
            on_time_pct = reliability.get("on_time_percentage", 70.0)
            
            # If airline-specific data available, use it
            if airline and "airline_scores" in reliability:
                airline_scores = reliability.get("airline_scores", {})
                if airline in airline_scores:
                    on_time_pct = airline_scores[airline].get("on_time_pct", on_time_pct)
            
            # Convert percentage to score
            if on_time_pct >= 95:
                return 10
            elif on_time_pct >= 85:
                return 7
            elif on_time_pct >= 75:
                return 5
            else:
                return 0
        else:
            # No data available - return neutral score
            return 5
    
    except Exception as e:
        logger.debug(f"Could not calculate reliability score: {e}")
        return 5  # Neutral score if lookup fails


def is_deal(
    current_price: float,
    avg_30d_price: float,
    availability: int,
    rating: float,
    has_promotion: bool = False,
    threshold: int = 40
) -> bool:
    """
    Quick check if a listing is a deal (score >= threshold)
    
    Args:
        current_price: Current price
        avg_30d_price: 30-day average price
        availability: Number of items available
        rating: User rating
        has_promotion: Has active promotion
        threshold: Minimum score for deal (default: 40)
    
    Returns:
        bool: True if listing is a deal
    
    Example:
        >>> is_deal(200, 300, 2, 4.5)
        True
    """
    breakdown = calculate_deal_score(
        current_price, avg_30d_price, availability, rating, has_promotion, threshold
    )
    return breakdown.is_deal


# ============================================
# Utility Functions
# ============================================

def get_deal_quality(score: int) -> str:
    """
    Get human-readable deal quality description
    
    Args:
        score: Deal score (0-100)
    
    Returns:
        str: Quality description
    
    Example:
        >>> get_deal_quality(85)
        'Excellent Deal'
    """
    if score >= 80:
        return "Excellent Deal"
    elif score >= 60:
        return "Great Deal"
    elif score >= 40:
        return "Good Deal"
    else:
        return "Not a Deal"


def calculate_savings(current_price: float, avg_30d_price: float) -> tuple[float, float]:
    """
    Calculate savings amount and percentage
    
    Args:
        current_price: Current price
        avg_30d_price: Average price
    
    Returns:
        tuple: (savings_amount, savings_percentage)
    
    Example:
        >>> calculate_savings(200, 300)
        (100.0, 33.33)
    """
    savings_amount = max(0, avg_30d_price - current_price)
    savings_pct = (savings_amount / avg_30d_price * 100) if avg_30d_price > 0 else 0
    return round(savings_amount, 2), round(savings_pct, 2)


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    # Example 1: Excellent deal
    print("Example 1: Excellent Deal")
    score1 = calculate_deal_score(
        current_price=200,
        avg_30d_price=350,  # 43% discount
        availability=1,      # Last one!
        rating=5.0,
        has_promotion=True
    )
    print(f"Score: {score1.total_score}/100")
    print(f"Quality: {get_deal_quality(score1.total_score)}")
    print(f"Is Deal: {score1.is_deal}")
    print(f"Breakdown: {score1}\n")
    
    # Example 2: Not a deal
    print("Example 2: Not a Deal")
    score2 = calculate_deal_score(
        current_price=290,
        avg_30d_price=300,   # Only 3% discount
        availability=50,      # Plenty available
        rating=3.5,
        has_promotion=False
    )
    print(f"Score: {score2.total_score}/100")
    print(f"Quality: {get_deal_quality(score2.total_score)}")
    print(f"Is Deal: {score2.is_deal}")
    print(f"Breakdown: {score2}\n")
    
    # Example 3: Calculate savings
    print("Example 3: Savings Calculation")
    amount, pct = calculate_savings(200, 300)
    print(f"Savings: ${amount} ({pct}%)")
