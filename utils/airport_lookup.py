"""
Airport Lookup Service
Uses airports.csv data (imported to MongoDB) to convert city names → IATA codes
"""

import os
import logging
from typing import Optional, Dict, List
from pymongo import MongoClient

logger = logging.getLogger(__name__)

class AirportLookup:
    """
    Airport lookup service for converting city names to IATA codes
    and validating routes.
    """
    
    def __init__(self):
        """Initialize with MongoDB connection"""
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        mongo_db = os.getenv("MONGO_DB", "kayak_doc")
        
        try:
            client = MongoClient(mongo_uri)
            self.db = client[mongo_db]
            self._build_cache()
            logger.info("AirportLookup initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize AirportLookup: {e}")
            self.db = None
            self.city_cache = {}
            self.iata_cache = {}
    
    def _build_cache(self):
        """Build city→IATA and IATA→info caches for fast lookups"""
        if self.db is None:
            return
        
        try:
            airports = self.db.airports.find({})
            self.city_cache = {}
            self.iata_cache = {}
            
            for apt in airports:
                city = apt.get("city", "").lower().strip()
                iata = apt.get("iata", "").strip().upper()
                name = apt.get("name", "").lower().strip()
                
                if not iata or len(iata) != 3:
                    continue
                
                # Store IATA → full info
                self.iata_cache[iata] = apt
                
                # Store city → IATA (handle multiple airports per city)
                if city:
                    if city not in self.city_cache:
                        self.city_cache[city] = []
                    if iata not in self.city_cache[city]:
                        self.city_cache[city].append(iata)
                
                # Also index by airport name keywords
                if name:
                    # Extract city from name (e.g., "San Francisco International" → "san francisco")
                    name_words = name.split()
                    for word in name_words:
                        if word not in ["international", "airport", "regional", "municipal"]:
                            key = word.lower()
                            if key not in self.city_cache:
                                self.city_cache[key] = []
                            if iata not in self.city_cache[key]:
                                self.city_cache[key].append(iata)
            
            logger.info(f"Built cache: {len(self.iata_cache)} airports, {len(self.city_cache)} city keys")
        except Exception as e:
            logger.error(f"Error building airport cache: {e}")
            self.city_cache = {}
            self.iata_cache = {}
    
    def city_to_iata(self, city_name: str, prefer_major: bool = True) -> Optional[str]:
        """
        Convert city name to IATA code
        
        Args:
            city_name: City name (e.g., "Miami", "New York", "NYC")
            prefer_major: If multiple airports, prefer major ones (JFK over LGA for NYC)
        
        Returns:
            IATA code (e.g., "MIA") or None if not found
        """
        try:
            if not city_name or not self.city_cache:
                return None
        except Exception:
            return None
        
        city_lower = city_name.lower().strip()
        
        # Direct match
        if city_lower in self.city_cache:
            iatas = self.city_cache[city_lower]
            if prefer_major:
                # Prefer major airports (common codes)
                major_airports = ["JFK", "LAX", "SFO", "ORD", "DFW", "MIA", "LHR", "CDG", "NRT"]
                for major in major_airports:
                    if major in iatas:
                        return major
            return iatas[0] if iatas else None
        
        # Partial match (e.g., "new york" contains "york")
        for city, iatas in self.city_cache.items():
            if city_lower in city or city in city_lower:
                if prefer_major:
                    major_airports = ["JFK", "LAX", "SFO", "ORD", "DFW", "MIA", "LHR", "CDG", "NRT"]
                    for major in major_airports:
                        if major in iatas:
                            return major
                return iatas[0] if iatas else None
        
        # Common city aliases
        aliases = {
            "nyc": "JFK",
            "new york": "JFK",
            "ny": "JFK",
            "san francisco": "SFO",
            "sf": "SFO",
            "los angeles": "LAX",
            "la": "LAX",
            "chicago": "ORD",
            "miami": "MIA",
            "london": "LHR",
            "paris": "CDG",
            "tokyo": "NRT",
            "delhi": "DEL",
            "mumbai": "BOM",
            "bangalore": "BLR",
            "kolkata": "CCU",
            "hyderabad": "HYD",
            "chennai": "MAA"
        }
        
        if city_lower in aliases:
            return aliases[city_lower]
        
        return None
    
    def get_airport_info(self, iata: str) -> Optional[Dict]:
        """
        Get full airport information by IATA code
        
        Args:
            iata: IATA code (e.g., "MIA")
        
        Returns:
            Airport dict with name, city, country, coordinates, etc.
        """
        if not iata or not self.iata_cache:
            return None
        
        iata_upper = iata.strip().upper()
        return self.iata_cache.get(iata_upper)
    
    def validate_route(self, origin: str, destination: str) -> bool:
        """
        Validate if a flight route exists
        
        Args:
            origin: Origin IATA code
            destination: Destination IATA code
        
        Returns:
            True if route exists in routes collection
        """
        if self.db is None:
            return True  # Assume valid if DB not available
        
        try:
            origin_upper = origin.strip().upper()
            dest_upper = destination.strip().upper()
            
            # Use max_time_ms to prevent hanging
            route = self.db.routes.find_one(
                {"origin": origin_upper, "destination": dest_upper},
                max_time_ms=1000  # 1 second timeout
            )
            
            return route is not None
        except Exception as e:
            logger.debug(f"Error validating route (non-critical): {e}")
            return True  # Assume valid on error
    
    def find_alternative_routes(self, origin: str, destination: str, max_stops: int = 1) -> List[Dict]:
        """
        Find alternative routes with connections
        
        Args:
            origin: Origin IATA code
            destination: Destination IATA code
            max_stops: Maximum number of stops (0=direct, 1=one stop)
        
        Returns:
            List of route dicts with connection airports
        """
        if self.db is None:
            return []
        
        try:
            origin_upper = origin.strip().upper()
            dest_upper = destination.strip().upper()
            
            # Direct route
            if max_stops >= 0:
                direct = self.db.routes.find_one({
                    "origin": origin_upper,
                    "destination": dest_upper,
                    "stops": 0
                })
                if direct:
                    return [{"origin": origin_upper, "destination": dest_upper, "stops": 0}]
            
            # One-stop routes
            if max_stops >= 1:
                # Find routes: origin → connection → destination
                origin_routes = list(self.db.routes.find({
                    "origin": origin_upper,
                    "stops": {"$lte": 1}
                }).limit(100))
                
                dest_routes = list(self.db.routes.find({
                    "destination": dest_upper,
                    "stops": {"$lte": 1}
                }).limit(100))
                
                # Find connections
                origin_dests = {r["destination"] for r in origin_routes}
                dest_origins = {r["origin"] for r in dest_routes}
                connections = origin_dests.intersection(dest_origins)
                
                alternatives = []
                for conn in list(connections)[:5]:  # Limit to 5 alternatives
                    alternatives.append({
                        "origin": origin_upper,
                        "connection": conn,
                        "destination": dest_upper,
                        "stops": 1
                    })
                
                return alternatives
            
            return []
        except Exception as e:
            logger.error(f"Error finding alternative routes: {e}")
            return []

# Global instance (singleton pattern)
_airport_lookup_instance = None

def get_airport_lookup() -> AirportLookup:
    """Get or create global AirportLookup instance"""
    global _airport_lookup_instance
    if _airport_lookup_instance is None:
        _airport_lookup_instance = AirportLookup()
    return _airport_lookup_instance

