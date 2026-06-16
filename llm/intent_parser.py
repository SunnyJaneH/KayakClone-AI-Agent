# llm/intent_parser.py
"""
Intent Parser for Concierge Agent
Extracts structured travel intent from natural language:
- Origin/destination
- Constraints (pet-friendly, no red-eye, etc.)
Implements: "Intent understanding with a single clarifying question max"
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger

# Try to import OpenAI for advanced parsing
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# ============================================
# Data Classes
# ============================================

@dataclass
class ParsedIntent:
    """Structured travel intent"""
    origin: Optional[str] = None
    destination: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    budget: Optional[float] = None
    travelers: int = 1
    constraints: List[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "budget": self.budget,
            "travelers": self.travelers,
            "constraints": self.constraints,
            "confidence": self.confidence,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question
        }


# ============================================
# Intent Parser
# ============================================

class IntentParser:
    """
    Parses natural language travel queries into structured intents.
    Uses rule-based parsing with optional LLM enhancement.
    """
    
    def __init__(self):
        # Common airport codes
        self.airport_codes = {
            # US Cities
            "sfo": "SFO", "san francisco": "SFO",
            "lax": "LAX", "los angeles": "LAX", "la": "LAX",
            "jfk": "JFK", "new york": "JFK", "nyc": "JFK",
            "mia": "MIA", "miami": "MIA",
            "ord": "ORD", "chicago": "ORD",
            "dfw": "DFW", "dallas": "DFW",
            "den": "DEN", "denver": "DEN",
            "sea": "SEA", "seattle": "SEA",
            "bos": "BOS", "boston": "BOS",
            "atl": "ATL", "atlanta": "ATL",
            "hnl": "HNL", "honolulu": "HNL", "hawaii": "HNL",
            "las": "LAS", "vegas": "LAS", "las vegas": "LAS",
            "phx": "PHX", "phoenix": "PHX",
            "slc": "SLC", "salt lake": "SLC",
            
            # Indian Cities
            "delhi": "DEL", "del": "DEL", "new delhi": "DEL",
            "mumbai": "BOM", "bom": "BOM", "bombay": "BOM",
            "bangalore": "BLR", "blr": "BLR", "bengaluru": "BLR",
            "chennai": "MAA", "maa": "MAA", "madras": "MAA",
            "kolkata": "CCU", "ccu": "CCU", "calcutta": "CCU",
            "hyderabad": "HYD", "hyd": "HYD",
            "ahmedabad": "AMD", "amd": "AMD",
            "pune": "PNQ", "pnq": "PNQ",
            "jaipur": "JAI", "jai": "JAI",
            "goa": "GOI", "goi": "GOI",
            
            # International
            "tokyo": "NRT", "nrt": "NRT", "hnd": "HND",
            "london": "LHR", "lhr": "LHR",
            "paris": "CDG", "cdg": "CDG",
            "rome": "FCO", "fco": "FCO",
            "cancun": "CUN", "cun": "CUN",
        }
        
        # Destination keywords (for "anywhere warm" type queries)
        self.destination_keywords = {
            "warm": ["MIA", "CUN", "HNL", "PHX"],
            "beach": ["MIA", "CUN", "HNL"],
            "mountain": ["DEN", "SLC"],
            "city": ["JFK", "ORD", "LAX"],
            "europe": ["CDG", "LHR", "FCO"],
            "asia": ["NRT", "HND"],
            "tropical": ["HNL", "CUN"],
        }
        
        # Constraint patterns
        self.constraint_patterns = {
            "pet-friendly": [r"pet[\s-]*friendly", r"with\s+pet", r"dog", r"cat", r"bring.*pet"],
            "no-red-eye": [r"no\s+red[\s-]*eye", r"avoid.*red[\s-]*eye", r"daytime", r"morning\s+flight"],
            "direct-flight": [r"direct", r"non[\s-]*stop", r"no\s+stops", r"no\s+layover"],
            "refundable": [r"refundable", r"free\s+cancellation", r"flexible"],
            "breakfast": [r"breakfast", r"morning\s+meal"],
            "near-transit": [r"near\s+transit", r"public\s+transport", r"subway", r"metro"],
            "business-class": [r"business\s+class", r"first\s+class", r"premium"],
            "budget": [r"cheap", r"budget", r"affordable", r"low\s+cost"],
        }
        
        # Month mapping
        self.months = {
            "jan": 1, "january": 1,
            "feb": 2, "february": 2,
            "mar": 3, "march": 3,
            "apr": 4, "april": 4,
            "may": 5,
            "jun": 6, "june": 6,
            "jul": 7, "july": 7,
            "aug": 8, "august": 8,
            "sep": 9, "september": 9, "sept": 9,
            "oct": 10, "october": 10,
            "nov": 11, "november": 11,
            "dec": 12, "december": 12
        }
    
    def parse(self, query: str, context: Optional[Dict[str, Any]] = None) -> ParsedIntent:
        """
        Parse a natural language query into structured intent.
        
        Args:
            query: User's natural language query
            context: Optional session context for multi-turn conversations
            
        Returns:
            ParsedIntent with extracted information
        """
        query_lower = query.lower().strip()
        
        intent = ParsedIntent()
        
        # Extract components
        intent.origin = self._extract_origin(query_lower, context)
        intent.destination = self._extract_destination(query_lower)
        intent.date_from, intent.date_to = self._extract_dates(query_lower)
        intent.budget = self._extract_budget(query_lower)
        intent.travelers = self._extract_travelers(query_lower)
        intent.constraints = self._extract_constraints(query_lower)
        
        # Calculate confidence
        intent.confidence = self._calculate_confidence(intent)
        
        # Check if clarification is needed
        intent.needs_clarification, intent.clarification_question = self._check_clarification_needed(intent)
        
        logger.info(f"Parsed intent: destination={intent.destination}, "
                   f"dates={intent.date_from}-{intent.date_to}, "
                   f"budget={intent.budget}, confidence={intent.confidence:.2f}")
        
        return intent
    
    def _extract_origin(self, query: str, context: Optional[Dict] = None) -> Optional[str]:
        """Extract origin airport/city"""
        
        # First, try "from X to Y" pattern (most specific)
        from_to_pattern = r"from\s+(\w+)\s+to\s+"
        match = re.search(from_to_pattern, query)
        if match:
            origin = match.group(1).lower().strip()
            if origin in self.airport_codes:
                return self.airport_codes[origin]
        
        # Pattern: "from SFO", "departing from San Francisco"
        patterns = [
            r"from\s+(\w+)(?:\s|,|$)",
            r"departing\s+(?:from\s+)?(\w+)",
            r"leaving\s+(?:from\s+)?(\w+)",
            r"(\w{3})\s+to\s+",  # SFO to ...
        ]
        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                location = match.group(1).lower().strip()
                if location in self.airport_codes:
                    return self.airport_codes[location]
        
        # Check context for previous origin
        if context and context.get("origin"):
            return context["origin"]
        
        return None

    def _extract_destination(self, query: str) -> Optional[str]:
        """Extract destination airport/city"""
        
        # First, try "from X to Y" pattern (most specific)
        from_to_pattern = r"from\s+(\w+(?:\s+\w+)?)\s+to\s+(\w+)"
        match = re.search(from_to_pattern, query)
        if match:
            destination = match.group(2).lower()
            if destination in self.airport_codes:
                return self.airport_codes[destination]
        
        # Pattern: "to Miami", "going to NYC" - but skip common verbs
        skip_words = {"travel", "go", "fly", "visit", "book", "find", "search", "get", "see", "the", "next", "this"}
        
        patterns = [
            r"to\s+(\w+(?:\s+\w+)?)",
            r"going\s+(?:to\s+)?(\w+(?:\s+\w+)?)",
            r"visiting\s+(\w+(?:\s+\w+)?)",
            r"trip\s+to\s+(\w+(?:\s+\w+)?)",
            r"flight\s+to\s+(\w+(?:\s+\w+)?)",
            r"flights\s+to\s+(\w+(?:\s+\w+)?)",
            r"deals\s+to\s+(\w+(?:\s+\w+)?)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, query)
            for location in matches:
                location = location.lower().strip()
                
                # Skip common verbs
                if location.split()[0] in skip_words:
                    continue
                
                # Check if full match is in airport codes
                if location in self.airport_codes:
                    return self.airport_codes[location]
                
                # Check first word (fix for "to JFK next week" where "JFK next" is matched)
                first_word = location.split()[0]
                if first_word in self.airport_codes:
                    return self.airport_codes[first_word]
        
        # Check for keyword destinations ("anywhere warm")
        for keyword, destinations in self.destination_keywords.items():
            if keyword in query:
                return destinations[0]
        
        # Direct city name matching (for queries like "Mumbai next week")
        words = query.split()
        for word in words:
            word_lower = word.lower().strip(",.!?")
            if word_lower in self.airport_codes:
                return self.airport_codes[word_lower]

        return None
    
    def _extract_dates(self, query: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract travel dates"""
        today = datetime.now()
        year = today.year
        
        # Pattern: "Oct 25-27", "October 25 to 27"
        range_pattern = r"(\w+)\s+(\d{1,2})[-–to]+\s*(\d{1,2})"
        match = re.search(range_pattern, query)
        if match:
            month_str = match.group(1).lower()
            day1 = int(match.group(2))
            day2 = int(match.group(3))
            
            if month_str in self.months:
                month = self.months[month_str]
                # Adjust year if month is in the past
                if month < today.month or (month == today.month and day1 < today.day):
                    year += 1
                try:
                    date_from = datetime(year, month, day1)
                    date_to = datetime(year, month, day2)
                    return date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        
        # Pattern: "December 20-25" or "Dec 20-25"
        range_pattern2 = r"(\w+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})"
        match = re.search(range_pattern2, query)
        if match:
            month_str = match.group(1).lower()
            day1 = int(match.group(2))
            day2 = int(match.group(3))
            
            if month_str in self.months:
                month = self.months[month_str]
                if month < today.month or (month == today.month and day1 < today.day):
                    year += 1
                try:
                    date_from = datetime(year, month, day1)
                    date_to = datetime(year, month, day2)
                    return date_from.strftime("%Y-%m-%d"), date_to.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        
        # Pattern: "next weekend"
        if "next weekend" in query:
            days_until_saturday = (5 - today.weekday()) % 7
            if days_until_saturday == 0:
                days_until_saturday = 7
            saturday = today + timedelta(days=days_until_saturday + 7)
            sunday = saturday + timedelta(days=1)
            return saturday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        
        # Pattern: "this weekend"
        if "this weekend" in query or "weekend" in query:
            days_until_saturday = (5 - today.weekday()) % 7
            if days_until_saturday == 0:
                days_until_saturday = 7
            saturday = today + timedelta(days=days_until_saturday)
            sunday = saturday + timedelta(days=1)
            return saturday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        
        # Pattern: "next week"
        if "next week" in query:
            next_monday = today + timedelta(days=(7 - today.weekday()))
            departure_date = next_monday.strftime("%Y-%m-%d")
            return_date = (next_monday + timedelta(days=5)).strftime("%Y-%m-%d")
            return departure_date, return_date
        
        # Pattern: single date "Oct 25" or "October 25"
        single_date_pattern = r"(\w+)\s+(\d{1,2})(?!\s*[-–])"
        match = re.search(single_date_pattern, query)
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            
            if month_str in self.months:
                month = self.months[month_str]
                if month < today.month or (month == today.month and day < today.day):
                    year += 1
                try:
                    date_from_obj = datetime(year, month, day)
                    date_to_obj = datetime(year, month, day) + timedelta(days=3)
                    return date_from_obj.strftime("%Y-%m-%d"), date_to_obj.strftime("%Y-%m-%d")
                except ValueError:
                    pass
        
        return None, None
    
    def _extract_budget(self, query: str) -> Optional[float]:
        """Extract budget amount"""
        # Pattern: "$1000", "1000 dollars", "budget $1000", "under $1000"
        patterns = [
            r"\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
            r"(\d+(?:,\d{3})*)\s*(?:dollars|usd)",
            r"budget\s*(?:of\s*)?\$?\s*(\d+(?:,\d{3})*)",
            r"under\s*\$?\s*(\d+(?:,\d{3})*)",
            r"max(?:imum)?\s*\$?\s*(\d+(?:,\d{3})*)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    return float(amount_str)
                except ValueError:
                    pass
        
        return None
    
    def _extract_travelers(self, query: str) -> int:
        """Extract number of travelers"""
        # Pattern: "for 2", "2 people", "two travelers"
        patterns = [
            r"for\s+(\d+)",
            r"(\d+)\s+(?:people|travelers|passengers|adults)",
            r"(\d+)\s+of\s+us",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # Word numbers
        word_numbers = {
            "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8
        }
        for word, num in word_numbers.items():
            if word in query:
                return num
        
        return 1  # Default to 1
    
    def _extract_constraints(self, query: str) -> List[str]:
        """Extract travel constraints/preferences"""
        constraints = []
        
        for constraint_name, patterns in self.constraint_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    constraints.append(constraint_name)
                    break
        
        return constraints
    
    def _calculate_confidence(self, intent: ParsedIntent) -> float:
        """Calculate confidence score based on extracted data"""
        score = 0.0
        
        if intent.destination:
            score += 0.3
        if intent.date_from and intent.date_to:
            score += 0.25
        elif intent.date_from:
            score += 0.15
        if intent.budget:
            score += 0.2
        if intent.origin:
            score += 0.15
        if intent.constraints:
            score += 0.1
        
        return min(score, 1.0)
    
    def _check_clarification_needed(self, intent: ParsedIntent) -> Tuple[bool, Optional[str]]:
        """
        Check if clarification is needed.
        Returns at most ONE clarifying question that asks for ALL missing required fields.
        (As per assignment requirement: "single clarifying question max")
        """
        missing = []
        
        if not intent.origin:
            missing.append("departure city (e.g., Delhi, SFO)")
        
        if not intent.destination:
            missing.append("destination (e.g., Mumbai, Tokyo, 'anywhere warm')")
        
        if not intent.date_from:
            missing.append("travel dates (e.g., 'December 15-20', 'next weekend')")
        
        if missing:
            question = f"I need a few more details: {' and '.join(missing)}. Could you provide these?"
            return True, question
        
        return False, None
    
    def merge_with_context(self, intent: ParsedIntent, context: Dict[str, Any]) -> ParsedIntent:
        """
        Merge new intent with existing session context.
        Implements 'Refine without starting over'.
        """
        # Only update fields that are present in new intent
        if not intent.origin and context.get("origin"):
            intent.origin = context["origin"]
        if not intent.destination and context.get("destination"):
            intent.destination = context["destination"]
        if not intent.date_from and context.get("date_from"):
            intent.date_from = context["date_from"]
        if not intent.date_to and context.get("date_to"):
            intent.date_to = context["date_to"]
        if not intent.budget and context.get("budget"):
            intent.budget = context["budget"]
        if intent.travelers == 1 and context.get("travelers", 1) > 1:
            intent.travelers = context["travelers"]
        
        # Merge constraints (append new, don't replace)
        existing_constraints = context.get("constraints", [])
        intent.constraints = list(set(existing_constraints + intent.constraints))
        
        # Recalculate confidence
        intent.confidence = self._calculate_confidence(intent)
        intent.needs_clarification, intent.clarification_question = self._check_clarification_needed(intent)
        
        return intent


# ============================================
# Global Instance
# ============================================

intent_parser = IntentParser()


# ============================================
# Convenience Function
# ============================================

def parse_intent(query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Parse a query and return dict"""
    intent = intent_parser.parse(query, context)
    if context:
        intent = intent_parser.merge_with_context(intent, context)
    return intent.to_dict()
