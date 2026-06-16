"""
Fit Score Algorithm
Calculates how well a bundle matches user requirements (0.0-1.0)

Algorithm Components:
1. Price Match (40%) - How close to user's budget
2. Amenity Match (30%) - How many required amenities are satisfied
3. Location Score (20%) - Hotel location quality
4. Policy Match (10%) - Cancellation/pet policies

Total: 0.0-1.0 (0% to 100% match)
"""

from typing import NamedTuple, List, Dict, Any, Optional
from loguru import logger


class FitScoreBreakdown(NamedTuple):
    """
    Breakdown of fit score components
    """
    price_match_score: float      # 0.0-0.4
    amenity_match_score: float    # 0.0-0.3
    location_score: float          # 0.0-0.2
    policy_match_score: float     # 0.0-0.1
    total_fit_score: float        # 0.0-1.0
    
    def __repr__(self) -> str:
        return (
            f"FitScore(total={self.total_fit_score:.2f}, "
            f"price={self.price_match_score:.2f}, "
            f"amenity={self.amenity_match_score:.2f}, "
            f"location={self.location_score:.2f}, "
            f"policy={self.policy_match_score:.2f})"
        )


def calculate_fit_score(
    bundle_price: float,
    user_budget: Optional[float],
    hotel_amenities: List[str],
    required_amenities: List[str],
    hotel_location: Dict[str, Any],
    hotel_policies: Dict[str, Any],
    user_preferences: Dict[str, Any]
) -> FitScoreBreakdown:
    """
    Calculate how well a bundle fits user requirements
    
    Args:
        bundle_price: Total price of flight + hotel bundle
        user_budget: User's maximum budget (None = no budget constraint)
        hotel_amenities: List of hotel amenities (e.g., ["wifi", "pool", "breakfast"])
        required_amenities: User's required amenities
        hotel_location: Dict with keys: near_transit, city_center, near_airport
        hotel_policies: Dict with keys: cancellation, pets
        user_preferences: Dict with preference flags
    
    Returns:
        FitScoreBreakdown: Detailed fit score breakdown
    
    Example:
        >>> fit = calculate_fit_score(
        ...     bundle_price=500,
        ...     user_budget=550,
        ...     hotel_amenities=["wifi", "pool", "breakfast"],
        ...     required_amenities=["wifi", "pool"],
        ...     hotel_location={"near_transit": True, "city_center": True},
        ...     hotel_policies={"cancellation": "refundable", "pets": True},
        ...     user_preferences={"refundable": True, "pet_friendly": True}
        ... )
        >>> print(f"Fit score: {fit.total_fit_score:.2%}")
        Fit score: 92%
    """
    
    # ============================================
    # 1. Price Match Score (0.0-0.4)
    # ============================================
    price_score = _calculate_price_match(bundle_price, user_budget)
    
    # ============================================
    # 2. Amenity Match Score (0.0-0.3)
    # ============================================
    amenity_score = _calculate_amenity_match(hotel_amenities, required_amenities)
    
    # ============================================
    # 3. Location Score (0.0-0.2)
    # ============================================
    location_score = _calculate_location_score(hotel_location)
    
    # ============================================
    # 4. Policy Match Score (0.0-0.1)
    # ============================================
    policy_score = _calculate_policy_match(hotel_policies, user_preferences)
    
    # ============================================
    # Calculate Total Fit Score
    # ============================================
    total_fit_score = min(
        price_score + amenity_score + location_score + policy_score,
        1.0
    )
    
    breakdown = FitScoreBreakdown(
        price_match_score=price_score,
        amenity_match_score=amenity_score,
        location_score=location_score,
        policy_match_score=policy_score,
        total_fit_score=total_fit_score
    )
    
    logger.debug(f"Fit score calculated: {breakdown}")
    
    return breakdown


def _calculate_price_match(bundle_price: float, user_budget: Optional[float]) -> float:
    """
    Calculate price match score (0.0-0.4)
    
    Logic:
    - Within $50 of budget: 0.40 (perfect)
    - Within $100: 0.30 (good)
    - Within $200: 0.20 (acceptable)
    - Over $200 or under budget: 0.10 (poor)
    - No budget specified: 0.30 (neutral)
    
    Args:
        bundle_price: Total bundle price
        user_budget: User's budget (None = no constraint)
    
    Returns:
        float: Price match score (0.0-0.4)
    """
    if user_budget is None:
        return 0.30  # Neutral score when no budget specified
    
    price_diff = abs(bundle_price - user_budget)
    
    if price_diff <= 50:
        return 0.40  # Within $50
    elif price_diff <= 100:
        return 0.30  # Within $100
    elif price_diff <= 200:
        return 0.20  # Within $200
    else:
        return 0.10  # Over $200 difference


def _calculate_amenity_match(
    hotel_amenities: List[str],
    required_amenities: List[str]
) -> float:
    """
    Calculate amenity match score (0.0-0.3)
    
    Logic:
    - All required amenities present: 0.30 (perfect)
    - Partial match: proportional score
    - No required amenities: 0.30 (neutral)
    
    Args:
        hotel_amenities: List of hotel amenities
        required_amenities: List of required amenities
    
    Returns:
        float: Amenity match score (0.0-0.3)
    """
    if not required_amenities:
        return 0.30  # No requirements = neutral score
    
    # Convert to lowercase sets for comparison
    hotel_set = set(a.lower() for a in hotel_amenities)
    required_set = set(a.lower() for a in required_amenities)
    
    # Calculate match percentage
    matched = hotel_set & required_set
    match_ratio = len(matched) / len(required_set)
    
    return 0.30 * match_ratio


def _calculate_location_score(hotel_location: Dict[str, Any]) -> float:
    """
    Calculate location score (0.0-0.2)
    
    Logic:
    - City center + near transit: 0.20 (best)
    - City center or near transit: 0.15 (good)
    - Near airport only: 0.10 (okay)
    - None of above: 0.05 (poor)
    
    Args:
        hotel_location: Dict with location attributes
    
    Returns:
        float: Location score (0.0-0.2)
    """
    near_transit = hotel_location.get("near_transit", False)
    city_center = hotel_location.get("city_center", False)
    near_airport = hotel_location.get("near_airport", False)
    
    if city_center and near_transit:
        return 0.20  # Best location
    elif city_center or near_transit:
        return 0.15  # Good location
    elif near_airport:
        return 0.10  # Okay location
    else:
        return 0.05  # Poor location


def _calculate_policy_match(
    hotel_policies: Dict[str, Any],
    user_preferences: Dict[str, Any]
) -> float:
    """
    Calculate policy match score (0.0-0.1)
    
    Logic:
    - Check refundable and pet-friendly preferences
    - 0.05 points for each matched policy
    
    Args:
        hotel_policies: Dict with policy info
        user_preferences: Dict with user preference flags
    
    Returns:
        float: Policy match score (0.0-0.1)
    """
    score = 0.0
    
    # Check refundable preference
    if user_preferences.get("refundable", False):
        if hotel_policies.get("cancellation") == "refundable":
            score += 0.05
    
    # Check pet-friendly preference
    if user_preferences.get("pet_friendly", False):
        if hotel_policies.get("pets", False):
            score += 0.05
    
    return score


# ============================================
# Utility Functions
# ============================================

def get_fit_quality(fit_score: float) -> str:
    """
    Get human-readable fit quality description
    
    Args:
        fit_score: Fit score (0.0-1.0)
    
    Returns:
        str: Quality description
    
    Example:
        >>> get_fit_quality(0.85)
        'Excellent Match'
    """
    if fit_score >= 0.85:
        return "Excellent Match"
    elif fit_score >= 0.70:
        return "Great Match"
    elif fit_score >= 0.55:
        return "Good Match"
    elif fit_score >= 0.40:
        return "Fair Match"
    else:
        return "Poor Match"


def parse_user_constraints(constraints: List[str]) -> Dict[str, Any]:
    """
    Parse user constraints into structured preferences
    
    Args:
        constraints: List of constraint strings (e.g., ["wifi", "pet-friendly", "refundable"])
    
    Returns:
        dict: Structured preferences
    
    Example:
        >>> parse_user_constraints(["wifi", "pool", "pet-friendly", "refundable"])
        {
            'required_amenities': ['wifi', 'pool'],
            'refundable': True,
            'pet_friendly': True
        }
    """
    amenities = []
    preferences = {}
    
    for constraint in constraints:
        constraint_lower = constraint.lower().replace(" ", "")
        
        if constraint_lower in ["refundable", "flexible"]:
            preferences["refundable"] = True
        elif "pet" in constraint_lower:
            preferences["pet_friendly"] = True
        else:
            # Treat as amenity
            amenities.append(constraint_lower)
    
    return {
        "required_amenities": amenities,
        **preferences
    }


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    # Example 1: Perfect match
    print("Example 1: Excellent Match")
    fit1 = calculate_fit_score(
        bundle_price=480,
        user_budget=500,
        hotel_amenities=["wifi", "pool", "breakfast", "gym"],
        required_amenities=["wifi", "pool"],
        hotel_location={"near_transit": True, "city_center": True, "near_airport": False},
        hotel_policies={"cancellation": "refundable", "pets": True},
        user_preferences={"refundable": True, "pet_friendly": True}
    )
    print(f"Fit Score: {fit1.total_fit_score:.2%}")
    print(f"Quality: {get_fit_quality(fit1.total_fit_score)}")
    print(f"Breakdown: {fit1}\n")
    
    # Example 2: Poor match
    print("Example 2: Poor Match")
    fit2 = calculate_fit_score(
        bundle_price=900,
        user_budget=500,
        hotel_amenities=["wifi"],
        required_amenities=["wifi", "pool", "breakfast"],
        hotel_location={"near_transit": False, "city_center": False, "near_airport": True},
        hotel_policies={"cancellation": "non-refundable", "pets": False},
        user_preferences={"refundable": True, "pet_friendly": True}
    )
    print(f"Fit Score: {fit2.total_fit_score:.2%}")
    print(f"Quality: {get_fit_quality(fit2.total_fit_score)}")
    print(f"Breakdown: {fit2}\n")
    
    # Example 3: Parse constraints
    print("Example 3: Parse User Constraints")
    constraints = ["wifi", "pool", "pet-friendly", "refundable"]
    parsed = parse_user_constraints(constraints)
    print(f"Parsed preferences: {parsed}")
