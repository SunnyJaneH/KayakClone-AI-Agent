"""
Bundle Builder for Concierge Agent
Builds flight+hotel bundles from cached deals using real Kaggle data
"""

import os
import sys
from typing import List, Dict, Any, Optional, Tuple
from pymongo import MongoClient
from datetime import datetime, timedelta
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import config, fallback to environment variables
try:
    from config import settings
    MONGO_URI = settings.MONGO_URI
    MONGO_DB_SEARCH = settings.MONGO_DB_SEARCH
except ImportError:
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    MONGO_DB_SEARCH = os.getenv('MONGO_DB_SEARCH', 'kayak_doc')

try:
    from agents.deal_scorer import DealScorer
except ImportError:
    # Fallback if import fails
    DealScorer = None

logger = logging.getLogger(__name__)

class BundleBuilder:
    """
    Builds flight+hotel bundles from real dataset deals
    Computes Fit Score based on price, amenities, location
    """
    
    def __init__(self):
        self.mongo_client = MongoClient(MONGO_URI)
        self.mongo_db = self.mongo_client[MONGO_DB_SEARCH]
        self.deal_scorer = DealScorer() if DealScorer else None
    
    def compute_fit_score(self, bundle: Dict[str, Any], user_budget: float, 
                         user_preferences: Dict[str, Any]) -> float:
        """
        Compute Fit Score (0-100) for a bundle
        Factors:
        - Price vs budget/median (40%)
        - Amenity/policy match (30%)
        - Location tag relevance (30%)
        """
        score = 0.0
        
        # 1. Price fit (40 points)
        total_price = bundle.get('total_price', 0)
        if user_budget > 0:
            price_ratio = min(1.0, user_budget / total_price) if total_price > 0 else 0
            score += price_ratio * 40
        else:
            # Compare to median
            median_price = bundle.get('median_price', total_price * 1.2)
            if total_price <= median_price:
                score += 40
            else:
                discount = (median_price / total_price) * 40
                score += discount
        
        # 2. Amenity/policy match (30 points)
        preferred_amenities = user_preferences.get('amenities', [])
        bundle_amenities = bundle.get('amenities', [])
        
        if preferred_amenities:
            matches = sum(1 for a in preferred_amenities if a.lower() in [b.lower() for b in bundle_amenities])
            match_ratio = matches / len(preferred_amenities) if preferred_amenities else 0
            score += match_ratio * 30
        else:
            score += 15  # Neutral score if no preferences
        
        # 3. Location tag relevance (30 points)
        preferred_location = user_preferences.get('location', '').lower()
        bundle_location = bundle.get('location', '').lower()
        
        if preferred_location and bundle_location:
            if preferred_location in bundle_location or bundle_location in preferred_location:
                score += 30
            elif any(word in bundle_location for word in preferred_location.split()):
                score += 20
            else:
                score += 10
        else:
            score += 15  # Neutral score
        
        return min(100, max(0, round(score, 1)))
    
    def build_bundles(self, origin: str, destination: str, 
                     start_date: datetime, end_date: datetime,
                     user_budget: float = 0,
                     user_preferences: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Build flight+hotel bundles from cached deals
        Uses real data from MongoDB collections
        """
        if user_preferences is None:
            user_preferences = {}
        
        bundles = []
        
        # Get flights for route
        flights = list(self.mongo_db.flights.find({
            'origin': origin.upper(),
            'destination': destination.upper(),
            'departureTime': {
                '$gte': start_date,
                '$lt': start_date + timedelta(days=1)
            }
        }).limit(10))
        
        if not flights:
            logger.warning(f"No flights found for {origin} → {destination}")
            return bundles
        
        # Get hotels at destination
        hotels = list(self.mongo_db.hotels.find({
            'address.city': {'$regex': destination, '$options': 'i'}
        }).limit(20))
        
        if not hotels:
            # Try broader search
            hotels = list(self.mongo_db.hotels.find().limit(20))
        
        # Build bundles
        for flight in flights[:5]:  # Limit to 5 flights
            for hotel in hotels[:5]:  # Limit to 5 hotels per flight
                try:
                    # Calculate total price
                    flight_price = flight.get('price', 0)
                    nights = (end_date - start_date).days
                    if nights <= 0:
                        nights = 1
                    hotel_price_per_night = hotel.get('pricePerNight', 0)
                    hotel_total = hotel_price_per_night * nights
                    total_price = flight_price + hotel_total
                    
                    # Get deal scores
                    flight_deal = self.deal_scorer.process_listing_for_deals('flight', flight.get('flightId', ''))
                    hotel_deal = self.deal_scorer.process_listing_for_deals('hotel', hotel.get('hotelId', ''))
                    
                    # Extract amenities
                    amenities = hotel.get('amenities', [])
                    if isinstance(amenities, str):
                        amenities = [a.strip() for a in amenities.replace('{', '').replace('}', '').split(',')]
                    
                    # Build bundle
                    bundle = {
                        'bundle_id': f"BUNDLE_{flight.get('flightId', '')}_{hotel.get('hotelId', '')}",
                        'flight': {
                            'flightId': flight.get('flightId', ''),
                            'airline': flight.get('airline', ''),
                            'origin': flight.get('origin', ''),
                            'destination': flight.get('destination', ''),
                            'departureTime': flight.get('departureTime'),
                            'arrivalTime': flight.get('arrivalTime'),
                            'price': flight_price,
                            'stops': flight.get('stops', 0),
                            'duration': flight.get('duration', 0)
                        },
                        'hotel': {
                            'hotelId': hotel.get('hotelId', ''),
                            'name': hotel.get('name', ''),
                            'city': hotel.get('address', {}).get('city', ''),
                            'neighbourhood': hotel.get('neighbourhood', ''),
                            'starRating': hotel.get('starRating', 3),
                            'pricePerNight': hotel_price_per_night,
                            'totalNights': nights,
                            'totalPrice': hotel_total
                        },
                        'total_price': total_price,
                        'amenities': amenities[:10],
                        'location': hotel.get('address', {}).get('city', ''),
                        'median_price': total_price * 1.15,  # Approximate median
                        'flight_deal_score': flight_deal.get('score', 0) if flight_deal else 0,
                        'hotel_deal_score': hotel_deal.get('score', 0) if hotel_deal else 0,
                        'created_at': datetime.utcnow()
                    }
                    
                    # Compute fit score
                    bundle['fit_score'] = self.compute_fit_score(bundle, user_budget, user_preferences)
                    
                    # Generate explanation
                    bundle['explanation'] = self.generate_explanation(bundle, flight_deal, hotel_deal)
                    
                    # Generate watch items
                    bundle['watch_items'] = self.generate_watch_items(bundle, hotel)
                    
                    bundles.append(bundle)
                except Exception as e:
                    logger.error(f"Error building bundle: {e}")
                    continue
        
        # Sort by fit score
        bundles.sort(key=lambda x: x.get('fit_score', 0), reverse=True)
        
        return bundles[:10]  # Return top 10
    
    def generate_explanation(self, bundle: Dict[str, Any], 
                            flight_deal: Optional[Dict], 
                            hotel_deal: Optional[Dict]) -> str:
        """
        Generate "Why this" explanation (≤25 words)
        """
        parts = []
        
        # Price comparison
        if flight_deal and flight_deal.get('discount_pct', 0) > 0:
            parts.append(f"{flight_deal['discount_pct']:.0f}% off flights")
        
        if hotel_deal and hotel_deal.get('discount_pct', 0) > 0:
            parts.append(f"{hotel_deal['discount_pct']:.0f}% off hotel")
        
        # Location
        neighbourhood = bundle.get('hotel', {}).get('neighbourhood', '')
        if neighbourhood:
            parts.append(f"in {neighbourhood}")
        
        # Amenities highlight
        amenities = bundle.get('amenities', [])
        if 'Pet-friendly' in amenities:
            parts.append("pet-friendly")
        if 'Breakfast' in amenities:
            parts.append("breakfast included")
        
        explanation = ", ".join(parts[:3])  # Limit to 3 parts
        if len(explanation) > 100:
            explanation = explanation[:97] + "..."
        
        return explanation or "Good value bundle with competitive pricing"
    
    def generate_watch_items(self, bundle: Dict[str, Any], hotel: Dict[str, Any]) -> List[str]:
        """
        Generate "What to watch" items (refund cutoff, limited rooms, etc.)
        """
        watch_items = []
        
        # Check availability
        room_types = hotel.get('roomTypes', [])
        if room_types:
            min_available = min([rt.get('available', 0) for rt in room_types])
            if min_available < 5:
                watch_items.append(f"Only {min_available} rooms left")
        
        # Cancellation policy
        cancellation = hotel.get('cancellation_policy', '')
        if cancellation:
            if 'strict' in cancellation.lower():
                watch_items.append("Strict cancellation policy - check refund terms")
            elif 'moderate' in cancellation.lower():
                watch_items.append("Moderate cancellation - 48h refund cutoff")
        
        # Price volatility
        if bundle.get('flight_deal_score', 0) > 70:
            watch_items.append("Flight prices may increase soon")
        
        return watch_items

