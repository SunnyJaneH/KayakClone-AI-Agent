"""
Kafka Message Schemas - Pydantic v2 Models
Defines the structure of all Kafka messages
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# ============================================
# Listing Event (Consumed from Backend)
# ============================================

class ListingEvent(BaseModel):
    """
    Event received from Backend's Listings Service
    Topic: listing.events
    
    This is the raw data we consume and process
    """
    listingId: str = Field(..., description="Unique listing identifier")
    listingType: str = Field(..., description="Type: flight, hotel, car")
    price: float = Field(..., description="Current price")
    avg_30d_price: float = Field(..., description="30-day average price")
    availability: int = Field(..., description="Available quantity")
    rating: float = Field(..., description="User rating (0-5)")
    
    # Flight-specific fields (optional)
    departure: Optional[str] = None
    arrival: Optional[str] = None
    date: Optional[str] = None
    airline: Optional[str] = None
    duration: Optional[int] = None  # in minutes
    stops: Optional[int] = None
    
    # Hotel-specific fields (optional)
    hotelName: Optional[str] = None
    city: Optional[str] = None
    starRating: Optional[float] = None
    amenities: Optional[List[str]] = None
    policies: Optional[Dict[str, Any]] = None
    location: Optional[Dict[str, Any]] = None
    
    # Common optional fields
    has_promotion: bool = False
    timestamp: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "listingId": "flight-001",
                "listingType": "flight",
                "price": 280.0,
                "avg_30d_price": 350.0,
                "availability": 3,
                "rating": 4.5,
                "departure": "SFO",
                "arrival": "MIA",
                "date": "2025-11-15",
                "airline": "United",
                "has_promotion": False
            }
        }


# ============================================
# Deal Scored Event (Published by Deals Agent)
# ============================================

class DealScoredEvent(BaseModel):
    """
    Event published after calculating deal score
    Topic: deals.scored
    
    This contains the Deal Score algorithm output
    """
    listingId: str = Field(..., description="Listing identifier")
    dealScore: int = Field(..., ge=0, le=100, description="Deal score (0-100)")
    isDeal: bool = Field(..., description="Whether score >= threshold")
    
    # Score breakdown for debugging
    priceAdvantageScore: int = Field(default=0, ge=0, le=40)
    scarcityScore: int = Field(default=0, ge=0, le=30)
    ratingScore: int = Field(default=0, ge=0, le=20)
    promotionScore: int = Field(default=0, ge=0, le=10)
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "listingId": "flight-001",
                "dealScore": 85,
                "isDeal": True,
                "priceAdvantageScore": 40,
                "scarcityScore": 30,
                "ratingScore": 15,
                "promotionScore": 0
            }
        }


# ============================================
# Deal Tagged Event (Published by Deals Agent)
# ============================================

class DealTaggedEvent(BaseModel):
    """
    Event published after tagging deals
    Topic: deals.tagged
    
    This contains auto-generated tags
    """
    listingId: str = Field(..., description="Listing identifier")
    tags: List[str] = Field(default_factory=list, description="List of tags")
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "listingId": "hotel-001",
                "tags": ["deal", "limited_availability", "pet-friendly", "wifi", "refundable"]
            }
        }


# ============================================
# Final Deal Event (Published by Deals Agent)
# ============================================

class DealEvent(BaseModel):
    """
    Final event published for frontend consumption
    Topic: deal.events
    
    This is the complete deal information
    """
    listingId: str = Field(..., description="Listing identifier")
    listingType: str = Field(..., description="Type: flight, hotel, car")
    
    # Deal information
    dealScore: int = Field(..., ge=0, le=100)
    isDeal: bool = Field(...)
    tags: List[str] = Field(default_factory=list)
    
    # Price information
    price: float = Field(...)
    avg_30d_price: float = Field(...)
    savings: float = Field(default=0.0, description="Price savings amount")
    savingsPercentage: float = Field(default=0.0, description="Savings percentage")
    
    # Availability
    availability: int = Field(...)
    rating: float = Field(...)
    
    # Original listing data (for display)
    listingData: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "listingId": "flight-001",
                "listingType": "flight",
                "dealScore": 85,
                "isDeal": True,
                "tags": ["deal", "limited_availability"],
                "price": 280.0,
                "avg_30d_price": 350.0,
                "savings": 70.0,
                "savingsPercentage": 20.0,
                "availability": 3,
                "rating": 4.5,
                "listingData": {
                    "departure": "SFO",
                    "arrival": "MIA",
                    "airline": "United"
                }
            }
        }


# ============================================
# Helper Functions
# ============================================

def create_deal_event_from_listing(
    listing: ListingEvent,
    deal_score: int,
    is_deal: bool,
    tags: List[str]
) -> DealEvent:
    """
    Helper function to create DealEvent from ListingEvent
    
    Args:
        listing: Original listing event
        deal_score: Calculated deal score
        is_deal: Whether it's a deal
        tags: Auto-generated tags
        
    Returns:
        DealEvent: Complete deal event ready to publish
    """
    savings = max(0, listing.avg_30d_price - listing.price)
    savings_pct = (savings / listing.avg_30d_price * 100) if listing.avg_30d_price > 0 else 0
    
    # Extract listing-specific data
    listing_data = listing.model_dump(exclude={'listingId', 'listingType', 'price', 'avg_30d_price', 'availability', 'rating'})
    
    return DealEvent(
        listingId=listing.listingId,
        listingType=listing.listingType,
        dealScore=deal_score,
        isDeal=is_deal,
        tags=tags,
        price=listing.price,
        avg_30d_price=listing.avg_30d_price,
        savings=round(savings, 2),
        savingsPercentage=round(savings_pct, 1),
        availability=listing.availability,
        rating=listing.rating,
        listingData=listing_data
    )
