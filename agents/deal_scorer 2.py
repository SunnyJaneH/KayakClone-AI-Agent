"""
Deals Agent - Backend Worker
Processes real data from Kaggle datasets to detect deals
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pymongo import MongoClient
from sqlmodel import Session, select
import logging

# Add ai directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import config, fallback to environment variables
try:
    from config import settings
    MONGO_URI = settings.MONGO_URI
    MONGO_DB_SEARCH = settings.MONGO_DB_SEARCH
except ImportError:
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
    MONGO_DB_SEARCH = os.getenv('MONGO_DB_SEARCH', 'kayak_doc')

logger = logging.getLogger(__name__)

class DealScorer:
    """
    Scores and tags deals from real dataset data
    Uses Inside Airbnb data for hotels, Flight Price data for flights
    """
    
    def __init__(self):
        self.mongo_client = MongoClient(MONGO_URI)
        self.mongo_db = self.mongo_client[MONGO_DB_SEARCH]
    
    def compute_avg_30d_price(self, listing_id: str, listing_type: str) -> float:
        """
        Compute 30-day average price for a listing
        From Inside Airbnb: uses price history if available
        Otherwise computes from similar listings
        """
        collection = self.mongo_db[f"{listing_type}s"]
        
        # Try to get price history (if available in dataset)
        listing = collection.find_one({f"{listing_type}Id": listing_id})
        if not listing:
            return 0.0
        
        # For hotels: use pricePerNight, compute average from similar listings
        if listing_type == 'hotel':
            current_price = listing.get('pricePerNight', 0)
            if current_price == 0:
                return 0.0
            
            # Get similar hotels in same area
            city = listing.get('address', {}).get('city', '')
            neighbourhood = listing.get('neighbourhood', '')
            
            similar = list(collection.find({
                'address.city': city,
                'neighbourhood': neighbourhood if neighbourhood else {'$exists': True}
            }).limit(30))
            
            if len(similar) > 5:
                prices = [h.get('pricePerNight', 0) for h in similar if h.get('pricePerNight', 0) > 0]
                if prices:
                    avg_price = sum(prices) / len(prices)
                    return avg_price
            
            return current_price * 1.1  # Default: assume 10% above average
        
        # For flights: use similar route prices
        elif listing_type == 'flight':
            origin = listing.get('origin', '')
            destination = listing.get('destination', '')
            current_price = listing.get('price', 0)
            
            if not origin or not destination:
                return current_price * 1.1
            
            similar = list(collection.find({
                'origin': origin,
                'destination': destination
            }).limit(30))
            
            if len(similar) > 5:
                prices = [f.get('price', 0) for f in similar if f.get('price', 0) > 0]
                if prices:
                    avg_price = sum(prices) / len(prices)
                    return avg_price
            
            return current_price * 1.1
        
        return 0.0
    
    def score_deal(self, listing_type: str, listing_id: str, price: float, 
                   avg_price: float, available_count: int = None) -> Dict[str, Any]:
        """
        Score a deal based on price vs average and availability
        Returns: score (0-100), is_deal (bool), tags (list), explanation
        """
        if avg_price == 0 or price == 0:
            return {
                'score': 0,
                'is_deal': False,
                'tags': [],
                'explanation': 'Insufficient price data'
            }
        
        # Price discount percentage
        discount_pct = ((avg_price - price) / avg_price) * 100
        
        # Base score from discount
        score = min(100, max(0, discount_pct * 2))  # 50% discount = 100 points
        
        # Availability bonus/penalty
        if available_count is not None:
            if available_count < 5:
                score += 10  # Limited availability bonus
            elif available_count > 20:
                score -= 5   # High availability penalty
        
        # Determine if it's a deal (≥15% discount)
        is_deal = discount_pct >= 15
        
        # Generate tags
        tags = []
        if discount_pct >= 25:
            tags.append('Great Deal')
        elif discount_pct >= 15:
            tags.append('Good Deal')
        
        if available_count is not None and available_count < 5:
            tags.append('Limited Availability')
        
        # Generate explanation
        explanation = f"{discount_pct:.0f}% below average price"
        if available_count is not None and available_count < 5:
            explanation += f", only {available_count} left"
        
        return {
            'score': round(score, 1),
            'is_deal': is_deal,
            'tags': tags,
            'explanation': explanation,
            'discount_pct': round(discount_pct, 1),
            'price': price,
            'avg_price': round(avg_price, 2)
        }
    
    def extract_tags_from_listing(self, listing: Dict[str, Any], listing_type: str) -> List[str]:
        """
        Extract tags from listing data (amenities, policies, etc.)
        From Inside Airbnb: amenities, pet-friendly, cancellation policy
        """
        tags = []
        
        if listing_type == 'hotel':
            # Amenities tags
            amenities = listing.get('amenities', [])
            if isinstance(amenities, str):
                amenities = [a.strip() for a in amenities.replace('{', '').replace('}', '').split(',')]
            
            amenity_keywords = {
                'Pet-friendly': ['pet', 'dog', 'cat', 'pets allowed'],
                'Breakfast': ['breakfast', 'continental breakfast'],
                'Near Transit': ['transit', 'metro', 'subway', 'bus'],
                'Parking': ['parking', 'garage', 'car park'],
                'WiFi': ['wifi', 'wireless', 'internet'],
                'Pool': ['pool', 'swimming'],
                'Gym': ['gym', 'fitness', 'exercise']
            }
            
            amenities_lower = [str(a).lower() for a in amenities]
            for tag, keywords in amenity_keywords.items():
                if any(kw in ' '.join(amenities_lower) for kw in keywords):
                    tags.append(tag)
            
            # Cancellation policy
            cancellation = listing.get('cancellation_policy', '').lower()
            if 'flexible' in cancellation:
                tags.append('Flexible Cancellation')
            elif 'moderate' in cancellation:
                tags.append('Moderate Cancellation')
        
        elif listing_type == 'flight':
            # Flight-specific tags
            stops = listing.get('stops', 0)
            if stops == 0:
                tags.append('Non-stop')
            elif stops == 1:
                tags.append('1 Stop')
            
            flight_class = listing.get('flightClass', 'economy')
            if flight_class == 'business':
                tags.append('Business Class')
            elif flight_class == 'first':
                tags.append('First Class')
        
        return tags
    
    def process_listing_for_deals(self, listing_type: str, listing_id: str) -> Optional[Dict[str, Any]]:
        """
        Process a single listing to detect if it's a deal
        Returns deal information if found
        """
        collection = self.mongo_db[f"{listing_type}s"]
        listing = collection.find_one({f"{listing_type}Id": listing_id})
        
        if not listing:
            return None
        
        # Get price
        if listing_type == 'hotel':
            price = listing.get('pricePerNight', 0)
            available_count = listing.get('roomTypes', [{}])[0].get('available', None) if listing.get('roomTypes') else None
        elif listing_type == 'flight':
            price = listing.get('price', 0)
            available_count = None  # Flights don't have availability in this dataset
        else:
            return None
        
        if price == 0:
            return None
        
        # Compute average price
        avg_price = self.compute_avg_30d_price(listing_id, listing_type)
        
        # Score the deal
        deal_info = self.score_deal(listing_type, listing_id, price, avg_price, available_count)
        
        # Extract tags
        listing_tags = self.extract_tags_from_listing(listing, listing_type)
        deal_info['tags'].extend(listing_tags)
        
        # Add listing data
        deal_info['listing_type'] = listing_type
        deal_info['listing_id'] = listing_id
        deal_info['listing_data'] = {
            'name': listing.get('name', listing.get('airline', 'Unknown')),
            'location': listing.get('address', {}).get('city', '') if listing_type == 'hotel' else f"{listing.get('origin', '')} → {listing.get('destination', '')}"
        }
        
        return deal_info if deal_info['is_deal'] else None

