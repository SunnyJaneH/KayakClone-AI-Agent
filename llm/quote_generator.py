# llm/quote_generator.py
"""
Quote Generator for 'Book or hand off cleanly' user journey
Generates complete, validated quotes with:
- Fare class, baggage, fees
- Cancellation policies
- Total breakdown
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class FlightQuoteDetails:
    """Detailed flight quote"""
    flight_id: str
    airline: str
    origin: str
    destination: str
    departure_time: str
    arrival_time: str
    duration_minutes: int
    stops: int
    flight_class: str
    
    # Pricing breakdown
    base_fare: float
    taxes: float
    carrier_fee: float = 0
    baggage_fee: float = 0
    seat_selection_fee: float = 0
    total: float = 0
    
    # Policies
    baggage_included: str = "1 carry-on"
    checked_bag_price: float = 35
    change_fee: float = 75
    cancellation_policy: str = "Non-refundable"
    
    def calculate_total(self):
        self.total = self.base_fare + self.taxes + self.carrier_fee + self.baggage_fee + self.seat_selection_fee


@dataclass
class HotelQuoteDetails:
    """Detailed hotel quote"""
    hotel_id: str
    name: str
    city: str
    star_rating: int
    room_type: str
    
    # Pricing breakdown
    rate_per_night: float
    nights: int
    subtotal: float = 0
    resort_fee_per_night: float = 0
    resort_fee_total: float = 0
    taxes_percent: float = 12.5
    taxes: float = 0
    total: float = 0
    
    # Policies
    cancellation_policy: str = "Free cancellation until 24 hours before check-in"
    cancellation_deadline: Optional[str] = None
    check_in_time: str = "3:00 PM"
    check_out_time: str = "11:00 AM"
    
    # Amenities included
    amenities_included: List[str] = field(default_factory=list)
    
    def calculate_total(self):
        self.subtotal = self.rate_per_night * self.nights
        self.resort_fee_total = self.resort_fee_per_night * self.nights
        self.taxes = (self.subtotal + self.resort_fee_total) * (self.taxes_percent / 100)
        self.total = self.subtotal + self.resort_fee_total + self.taxes


@dataclass
class FullQuote:
    """Complete quote for bundle"""
    quote_id: str
    bundle_id: str
    
    flight_quote: FlightQuoteDetails
    hotel_quote: HotelQuoteDetails
    
    grand_total: float = 0
    separate_booking_total: float = 0
    bundle_savings: float = 0
    
    # Summary
    cancellation_summary: str = ""
    important_notes: List[str] = field(default_factory=list)
    
    # Validity
    quote_valid_until: str = ""
    created_at: str = ""
    
    def calculate_totals(self):
        self.grand_total = self.flight_quote.total + self.hotel_quote.total
        # Assume 10% bundle discount
        self.separate_booking_total = self.grand_total * 1.1
        self.bundle_savings = self.separate_booking_total - self.grand_total


class QuoteGenerator:
    """
    Generates complete quotes for bookings.
    Implements 'Book or hand off cleanly' user journey.
    """
    
    def __init__(self):
        # Default fee structures by airline
        self.airline_fees = {
            "default": {
                "carrier_fee": 15,
                "checked_bag": 35,
                "seat_selection": 15,
                "change_fee": 75,
                "cancellation": "Non-refundable, change fee applies"
            },
            "AA": {
                "carrier_fee": 20,
                "checked_bag": 35,
                "seat_selection": 10,
                "change_fee": 0,
                "cancellation": "Free change, non-refundable"
            },
            "UA": {
                "carrier_fee": 18,
                "checked_bag": 40,
                "seat_selection": 12,
                "change_fee": 75,
                "cancellation": "Non-refundable"
            },
            "DL": {
                "carrier_fee": 15,
                "checked_bag": 35,
                "seat_selection": 15,
                "change_fee": 0,
                "cancellation": "Free change for Basic Economy+"
            },
            "SW": {
                "carrier_fee": 0,
                "checked_bag": 0,
                "seat_selection": 0,
                "change_fee": 0,
                "cancellation": "Free cancellation, travel credit issued"
            }
        }
        
        # Tax rates by region
        self.tax_rates = {
            "domestic": 0.075,  # 7.5% US domestic
            "international": 0.10,  # ~10% international
        }
        
        # Hotel resort fees by star rating
        self.resort_fees = {
            5: 45,
            4: 25,
            3: 15,
            2: 0,
            1: 0
        }
    
    def generate_flight_quote(self, flight: Dict[str, Any], add_baggage: bool = False,
                              add_seat_selection: bool = False) -> FlightQuoteDetails:
        """Generate detailed flight quote"""
        airline_code = flight.get("airline", "")[:2].upper()
        fees = self.airline_fees.get(airline_code, self.airline_fees["default"])
        
        base_fare = flight.get("price", 0)
        
        # Determine tax rate
        origin = flight.get("origin", "")
        destination = flight.get("destination", "")
        is_international = self._is_international(origin, destination)
        tax_rate = self.tax_rates["international"] if is_international else self.tax_rates["domestic"]
        
        taxes = base_fare * tax_rate
        carrier_fee = fees["carrier_fee"]
        
        baggage_fee = fees["checked_bag"] if add_baggage else 0
        seat_fee = fees["seat_selection"] if add_seat_selection else 0
        
        quote = FlightQuoteDetails(
            flight_id=flight.get("flight_id", f"FL{uuid.uuid4().hex[:6].upper()}"),
            airline=flight.get("airline", "Unknown Airline"),
            origin=origin,
            destination=destination,
            departure_time=flight.get("departure_time", ""),
            arrival_time=flight.get("arrival_time", ""),
            duration_minutes=flight.get("duration_minutes", 0),
            stops=flight.get("stops", 0),
            flight_class=flight.get("flight_class", "Economy"),
            base_fare=base_fare,
            taxes=taxes,
            carrier_fee=carrier_fee,
            baggage_fee=baggage_fee,
            seat_selection_fee=seat_fee,
            baggage_included="1 carry-on, 1 personal item",
            checked_bag_price=fees["checked_bag"],
            change_fee=fees["change_fee"],
            cancellation_policy=fees["cancellation"]
        )
        
        quote.calculate_total()
        return quote
    
    def generate_hotel_quote(self, hotel: Dict[str, Any], nights: int,
                             check_in_date: Optional[str] = None) -> HotelQuoteDetails:
        """Generate detailed hotel quote"""
        star_rating = hotel.get("star_rating", 3)
        rate_per_night = hotel.get("price_per_night", hotel.get("price", 0))
        
        # Resort fee based on star rating
        resort_fee = self.resort_fees.get(star_rating, 0)
        
        # Calculate cancellation deadline
        cancellation_deadline = None
        if check_in_date:
            try:
                check_in = datetime.fromisoformat(check_in_date)
                cancel_by = check_in - timedelta(hours=24)
                cancellation_deadline = cancel_by.strftime("%B %d, %Y at %I:%M %p")
            except:
                pass
        
        # Determine cancellation policy
        policy = hotel.get("policy", {})
        if policy.get("refundable", True):
            cancel_policy = f"Free cancellation until {cancellation_deadline or '24 hours before check-in'}"
        else:
            cancel_policy = "Non-refundable. No refund for cancellation or no-show."
        
        quote = HotelQuoteDetails(
            hotel_id=hotel.get("hotel_id", f"HT{uuid.uuid4().hex[:6].upper()}"),
            name=hotel.get("name", "Hotel"),
            city=hotel.get("city", ""),
            star_rating=star_rating,
            room_type=hotel.get("room_type", "Standard Room"),
            rate_per_night=rate_per_night,
            nights=nights,
            resort_fee_per_night=resort_fee,
            cancellation_policy=cancel_policy,
            cancellation_deadline=cancellation_deadline,
            amenities_included=hotel.get("amenities", [])[:5]
        )
        
        quote.calculate_total()
        return quote
    
    def generate_full_quote(self, bundle: Dict[str, Any], 
                           add_baggage: bool = False,
                           add_seat_selection: bool = False) -> FullQuote:
        """
        Generate complete quote for a bundle.
        Implements 'Book or hand off cleanly'.
        """
        flight = bundle.get("flight", {})
        hotel = bundle.get("hotel", {})
        
        # Calculate nights from dates
        date_from = bundle.get("date_from") or (flight.get("departure_time", "")[:10] if flight else "")
        date_to = bundle.get("date_to") or ""
        
        nights = 3  # Default
        if date_from and date_to:
            try:
                d1 = datetime.fromisoformat(date_from)
                d2 = datetime.fromisoformat(date_to)
                nights = (d2 - d1).days
            except:
                pass
        
        # Generate individual quotes
        flight_quote = self.generate_flight_quote(flight, add_baggage, add_seat_selection)
        hotel_quote = self.generate_hotel_quote(hotel, nights, date_from)
        
        # Create full quote
        quote_id = f"QT{uuid.uuid4().hex[:8].upper()}"
        bundle_id = bundle.get("bundle_id", f"BN{uuid.uuid4().hex[:6].upper()}")
        
        # Quote valid for 30 minutes
        valid_until = datetime.utcnow() + timedelta(minutes=30)
        
        full_quote = FullQuote(
            quote_id=quote_id,
            bundle_id=bundle_id,
            flight_quote=flight_quote,
            hotel_quote=hotel_quote,
            quote_valid_until=valid_until.isoformat(),
            created_at=datetime.utcnow().isoformat()
        )
        
        full_quote.calculate_totals()
        
        # Generate summary
        full_quote.cancellation_summary = self._generate_cancellation_summary(flight_quote, hotel_quote)
        full_quote.important_notes = self._generate_important_notes(flight_quote, hotel_quote, bundle)
        
        logger.info(f"Generated quote {quote_id}: ${full_quote.grand_total:.2f} "
                   f"(saves ${full_quote.bundle_savings:.2f})")
        
        return full_quote
    
    def _is_international(self, origin: str, destination: str) -> bool:
        """Check if flight is international"""
        us_airports = {"SFO", "LAX", "JFK", "MIA", "ORD", "DFW", "DEN", "SEA", 
                       "BOS", "ATL", "LAS", "PHX", "HNL", "EWR", "IAD", "DCA"}
        
        origin_us = origin.upper() in us_airports
        dest_us = destination.upper() in us_airports
        
        return origin_us != dest_us
    
    def _generate_cancellation_summary(self, flight: FlightQuoteDetails, 
                                       hotel: HotelQuoteDetails) -> str:
        """Generate combined cancellation summary"""
        parts = []
        
        parts.append(f"Flight: {flight.cancellation_policy}")
        parts.append(f"Hotel: {hotel.cancellation_policy}")
        
        return " | ".join(parts)
    
    def _generate_important_notes(self, flight: FlightQuoteDetails,
                                  hotel: HotelQuoteDetails,
                                  bundle: Dict[str, Any]) -> List[str]:
        """Generate list of important notes"""
        notes = []
        
        # Flight notes
        if flight.stops > 0:
            notes.append(f"Flight has {flight.stops} stop(s)")
        
        if flight.change_fee > 0:
            notes.append(f"Flight change fee: ${flight.change_fee}")
        
        if flight.checked_bag_price > 0:
            notes.append(f"Checked bags: ${flight.checked_bag_price} each")
        
        # Hotel notes
        if hotel.resort_fee_per_night > 0:
            notes.append(f"Resort fee: ${hotel.resort_fee_per_night}/night (included in total)")
        
        if hotel.cancellation_deadline:
            notes.append(f"Cancel hotel by: {hotel.cancellation_deadline}")
        
        # Bundle notes
        notes.append("Bundle pricing locked for 30 minutes")
        notes.append("Prices subject to availability")
        
        return notes
    
    def quote_to_dict(self, quote: FullQuote) -> Dict[str, Any]:
        """Convert quote to dictionary for API response"""
        return {
            "quote_id": quote.quote_id,
            "bundle_id": quote.bundle_id,
            "flight_quote": {
                "flight_id": quote.flight_quote.flight_id,
                "airline": quote.flight_quote.airline,
                "route": f"{quote.flight_quote.origin} → {quote.flight_quote.destination}",
                "departure": quote.flight_quote.departure_time,
                "arrival": quote.flight_quote.arrival_time,
                "duration_minutes": quote.flight_quote.duration_minutes,
                "stops": quote.flight_quote.stops,
                "class": quote.flight_quote.flight_class,
                "pricing": {
                    "base_fare": quote.flight_quote.base_fare,
                    "taxes": quote.flight_quote.taxes,
                    "carrier_fee": quote.flight_quote.carrier_fee,
                    "baggage_fee": quote.flight_quote.baggage_fee,
                    "seat_selection_fee": quote.flight_quote.seat_selection_fee,
                    "total": quote.flight_quote.total
                },
                "baggage": {
                    "included": quote.flight_quote.baggage_included,
                    "checked_bag_price": quote.flight_quote.checked_bag_price
                },
                "policies": {
                    "change_fee": quote.flight_quote.change_fee,
                    "cancellation": quote.flight_quote.cancellation_policy
                }
            },
            "hotel_quote": {
                "hotel_id": quote.hotel_quote.hotel_id,
                "name": quote.hotel_quote.name,
                "city": quote.hotel_quote.city,
                "star_rating": quote.hotel_quote.star_rating,
                "room_type": quote.hotel_quote.room_type,
                "pricing": {
                    "rate_per_night": quote.hotel_quote.rate_per_night,
                    "nights": quote.hotel_quote.nights,
                    "subtotal": quote.hotel_quote.subtotal,
                    "resort_fee_total": quote.hotel_quote.resort_fee_total,
                    "taxes": quote.hotel_quote.taxes,
                    "total": quote.hotel_quote.total
                },
                "check_in": quote.hotel_quote.check_in_time,
                "check_out": quote.hotel_quote.check_out_time,
                "amenities": quote.hotel_quote.amenities_included,
                "policies": {
                    "cancellation": quote.hotel_quote.cancellation_policy,
                    "cancel_by": quote.hotel_quote.cancellation_deadline
                }
            },
            "summary": {
                "grand_total": quote.grand_total,
                "separate_booking_total": quote.separate_booking_total,
                "bundle_savings": quote.bundle_savings,
                "savings_percent": round((quote.bundle_savings / quote.separate_booking_total) * 100, 1) if quote.separate_booking_total > 0 else 0
            },
            "cancellation_summary": quote.cancellation_summary,
            "important_notes": quote.important_notes,
            "quote_valid_until": quote.quote_valid_until,
            "created_at": quote.created_at
        }


# ============================================
# Global Instance
# ============================================

quote_generator = QuoteGenerator()


# ============================================
# Convenience Functions
# ============================================

def generate_quote(bundle: Dict[str, Any], add_baggage: bool = False,
                   add_seat_selection: bool = False) -> Dict[str, Any]:
    """Generate a full quote and return as dict"""
    quote = quote_generator.generate_full_quote(bundle, add_baggage, add_seat_selection)
    return quote_generator.quote_to_dict(quote)
