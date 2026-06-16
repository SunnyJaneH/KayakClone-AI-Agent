# interfaces/policy_store.py
"""
Policy Store for 'Policy Answers' functionality
Stores and retrieves structured policy information:
- Refund policies
- Pet policies
- Parking
- Amenities
- Cancellation rules
"""

import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from loguru import logger

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class PolicyInfo:
    """Structured policy information for a listing"""
    listing_id: str
    listing_type: str  # "flight", "hotel"
    
    # Refund/Cancellation
    refundable: bool = True
    refund_window: Optional[str] = None  # "24 hours before", "Oct 23 6:00 PM"
    refund_percent: int = 100  # Percentage refunded
    cancellation_fee: float = 0
    change_allowed: bool = True
    change_fee: float = 0
    
    # Pet policy
    pet_friendly: bool = False
    pet_fee: float = 0
    pet_restrictions: Optional[str] = None  # "Dogs only, max 25 lbs"
    
    # Parking
    parking_available: bool = False
    parking_type: Optional[str] = None  # "Self", "Valet", "Street"
    parking_fee: float = 0  # 0 = free
    
    # Food
    breakfast_included: bool = False
    breakfast_fee: float = 0
    restaurant_onsite: bool = False
    
    # Internet
    wifi_included: bool = True
    wifi_fee: float = 0
    
    # Other amenities
    pool: bool = False
    gym: bool = False
    spa: bool = False
    business_center: bool = False
    airport_shuttle: bool = False
    shuttle_fee: float = 0
    
    # Flight-specific
    baggage_included: Optional[str] = None  # "1 carry-on, 1 personal item"
    checked_bag_fee: float = 0
    seat_selection_fee: float = 0
    
    # Check-in/out (hotel)
    check_in_time: Optional[str] = None
    check_out_time: Optional[str] = None
    early_check_in_fee: float = 0
    late_check_out_fee: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PolicyInfo':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PolicyStore:
    """
    Stores and retrieves policy information for listings.
    Enables quick 'Policy Answers' in chat.
    """
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        self.redis_client = None
        self._memory_store: Dict[str, PolicyInfo] = {}
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info(f"PolicyStore connected to Redis")
            except Exception as e:
                logger.warning(f"PolicyStore Redis connection failed: {e}")
                self.redis_client = None
        
        # Pre-populate with default policies
        self._init_default_policies()
    
    def _get_key(self, listing_id: str) -> str:
        return f"policy:{listing_id}"
    
    def _init_default_policies(self):
        """Initialize with some default policies for demo"""
        # Sample hotel policies
        hotel_policies = [
            PolicyInfo(
                listing_id="hotel_miami_beach",
                listing_type="hotel",
                refundable=True,
                refund_window="48 hours before check-in",
                pet_friendly=True,
                pet_fee=50,
                pet_restrictions="Dogs and cats, max 50 lbs",
                parking_available=True,
                parking_type="Valet",
                parking_fee=35,
                breakfast_included=True,
                wifi_included=True,
                pool=True,
                gym=True,
                spa=True,
                check_in_time="3:00 PM",
                check_out_time="11:00 AM"
            ),
            PolicyInfo(
                listing_id="hotel_downtown",
                listing_type="hotel",
                refundable=True,
                refund_window="24 hours before check-in",
                pet_friendly=False,
                parking_available=True,
                parking_type="Self",
                parking_fee=25,
                breakfast_included=False,
                breakfast_fee=18,
                wifi_included=True,
                pool=False,
                gym=True,
                check_in_time="4:00 PM",
                check_out_time="12:00 PM"
            ),
            PolicyInfo(
                listing_id="hotel_budget",
                listing_type="hotel",
                refundable=False,
                cancellation_fee=50,
                pet_friendly=False,
                parking_available=True,
                parking_type="Street",
                parking_fee=0,
                breakfast_included=False,
                wifi_included=True,
                wifi_fee=5,
                pool=False,
                gym=False,
                check_in_time="3:00 PM",
                check_out_time="11:00 AM"
            )
        ]
        
        # Sample flight policies
        flight_policies = [
            PolicyInfo(
                listing_id="flight_aa_economy",
                listing_type="flight",
                refundable=False,
                change_allowed=True,
                change_fee=0,
                baggage_included="1 carry-on, 1 personal item",
                checked_bag_fee=35,
                seat_selection_fee=10
            ),
            PolicyInfo(
                listing_id="flight_ua_economy",
                listing_type="flight",
                refundable=False,
                change_allowed=True,
                change_fee=75,
                baggage_included="1 carry-on, 1 personal item",
                checked_bag_fee=40,
                seat_selection_fee=12
            ),
            PolicyInfo(
                listing_id="flight_sw_economy",
                listing_type="flight",
                refundable=True,
                refund_window="Anytime (travel credit)",
                change_allowed=True,
                change_fee=0,
                baggage_included="2 checked bags, 1 carry-on, 1 personal item",
                checked_bag_fee=0,
                seat_selection_fee=0
            )
        ]
        
        for policy in hotel_policies + flight_policies:
            self.set_policy(policy)
    
    def set_policy(self, policy: PolicyInfo):
        """Store a policy"""
        key = self._get_key(policy.listing_id)
        
        if self.redis_client:
            try:
                self.redis_client.set(key, json.dumps(policy.to_dict()))
            except Exception as e:
                logger.error(f"Redis set policy error: {e}")
        
        self._memory_store[policy.listing_id] = policy
    
    def get_policy(self, listing_id: str) -> Optional[PolicyInfo]:
        """Get policy for a listing"""
        key = self._get_key(listing_id)
        
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    return PolicyInfo.from_dict(json.loads(data))
            except Exception as e:
                logger.error(f"Redis get policy error: {e}")
        
        return self._memory_store.get(listing_id)
    
    def get_policy_or_default(self, listing_id: str, listing_type: str) -> PolicyInfo:
        """Get policy or return default for listing type"""
        policy = self.get_policy(listing_id)
        
        if policy:
            return policy
        
        # Return default based on type
        if listing_type == "flight":
            return PolicyInfo(
                listing_id=listing_id,
                listing_type="flight",
                refundable=False,
                change_allowed=True,
                change_fee=75,
                baggage_included="1 carry-on, 1 personal item",
                checked_bag_fee=35,
                seat_selection_fee=15
            )
        else:
            return PolicyInfo(
                listing_id=listing_id,
                listing_type="hotel",
                refundable=True,
                refund_window="24 hours before check-in",
                pet_friendly=False,
                parking_available=False,
                breakfast_included=False,
                wifi_included=True,
                check_in_time="3:00 PM",
                check_out_time="11:00 AM"
            )
    
    def format_policy_summary(self, policy: PolicyInfo) -> str:
        """Format policy as human-readable summary"""
        parts = []
        
        # Cancellation
        if policy.refundable:
            if policy.refund_window:
                parts.append(f"Refundable until {policy.refund_window}")
            else:
                parts.append("Fully refundable")
        else:
            if policy.cancellation_fee > 0:
                parts.append(f"Non-refundable (${policy.cancellation_fee} fee)")
            else:
                parts.append("Non-refundable")
        
        # Pet policy
        if policy.pet_friendly:
            if policy.pet_fee > 0:
                parts.append(f"Pets OK (+${policy.pet_fee})")
            else:
                parts.append("Pets allowed")
            if policy.pet_restrictions:
                parts.append(f"({policy.pet_restrictions})")
        
        # Parking
        if policy.parking_available:
            if policy.parking_fee > 0:
                parts.append(f"Parking: ${policy.parking_fee}/night ({policy.parking_type})")
            else:
                parts.append(f"Free parking ({policy.parking_type})")
        
        # Breakfast
        if policy.breakfast_included:
            parts.append("Breakfast included")
        elif policy.breakfast_fee > 0:
            parts.append(f"Breakfast: ${policy.breakfast_fee}")
        
        # WiFi
        if policy.wifi_included:
            if policy.wifi_fee > 0:
                parts.append(f"WiFi: ${policy.wifi_fee}/day")
            else:
                parts.append("Free WiFi")
        
        # Flight-specific
        if policy.listing_type == "flight":
            if policy.baggage_included:
                parts.append(f"Bags: {policy.baggage_included}")
            if policy.checked_bag_fee > 0:
                parts.append(f"Checked bag: ${policy.checked_bag_fee}")
            if policy.change_fee > 0:
                parts.append(f"Change fee: ${policy.change_fee}")
            elif policy.change_allowed:
                parts.append("Free flight changes")
        
        return " | ".join(parts)
    
    def answer_policy_question(self, listing_id: str, question: str) -> str:
        """
        Answer a specific policy question.
        Implements 'Policy Answers' for chat.
        """
        question_lower = question.lower()
        policy = self.get_policy(listing_id)
        
        if not policy:
            return "I don't have detailed policy information for this listing."
        
        # Cancellation questions
        if any(word in question_lower for word in ["cancel", "refund", "money back"]):
            if policy.refundable:
                if policy.refund_window:
                    return f"Yes, this booking is refundable until {policy.refund_window}. You'll receive a {policy.refund_percent}% refund."
                return "Yes, this booking is fully refundable."
            else:
                if policy.cancellation_fee > 0:
                    return f"This booking is non-refundable. Cancellation fee is ${policy.cancellation_fee}."
                return "This booking is non-refundable."
        
        # Pet questions
        if any(word in question_lower for word in ["pet", "dog", "cat", "animal"]):
            if policy.pet_friendly:
                response = "Yes, pets are allowed!"
                if policy.pet_fee > 0:
                    response += f" There's a ${policy.pet_fee} pet fee."
                if policy.pet_restrictions:
                    response += f" Restrictions: {policy.pet_restrictions}"
                return response
            return "Unfortunately, pets are not allowed at this property."
        
        # Parking questions
        if any(word in question_lower for word in ["parking", "car", "park"]):
            if policy.parking_available:
                if policy.parking_fee > 0:
                    return f"{policy.parking_type} parking is available for ${policy.parking_fee}/night."
                return f"Free {policy.parking_type.lower()} parking is available."
            return "Parking is not available at this property. Consider nearby parking garages."
        
        # Breakfast questions
        if any(word in question_lower for word in ["breakfast", "food", "meal"]):
            if policy.breakfast_included:
                return "Breakfast is included with your stay!"
            elif policy.breakfast_fee > 0:
                return f"Breakfast is available for ${policy.breakfast_fee} per person."
            return "Breakfast is not included. There may be restaurants nearby."
        
        # WiFi questions
        if any(word in question_lower for word in ["wifi", "internet", "wi-fi"]):
            if policy.wifi_included:
                if policy.wifi_fee > 0:
                    return f"WiFi is available for ${policy.wifi_fee}/day."
                return "Free WiFi is included."
            return "WiFi information is not available for this listing."
        
        # Baggage questions (flights)
        if any(word in question_lower for word in ["bag", "luggage", "carry-on", "checked"]):
            if policy.baggage_included:
                response = f"Included: {policy.baggage_included}."
                if policy.checked_bag_fee > 0:
                    response += f" Additional checked bags: ${policy.checked_bag_fee} each."
                return response
            return "Please check the airline's baggage policy."
        
        # Change/modify questions
        if any(word in question_lower for word in ["change", "modify", "reschedule"]):
            if policy.change_allowed:
                if policy.change_fee > 0:
                    return f"Changes are allowed with a ${policy.change_fee} fee."
                return "Free changes are allowed!"
            return "Changes may not be allowed for this fare type."
        
        # Check-in/out questions
        if any(word in question_lower for word in ["check-in", "check in", "check-out", "check out"]):
            parts = []
            if policy.check_in_time:
                parts.append(f"Check-in: {policy.check_in_time}")
            if policy.check_out_time:
                parts.append(f"Check-out: {policy.check_out_time}")
            if parts:
                return " | ".join(parts)
            return "Standard check-in is 3:00 PM, check-out is 11:00 AM."
        
        # Default: return full summary
        return self.format_policy_summary(policy)
    
    def extract_policy_from_listing(self, listing: Dict[str, Any], 
                                    listing_type: str) -> PolicyInfo:
        """
        Extract policy info from a listing dict (from database/API).
        Normalizes various data formats.
        """
        listing_id = listing.get("id") or listing.get("listing_id") or listing.get("hotel_id") or listing.get("flight_id", "")
        
        policy = PolicyInfo(
            listing_id=str(listing_id),
            listing_type=listing_type
        )
        
        # Check various field names
        if listing_type == "hotel":
            # Amenities parsing
            amenities = listing.get("amenities", [])
            if isinstance(amenities, str):
                amenities = [a.strip() for a in amenities.split(",")]
            
            amenities_lower = [a.lower() for a in amenities]
            
            policy.pet_friendly = any("pet" in a for a in amenities_lower)
            policy.parking_available = any("parking" in a for a in amenities_lower)
            policy.breakfast_included = any("breakfast" in a for a in amenities_lower)
            policy.wifi_included = any("wifi" in a or "internet" in a for a in amenities_lower)
            policy.pool = any("pool" in a for a in amenities_lower)
            policy.gym = any("gym" in a or "fitness" in a for a in amenities_lower)
            
            # Cancellation
            cancel_policy = listing.get("cancellation_policy", "").lower()
            if "free" in cancel_policy or "refund" in cancel_policy:
                policy.refundable = True
            elif "non" in cancel_policy or "no refund" in cancel_policy:
                policy.refundable = False
        
        elif listing_type == "flight":
            policy.baggage_included = listing.get("baggage_included", "1 carry-on")
            policy.checked_bag_fee = listing.get("checked_bag_fee", 35)
            policy.change_fee = listing.get("change_fee", 75)
            policy.refundable = listing.get("refundable", False)
        
        return policy


# ============================================
# Global Instance
# ============================================

from config import settings
policy_store = PolicyStore(
    redis_host=settings.REDIS_HOST,
    redis_port=settings.REDIS_PORT
)


# ============================================
# Convenience Functions
# ============================================

def get_policy(listing_id: str) -> Optional[Dict[str, Any]]:
    """Get policy as dict"""
    policy = policy_store.get_policy(listing_id)
    return policy.to_dict() if policy else None


def format_policy(listing_id: str) -> str:
    """Get formatted policy string"""
    policy = policy_store.get_policy(listing_id)
    if policy:
        return policy_store.format_policy_summary(policy)
    return "Policy information not available"


def answer_policy_question(listing_id: str, question: str) -> str:
    """Answer a policy question"""
    return policy_store.answer_policy_question(listing_id, question)
