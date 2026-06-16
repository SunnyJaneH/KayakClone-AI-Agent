"""
Bundle Matcher - Travel Bundle Recommendation Engine
Combines flights and hotels to create optimal bundles based on:
1. Deal Score - How good the deal is
2. Fit Score - How well it matches user requirements
"""

from typing import List, Dict, Any, Optional, NamedTuple
from dataclasses import dataclass
from loguru import logger

from .deal_scorer import calculate_deal_score, DealScoreBreakdown
from .fit_scorer import calculate_fit_score, FitScoreBreakdown, parse_user_constraints


@dataclass
class Flight:
    """Flight data structure"""
    listingId: str
    departure: str
    arrival: str
    date: str
    airline: str
    price: float
    avg_30d_price: float
    availability: int
    rating: float
    duration: int  # minutes
    stops: int
    has_promotion: bool = False


@dataclass
class Hotel:
    """Hotel data structure"""
    listingId: str
    hotelName: str
    city: str
    price: float
    avg_30d_price: float
    availability: int
    rating: float
    starRating: float
    amenities: List[str]
    policies: Dict[str, Any]
    location: Dict[str, Any]
    has_promotion: bool = False


@dataclass
class Bundle:
    """Flight + Hotel bundle with scores"""
    bundleId: str
    flight: Flight
    hotel: Hotel
    total_price: float
    savings: float
    deal_score: DealScoreBreakdown
    fit_score: FitScoreBreakdown
    combined_score: float  # Weighted combination of deal + fit
    explanation: str = ""


class UserQuery(NamedTuple):
    """Structured user query"""
    origin: Optional[str] = None
    destination: Optional[str] = None
    dates: Optional[List[str]] = None
    budget: Optional[float] = None
    constraints: List[str] = []  # e.g., ["wifi", "pet-friendly", "refundable"]


class BundleMatcher:
    """
    Bundle recommendation engine
    
    Usage:
        matcher = BundleMatcher()
        bundles = matcher.find_best_bundles(
            flights=all_flights,
            hotels=all_hotels,
            user_query=user_query,
            top_k=3
        )
    """
    
    def __init__(
        self,
        deal_weight: float = 0.4,
        fit_weight: float = 0.6,
        min_deal_score: int = 40
    ):
        """
        Initialize Bundle Matcher
        
        Args:
            deal_weight: Weight for deal score (default: 0.4)
            fit_weight: Weight for fit score (default: 0.6)
            min_deal_score: Minimum deal score to consider (default: 40)
        """
        self.deal_weight = deal_weight
        self.fit_weight = fit_weight
        self.min_deal_score = min_deal_score
        
        logger.info(
            f"BundleMatcher initialized: "
            f"deal_weight={deal_weight}, fit_weight={fit_weight}, "
            f"min_deal_score={min_deal_score}"
        )
    
    def find_best_bundles(
        self,
        flights: List[Flight],
        hotels: List[Hotel],
        user_query: UserQuery,
        top_k: int = 3
    ) -> List[Bundle]:
        """
        Find best flight+hotel bundles for user
        
        Args:
            flights: List of available flights
            hotels: List of available hotels
            user_query: User's structured query
            top_k: Number of bundles to return
        
        Returns:
            List[Bundle]: Top K bundles sorted by combined score
        """
        logger.info(
            f"Finding bundles: {len(flights)} flights × {len(hotels)} hotels = "
            f"{len(flights) * len(hotels)} combinations"
        )
        
        # Filter flights and hotels by destination
        filtered_flights = self._filter_flights(flights, user_query)
        filtered_hotels = self._filter_hotels(hotels, user_query)
        
        logger.info(
            f"After filtering: {len(filtered_flights)} flights, {len(filtered_hotels)} hotels"
        )
        
        # Generate all possible bundles
        bundles = []
        for flight in filtered_flights:
            for hotel in filtered_hotels:
                bundle = self._create_bundle(flight, hotel, user_query)
                if bundle:
                    bundles.append(bundle)
        
        logger.info(f"Generated {len(bundles)} valid bundles")
        
        # Sort by combined score and return top K
        bundles.sort(key=lambda b: b.combined_score, reverse=True)
        top_bundles = bundles[:top_k]
        
        logger.info(
            f"Returning top {len(top_bundles)} bundles "
            f"(scores: {[f'{b.combined_score:.2f}' for b in top_bundles]})"
        )
        
        return top_bundles
    
    def _filter_flights(self, flights: List[Flight], query: UserQuery) -> List[Flight]:
        """Filter flights by user query"""
        filtered = flights
        
        if query.destination:
            filtered = [
                f for f in filtered
                if f.arrival.lower() == query.destination.lower()
            ]
        
        if query.origin:
            filtered = [
                f for f in filtered
                if f.departure.lower() == query.origin.lower()
            ]
        
        return filtered
    
    def _filter_hotels(self, hotels: List[Hotel], query: UserQuery) -> List[Hotel]:
        """Filter hotels by user query"""
        filtered = hotels
        
        if query.destination:
            filtered = [
                h for h in filtered
                if h.city.lower() == query.destination.lower()
            ]
        
        return filtered
    
    def _create_bundle(
        self,
        flight: Flight,
        hotel: Hotel,
        user_query: UserQuery
    ) -> Optional[Bundle]:
        """
        Create and score a bundle
        
        Returns:
            Bundle if valid, None if doesn't meet criteria
        """
        # Calculate total price and savings
        total_price = flight.price + hotel.price
        total_avg_price = flight.avg_30d_price + hotel.avg_30d_price
        savings = max(0, total_avg_price - total_price)
        
        # Calculate Deal Score (average of flight and hotel)
        flight_deal = calculate_deal_score(
            flight.price,
            flight.avg_30d_price,
            flight.availability,
            flight.rating,
            flight.has_promotion
        )
        
        hotel_deal = calculate_deal_score(
            hotel.price,
            hotel.avg_30d_price,
            hotel.availability,
            hotel.rating,
            hotel.has_promotion
        )
        
        # Average deal score
        avg_deal_score = (flight_deal.total_score + hotel_deal.total_score) / 2
        
        # Skip if deal score too low
        if avg_deal_score < self.min_deal_score:
            return None
        
        # Create combined deal breakdown
        combined_deal = DealScoreBreakdown(
            price_advantage_score=(flight_deal.price_advantage_score + hotel_deal.price_advantage_score) // 2,
            scarcity_score=(flight_deal.scarcity_score + hotel_deal.scarcity_score) // 2,
            rating_score=(flight_deal.rating_score + hotel_deal.rating_score) // 2,
            promotion_score=(flight_deal.promotion_score + hotel_deal.promotion_score) // 2,
            total_score=int(avg_deal_score),
            is_deal=avg_deal_score >= self.min_deal_score
        )
        
        # Calculate Fit Score
        parsed_prefs = parse_user_constraints(user_query.constraints)
        
        fit = calculate_fit_score(
            bundle_price=total_price,
            user_budget=user_query.budget,
            hotel_amenities=hotel.amenities,
            required_amenities=parsed_prefs.get("required_amenities", []),
            hotel_location=hotel.location,
            hotel_policies=hotel.policies,
            user_preferences=parsed_prefs
        )
        
        # Calculate combined score
        combined = (
            self.deal_weight * (combined_deal.total_score / 100) +
            self.fit_weight * fit.total_fit_score
        )
        
        # Generate explanation
        explanation = self._generate_explanation(
            flight, hotel, combined_deal, fit, savings
        )
        
        bundle = Bundle(
            bundleId=f"bundle-{flight.listingId}-{hotel.listingId}",
            flight=flight,
            hotel=hotel,
            total_price=round(total_price, 2),
            savings=round(savings, 2),
            deal_score=combined_deal,
            fit_score=fit,
            combined_score=round(combined, 3),
            explanation=explanation
        )
        
        return bundle
    
    def _generate_explanation(
        self,
        flight: Flight,
        hotel: Hotel,
        deal: DealScoreBreakdown,
        fit: FitScoreBreakdown,
        savings: float
    ) -> str:
        """
        Generate human-readable explanation for why this bundle was recommended
        
        Max 2-3 sentences
        """
        parts = []
        
        # Deal quality
        if deal.total_score >= 80:
            parts.append(f"Excellent deal with ${savings:.0f} savings")
        elif deal.total_score >= 60:
            parts.append(f"Great value saving ${savings:.0f}")
        
        # Scarcity
        if deal.scarcity_score >= 25:
            parts.append("limited availability")
        
        # Rating
        if deal.rating_score >= 15:
            parts.append("highly rated")
        
        # Fit quality
        if fit.total_fit_score >= 0.85:
            parts.append("perfect match for your needs")
        elif fit.total_fit_score >= 0.70:
            parts.append("great fit")
        
        explanation = f"{flight.airline} to {hotel.city} with {hotel.starRating}★ {hotel.hotelName}"
        if parts:
            explanation += " - " + ", ".join(parts[:2])
        
        return explanation


# ============================================
# Convenience Function
# ============================================

def find_best_bundles(
    flights: List[Dict[str, Any]],
    hotels: List[Dict[str, Any]],
    user_query: Dict[str, Any],
    top_k: int = 3,
    deal_weight: float = 0.4,
    fit_weight: float = 0.6
) -> List[Dict[str, Any]]:
    """
    Convenience function to find best bundles from raw dicts
    
    Args:
        flights: List of flight dicts
        hotels: List of hotel dicts
        user_query: User query dict
        top_k: Number of results
        deal_weight: Deal score weight
        fit_weight: Fit score weight
    
    Returns:
        List[dict]: Bundle results as dicts
    """
    # Convert dicts to dataclasses
    flight_objs = [Flight(**f) for f in flights]
    hotel_objs = [Hotel(**h) for h in hotels]
    query_obj = UserQuery(**user_query)
    
    # Find bundles
    matcher = BundleMatcher(deal_weight=deal_weight, fit_weight=fit_weight)
    bundles = matcher.find_best_bundles(flight_objs, hotel_objs, query_obj, top_k)
    
    # Convert back to dicts
    results = []
    for bundle in bundles:
        results.append({
            "bundleId": bundle.bundleId,
            "totalPrice": bundle.total_price,
            "savings": bundle.savings,
            "dealScore": bundle.deal_score.total_score,
            "fitScore": bundle.fit_score.total_fit_score,
            "combinedScore": bundle.combined_score,
            "explanation": bundle.explanation,
            "flight": {
                "listingId": bundle.flight.listingId,
                "airline": bundle.flight.airline,
                "departure": bundle.flight.departure,
                "arrival": bundle.flight.arrival,
                "price": bundle.flight.price
            },
            "hotel": {
                "listingId": bundle.hotel.listingId,
                "hotelName": bundle.hotel.hotelName,
                "city": bundle.hotel.city,
                "starRating": bundle.hotel.starRating,
                "price": bundle.hotel.price
            }
        })
    
    return results


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    # Example flights and hotels
    flights = [
        Flight(
            listingId="flight-001",
            departure="SFO",
            arrival="MIA",
            date="2025-11-15",
            airline="United",
            price=280,
            avg_30d_price=350,
            availability=3,
            rating=4.5,
            duration=360,
            stops=0
        )
    ]
    
    hotels = [
        Hotel(
            listingId="hotel-001",
            hotelName="Grand Hyatt Miami",
            city="MIA",
            price=150,
            avg_30d_price=200,
            availability=2,
            rating=4.8,
            starRating=4.5,
            amenities=["wifi", "pool", "breakfast"],
            policies={"cancellation": "refundable", "pets": True},
            location={"near_transit": True, "city_center": True, "near_airport": False}
        )
    ]
    
    # Example user query
    query = UserQuery(
        origin="SFO",
        destination="MIA",
        budget=500,
        constraints=["wifi", "pool", "refundable"]
    )
    
    # Find best bundles
    matcher = BundleMatcher()
    bundles = matcher.find_best_bundles(flights, hotels, query, top_k=1)
    
    # Display results
    for i, bundle in enumerate(bundles, 1):
        print(f"\n=== Bundle {i} ===")
        print(f"Price: ${bundle.total_price} (save ${bundle.savings})")
        print(f"Deal Score: {bundle.deal_score.total_score}/100")
        print(f"Fit Score: {bundle.fit_score.total_fit_score:.0%}")
        print(f"Combined: {bundle.combined_score:.2f}")
        print(f"Explanation: {bundle.explanation}")
