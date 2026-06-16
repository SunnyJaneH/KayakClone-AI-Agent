"""
AI Helper Utilities
Common utility functions for AI service
"""

from typing import List, Dict, Any
from kafka.message_schemas import ListingEvent


def auto_tag_deal(
    listing: ListingEvent,
    deal_score: int,
    is_deal: bool
) -> List[str]:
    """
    Automatically generate tags for a listing
    
    Tags include:
    - deal: Is a good deal (score >= 40)
    - limited_availability: Low availability
    - high_rating: Rating >= 4.5
    - promotion: Has active promotion
    - pet-friendly: Hotel allows pets
    - refundable: Hotel has refundable cancellation
    - wifi: Has wifi
    - pool: Has pool
    - near-transit: Near public transit
    
    Args:
        listing: ListingEvent object
        deal_score: Calculated deal score
        is_deal: Whether it's considered a deal
    
    Returns:
        List[str]: List of tags
    
    Example:
        >>> from kafka.message_schemas import ListingEvent
        >>> listing = ListingEvent(
        ...     listingId="hotel-001",
        ...     listingType="hotel",
        ...     price=150,
        ...     avg_30d_price=200,
        ...     availability=2,
        ...     rating=4.8,
        ...     amenities=["wifi", "pool"],
        ...     policies={"pets": True, "cancellation": "refundable"}
        ... )
        >>> tags = auto_tag_deal(listing, 85, True)
        >>> print(tags)
        ['deal', 'limited_availability', 'high_rating', 'pet-friendly', 'refundable', 'wifi', 'pool']
    """
    tags = []
    
    # Deal tag
    if is_deal:
        tags.append("deal")
    
    # Availability tags
    if listing.availability <= 3:
        tags.append("limited_availability")
    
    # Rating tags
    if listing.rating >= 4.5:
        tags.append("high_rating")
    
    # Promotion tag
    if listing.has_promotion:
        tags.append("promotion")
    
    # Hotel-specific tags
    if listing.listingType == "hotel":
        # Policy tags
        if listing.policies:
            if listing.policies.get("pets"):
                tags.append("pet-friendly")
            if listing.policies.get("cancellation") == "refundable":
                tags.append("refundable")
        
        # Amenity tags
        if listing.amenities:
            amenities_lower = [a.lower() for a in listing.amenities]
            
            if "wifi" in amenities_lower:
                tags.append("wifi")
            if "pool" in amenities_lower:
                tags.append("pool")
            if "breakfast" in amenities_lower:
                tags.append("breakfast")
            if "gym" in amenities_lower or "fitness" in amenities_lower:
                tags.append("gym")
            if "spa" in amenities_lower:
                tags.append("spa")
            if "beach" in amenities_lower:
                tags.append("beach")
        
        # Location tags
        if listing.location:
            if listing.location.get("near_transit"):
                tags.append("near-transit")
            if listing.location.get("city_center"):
                tags.append("city-center")
            if listing.location.get("near_airport"):
                tags.append("near-airport")
    
    # Flight-specific tags
    if listing.listingType == "flight":
        if listing.stops == 0:
            tags.append("nonstop")
        if listing.airline:
            tags.append(f"airline-{listing.airline.lower().replace(' ', '-')}")
    
    return tags


def format_price(price: float) -> str:
    """
    Format price as currency string
    
    Args:
        price: Price value
    
    Returns:
        str: Formatted price (e.g., "$280.00")
    """
    return f"${price:.2f}"


def calculate_savings_percentage(current_price: float, avg_price: float) -> float:
    """
    Calculate savings percentage
    
    Args:
        current_price: Current price
        avg_price: Average price
    
    Returns:
        float: Savings percentage (e.g., 20.5 for 20.5%)
    """
    if avg_price <= 0:
        return 0.0
    
    savings = max(0, avg_price - current_price)
    return round((savings / avg_price) * 100, 1)


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add (default: "...")
    
    Returns:
        str: Truncated text
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def extract_city_from_code(airport_code: str) -> str:
    """
    Extract city name from airport code
    (Simple mapping for common codes)
    
    Args:
        airport_code: 3-letter airport code
    
    Returns:
        str: City name or airport code if not found
    """
    mapping = {
        "SFO": "San Francisco",
        "LAX": "Los Angeles",
        "JFK": "New York",
        "NYC": "New York",
        "MIA": "Miami",
        "LAS": "Las Vegas",
        "ORD": "Chicago",
        "DFW": "Dallas",
        "ATL": "Atlanta",
        "SEA": "Seattle",
        "BOS": "Boston",
        "DEN": "Denver",
        "PHX": "Phoenix"
    }
    
    return mapping.get(airport_code.upper(), airport_code)


def merge_tags(*tag_lists: List[str]) -> List[str]:
    """
    Merge multiple tag lists, removing duplicates
    
    Args:
        *tag_lists: Variable number of tag lists
    
    Returns:
        List[str]: Merged unique tags
    """
    all_tags = []
    for tags in tag_lists:
        all_tags.extend(tags)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in all_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags


def filter_deals_by_tags(
    deals: List[Dict[str, Any]],
    required_tags: List[str]
) -> List[Dict[str, Any]]:
    """
    Filter deals by required tags
    
    Args:
        deals: List of deal dicts (must have 'tags' key)
        required_tags: Tags that must be present
    
    Returns:
        List[dict]: Filtered deals
    """
    filtered = []
    required_set = set(tag.lower() for tag in required_tags)
    
    for deal in deals:
        deal_tags = set(tag.lower() for tag in deal.get("tags", []))
        if required_set.issubset(deal_tags):
            filtered.append(deal)
    
    return filtered


def sort_deals_by_score(
    deals: List[Dict[str, Any]],
    score_key: str = "dealScore",
    descending: bool = True
) -> List[Dict[str, Any]]:
    """
    Sort deals by score
    
    Args:
        deals: List of deal dicts
        score_key: Key name for score (default: "dealScore")
        descending: Sort in descending order (default: True)
    
    Returns:
        List[dict]: Sorted deals
    """
    return sorted(
        deals,
        key=lambda d: d.get(score_key, 0),
        reverse=descending
    )


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    from kafka.message_schemas import ListingEvent
    
    # Example: Auto-tag a hotel listing
    hotel = ListingEvent(
        listingId="hotel-001",
        listingType="hotel",
        hotelName="Grand Hyatt",
        price=150.0,
        avg_30d_price=200.0,
        availability=2,
        rating=4.8,
        city="Miami",
        starRating=4.5,
        amenities=["wifi", "pool", "breakfast", "gym"],
        policies={"cancellation": "refundable", "pets": True},
        location={"near_transit": True, "city_center": True, "near_airport": False},
        has_promotion=False
    )
    
    tags = auto_tag_deal(hotel, deal_score=85, is_deal=True)
    print(f"Auto-generated tags: {tags}")
    
    # Example: Price formatting
    print(f"Price: {format_price(280.50)}")
    
    # Example: Savings calculation
    savings_pct = calculate_savings_percentage(280, 350)
    print(f"Savings: {savings_pct}%")
    
    # Example: City extraction
    print(f"SFO = {extract_city_from_code('SFO')}")
    print(f"MIA = {extract_city_from_code('MIA')}")
