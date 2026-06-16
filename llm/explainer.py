# llm/explainer.py
"""
Explainer module for generating structured explanations.
Implements:
- "Why this" (≤25 words): Explains why a recommendation is good
- "What to watch" (≤12 words): Highlights risks or things to monitor
- Price analysis for "Decide with confidence"
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from loguru import logger


@dataclass
class Explanation:
    """Structured explanation for a recommendation"""
    why_this: str  # ≤25 words
    what_to_watch: str  # ≤12 words


@dataclass
class PriceAnalysis:
    """Price analysis for 'Decide with confidence'"""
    current_price: float
    avg_30d_price: float
    avg_60d_price: Optional[float]
    price_vs_avg_percent: float  # Negative means below average (good)
    similar_options: List[Dict[str, Any]]
    verdict: str  # "EXCELLENT DEAL", "GREAT DEAL", "FAIR PRICE", "OVERPRICED"
    verdict_explanation: str


class Explainer:
    """
    Generates structured explanations for recommendations.
    Uses template-based approach with dynamic data insertion.
    """
    
    def __init__(self):
        # Templates for "Why this" explanations
        self.why_templates = {
            "price_drop": "{percent}% below 30-day average, saving ${savings:.0f}",
            "high_rating": "{rating:.1f} rating from {reviews} reviews",
            "good_location": "Great location in {neighborhood}",
            "amenities": "Includes {amenities}",
            "refundable": "Free cancellation available",
            "bundle_savings": "Bundle saves ${savings:.0f} vs booking separately",
            "limited_time": "Limited-time offer ends soon",
            "pet_friendly": "Pet-friendly accommodation",
            "direct_flight": "Direct flight, no layovers",
            "short_duration": "Quick {duration} flight"
        }
        
        # Templates for "What to watch" explanations
        self.watch_templates = {
            "low_inventory": "Only {count} left!",
            "price_rising": "Price trending up",
            "refund_deadline": "Cancel by {deadline}",
            "non_refundable": "Non-refundable rate",
            "layover": "{stops} stop(s), {layover_time}",
            "fees": "Extra fees: {fees}",
            "early_departure": "Early {time} departure",
            "red_eye": "Red-eye flight",
            "resort_fee": "${fee}/night resort fee"
        }
        
        # Verdict thresholds
        self.verdict_thresholds = {
            "excellent": -20,  # 20%+ below average
            "great": -10,      # 10-20% below average
            "good": -5,        # 5-10% below average
            "fair": 5,         # -5% to +5%
            "overpriced": 100  # 5%+ above average
        }
    
    def generate_explanation(self, recommendation: Dict[str, Any]) -> Explanation:
        """
        Generate "Why this" and "What to watch" for a recommendation.
        
        Args:
            recommendation: Dict containing flight/hotel details, scores, etc.
        
        Returns:
            Explanation with why_this (≤25 words) and what_to_watch (≤12 words)
        """
        why_parts = []
        watch_parts = []
        
        # Extract relevant data
        deal_score = recommendation.get("deal_score", 50)
        price = recommendation.get("total_price", 0)
        avg_price = recommendation.get("avg_30d_price", price)
        rating = recommendation.get("rating", 0)
        reviews = recommendation.get("review_count", 0)
        rooms_left = recommendation.get("rooms_left") or recommendation.get("seats_left")
        
        flight = recommendation.get("flight", {})
        hotel = recommendation.get("hotel", {})
        
        # === Generate "Why this" ===
        
        # Price advantage
        if avg_price > 0 and price < avg_price:
            savings = avg_price - price
            percent = int((savings / avg_price) * 100)
            if percent >= 5:
                why_parts.append(f"{percent}% below average, save ${savings:.0f}")
        
        # Rating
        if rating and rating >= 4.0:
            if reviews:
                why_parts.append(f"{rating:.1f} rating ({reviews} reviews)")
            else:
                why_parts.append(f"{rating:.1f} rating")
        
        # Bundle savings
        savings = recommendation.get("savings", 0)
        if savings > 0:
            why_parts.append(f"Bundle saves ${savings:.0f}")
        
        # Hotel amenities
        hotel_amenities = hotel.get("amenities", [])
        if hotel_amenities:
            top_amenities = hotel_amenities[:2]
            why_parts.append(f"Includes {', '.join(top_amenities)}")
        
        # Location
        neighborhood = hotel.get("neighborhood")
        if neighborhood:
            why_parts.append(f"Great location in {neighborhood}")
        
        # Refundable
        policy = hotel.get("policy", {})
        if policy.get("refundable"):
            why_parts.append("Free cancellation")
        
        # Direct flight
        stops = flight.get("stops", 0)
        if stops == 0:
            why_parts.append("Direct flight")
        
        # Combine and truncate to ~25 words
        why_this = self._combine_and_truncate(why_parts, max_words=25)
        
        # Default if empty
        if not why_this:
            why_this = f"Good value at ${price:.0f} with reliable quality"
        
        # === Generate "What to watch" ===
        
        # Low inventory
        if rooms_left and rooms_left <= 5:
            watch_parts.append(f"Only {rooms_left} left!")
        
        # Non-refundable
        if not policy.get("refundable", True):
            deadline = policy.get("refund_window")
            if deadline:
                watch_parts.append(f"Cancel by {deadline}")
            else:
                watch_parts.append("Non-refundable")
        
        # Layovers
        if stops > 0:
            watch_parts.append(f"{stops} stop(s)")
        
        # Resort fee
        resort_fee = hotel.get("resort_fee", 0)
        if resort_fee > 0:
            watch_parts.append(f"${resort_fee}/night resort fee")
        
        # Early departure
        departure_time = flight.get("departure_time", "")
        if departure_time:
            try:
                if isinstance(departure_time, str):
                    hour = int(departure_time.split("T")[1].split(":")[0]) if "T" in departure_time else 12
                else:
                    hour = departure_time.hour
                if hour < 6:
                    watch_parts.append("Red-eye flight")
                elif hour < 8:
                    watch_parts.append("Early morning departure")
            except:
                pass
        
        # Combine and truncate to ~12 words
        what_to_watch = self._combine_and_truncate(watch_parts, max_words=12)
        
        # Default if empty
        if not what_to_watch:
            what_to_watch = "Book soon, prices may change"
        
        return Explanation(why_this=why_this, what_to_watch=what_to_watch)
    
    def _combine_and_truncate(self, parts: List[str], max_words: int) -> str:
        """Combine parts and truncate to max words"""
        if not parts:
            return ""
        
        combined = ", ".join(parts[:3])  # Max 3 parts
        words = combined.split()
        
        if len(words) > max_words:
            # Truncate to max words
            combined = " ".join(words[:max_words])
            # Remove trailing comma if present
            if combined.endswith(","):
                combined = combined[:-1]
        
        return combined
    
    def generate_price_analysis(
        self,
        current_price: float,
        avg_30d_price: float,
        avg_60d_price: Optional[float] = None,
        similar_options: Optional[List[Dict[str, Any]]] = None
    ) -> PriceAnalysis:
        """
        Generate price analysis for 'Decide with confidence'.
        
        Args:
            current_price: Current listing price
            avg_30d_price: 30-day rolling average price
            avg_60d_price: Optional 60-day average
            similar_options: List of similar listings with prices
        
        Returns:
            PriceAnalysis with verdict and comparison data
        """
        # Calculate percentage difference
        if avg_30d_price > 0:
            price_vs_avg = ((current_price - avg_30d_price) / avg_30d_price) * 100
        else:
            price_vs_avg = 0
        
        # Determine verdict
        if price_vs_avg <= self.verdict_thresholds["excellent"]:
            verdict = "EXCELLENT DEAL"
            verdict_explanation = f"This is {abs(price_vs_avg):.0f}% below the 30-day average - an exceptional price!"
        elif price_vs_avg <= self.verdict_thresholds["great"]:
            verdict = "GREAT DEAL"
            verdict_explanation = f"This is {abs(price_vs_avg):.0f}% below average - a solid deal."
        elif price_vs_avg <= self.verdict_thresholds["good"]:
            verdict = "GOOD DEAL"
            verdict_explanation = f"This is {abs(price_vs_avg):.0f}% below average - decent savings."
        elif price_vs_avg <= self.verdict_thresholds["fair"]:
            verdict = "FAIR PRICE"
            verdict_explanation = "This is around the typical price for this listing."
        else:
            verdict = "ABOVE AVERAGE"
            verdict_explanation = f"This is {price_vs_avg:.0f}% above the 30-day average. Consider waiting for a better deal."
        
        # Add similar options comparison if provided
        if similar_options:
            similar_count = len(similar_options)
            similar_prices = [opt.get("price", 0) for opt in similar_options]
            if similar_prices:
                avg_similar = sum(similar_prices) / len(similar_prices)
                min_similar = min(similar_prices)
                max_similar = max(similar_prices)
                
                if current_price < min_similar:
                    verdict_explanation += f" This is the cheapest among {similar_count} similar options (${min_similar:.0f}-${max_similar:.0f})."
                elif current_price < avg_similar:
                    verdict_explanation += f" Below average vs {similar_count} similar options."
        
        return PriceAnalysis(
            current_price=current_price,
            avg_30d_price=avg_30d_price,
            avg_60d_price=avg_60d_price,
            price_vs_avg_percent=price_vs_avg,
            similar_options=similar_options or [],
            verdict=verdict,
            verdict_explanation=verdict_explanation
        )
    
    def generate_change_summary(
        self,
        changes: List[Dict[str, Any]],
        constraints_applied: List[str]
    ) -> str:
        """
        Generate summary for 'Refine without starting over'.
        
        Args:
            changes: List of changes from previous recommendation
            constraints_applied: New constraints that were applied
        
        Returns:
            Human-readable summary of changes
        """
        if constraints_applied:
            constraints_text = ", ".join(constraints_applied)
            summary = f"Updated based on: {constraints_text}"
        else:
            summary = "Updated recommendations"
        
        # Count improvements vs tradeoffs
        improvements = [c for c in changes if c.get("is_improvement")]
        tradeoffs = [c for c in changes if not c.get("is_improvement")]
        
        if improvements and tradeoffs:
            summary += f". {len(improvements)} improvements, {len(tradeoffs)} trade-offs."
        elif improvements:
            summary += f". {len(improvements)} improvements made."
        elif tradeoffs:
            summary += f". {len(tradeoffs)} trade-offs to consider."
        
        return summary
    
    def format_policy_info(self, policy: Dict[str, Any]) -> str:
        """
        Format policy information for display.
        
        Args:
            policy: Policy dict with refundable, pet_friendly, etc.
        
        Returns:
            Formatted string of policy highlights
        """
        parts = []
        
        if policy.get("refundable"):
            deadline = policy.get("refund_window", "before check-in")
            parts.append(f"Refundable until {deadline}")
        else:
            parts.append("Non-refundable")
        
        if policy.get("pet_friendly"):
            fee = policy.get("pet_fee")
            if fee:
                parts.append(f"Pets OK (+${fee})")
            else:
                parts.append("Pets allowed")
        
        parking = policy.get("parking")
        if parking:
            parts.append(f"Parking: {parking}")
        
        if policy.get("breakfast"):
            fee = policy.get("breakfast_fee")
            if fee:
                parts.append(f"Breakfast +${fee}")
            else:
                parts.append("Breakfast included")
        
        if policy.get("wifi"):
            fee = policy.get("wifi_fee")
            if fee:
                parts.append(f"WiFi +${fee}")
            else:
                parts.append("Free WiFi")
        
        return " | ".join(parts) if parts else "Standard policies apply"


# ============================================
# Global Instance
# ============================================

explainer = Explainer()


# ============================================
# Convenience Functions
# ============================================

def generate_explanation(recommendation: Dict[str, Any]) -> Dict[str, str]:
    """Generate explanation dict for a recommendation"""
    exp = explainer.generate_explanation(recommendation)
    return {
        "why_this": exp.why_this,
        "what_to_watch": exp.what_to_watch
    }


def generate_price_analysis(
    current_price: float,
    avg_30d_price: float,
    avg_60d_price: Optional[float] = None,
    similar_options: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Generate price analysis dict"""
    analysis = explainer.generate_price_analysis(
        current_price, avg_30d_price, avg_60d_price, similar_options
    )
    return {
        "current_price": analysis.current_price,
        "avg_30d_price": analysis.avg_30d_price,
        "avg_60d_price": analysis.avg_60d_price,
        "price_vs_avg_percent": analysis.price_vs_avg_percent,
        "similar_options": analysis.similar_options,
        "verdict": analysis.verdict,
        "verdict_explanation": analysis.verdict_explanation
    }


def format_policy(policy: Dict[str, Any]) -> str:
    """Format policy info for display"""
    return explainer.format_policy_info(policy)
