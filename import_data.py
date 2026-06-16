"""
Data Import Script for Kayak Project
Imports flights, hotels, and airports data into:
- MongoDB (for existing services compatibility)
- SQLite via SQLModel (Assignment requirement)

With Deal Score fields: avg_30d_price, discount_percent, has_promo, promo_end_date
Added: neighbourhood, near-transit tag, Indian city mapping for hotels
"""

import pandas as pd
from pymongo import MongoClient
import mysql.connector
import os
import sys
import random
import json
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# SQLModel imports
try:
    from sqlmodel import Session
    from models.database import get_engine, init_db
    from models.deals_entities import FlightDeal, HotelDeal, Airport
    SQLMODEL_AVAILABLE = True
except ImportError:
    SQLMODEL_AVAILABLE = False
    print("Warning: SQLModel not available, will only import to MongoDB")

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "kayak_doc")

# MySQL connection
MYSQL_HOST = os.getenv("DB_HOST", "localhost")
MYSQL_PORT = int(os.getenv("DB_PORT", 3306))
MYSQL_USER = os.getenv("DB_USER", "root")
MYSQL_PASSWORD = os.getenv("DB_PASSWORD", "password")
MYSQL_DB = os.getenv("DB_NAME_USERS", "kayak_users")

# Data directory
# In Docker: data/ is mounted to /data
DATA_DIR = os.getenv("DATA_DIR", "/data")

# ============================================
# City/Country Mapping for Hotels
# Hotels CSV has European countries, Flights CSV has Indian cities
# We map European countries to Indian cities for matching
# ============================================

COUNTRY_TO_INDIAN_CITY = {
    "PRT": {"city": "Mumbai", "code": "BOM"},      # Portugal → Mumbai
    "GBR": {"city": "Delhi", "code": "DEL"},       # UK → Delhi
    "ESP": {"city": "Bangalore", "code": "BLR"},   # Spain → Bangalore
    "FRA": {"city": "Chennai", "code": "MAA"},     # France → Chennai
    "DEU": {"city": "Kolkata", "code": "CCU"},     # Germany → Kolkata
    "ITA": {"city": "Hyderabad", "code": "HYD"},   # Italy → Hyderabad
    "NLD": {"city": "Mumbai", "code": "BOM"},      # Netherlands → Mumbai
    "IRL": {"city": "Delhi", "code": "DEL"},       # Ireland → Delhi
    "BEL": {"city": "Bangalore", "code": "BLR"},   # Belgium → Bangalore
    "BRA": {"city": "Chennai", "code": "MAA"},     # Brazil → Chennai
    "USA": {"city": "Mumbai", "code": "BOM"},      # USA → Mumbai
    "CHE": {"city": "Delhi", "code": "DEL"},       # Switzerland → Delhi
    "CN": {"city": "Kolkata", "code": "CCU"},      # China → Kolkata
    "AUT": {"city": "Hyderabad", "code": "HYD"},   # Austria → Hyderabad
}

# Default mapping for unknown countries
DEFAULT_CITIES = [
    {"city": "Mumbai", "code": "BOM"},
    {"city": "Delhi", "code": "DEL"},
    {"city": "Bangalore", "code": "BLR"},
    {"city": "Chennai", "code": "MAA"},
    {"city": "Kolkata", "code": "CCU"},
    {"city": "Hyderabad", "code": "HYD"},
]

# Neighbourhoods for Indian cities (simulated)
CITY_NEIGHBOURHOODS = {
    "Mumbai": ["Bandra", "Andheri", "Juhu", "Colaba", "Worli", "Powai", "Lower Parel"],
    "Delhi": ["Connaught Place", "Karol Bagh", "Paharganj", "Aerocity", "Dwarka", "Saket"],
    "Bangalore": ["MG Road", "Koramangala", "Whitefield", "Indiranagar", "Electronic City"],
    "Chennai": ["T Nagar", "Anna Nagar", "Adyar", "Egmore", "Mylapore", "OMR"],
    "Kolkata": ["Park Street", "Salt Lake", "New Town", "Howrah", "Esplanade"],
    "Hyderabad": ["Banjara Hills", "Jubilee Hills", "Hitech City", "Gachibowli", "Secunderabad"],
}

# City to airport code mapping (for flights)
CITY_TO_AIRPORT = {
    "Delhi": "DEL",
    "Mumbai": "BOM",
    "Bangalore": "BLR",
    "Kolkata": "CCU",
    "Hyderabad": "HYD",
    "Chennai": "MAA"
}


def connect_mongo():
    """Connect to MongoDB"""
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    print(f"Connected to MongoDB: {MONGO_URI}/{MONGO_DB}")
    return db


def connect_mysql():
    """Connect to MySQL"""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB
        )
        print(f"Connected to MySQL: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
        return conn
    except Exception as e:
        print(f"MySQL Connection Error: {e}")
        return None


def get_indian_city(country_code: str, index: int) -> dict:
    """Map country code to Indian city for hotel location"""
    if country_code in COUNTRY_TO_INDIAN_CITY:
        return COUNTRY_TO_INDIAN_CITY[country_code]
    # Use index to distribute unknown countries across cities
    return DEFAULT_CITIES[index % len(DEFAULT_CITIES)]


def get_neighbourhood(city: str, index: int) -> str:
    """Get a neighbourhood for a city based on index"""
    neighbourhoods = CITY_NEIGHBOURHOODS.get(city, ["City Center"])
    return neighbourhoods[index % len(neighbourhoods)]


def import_airports(db, filepath):
    """Import airports data to MongoDB and SQLite"""
    print(f"\n=== Importing Airports from {filepath} ===")
    
    df = pd.read_csv(filepath)
    print(f"Loaded {len(df)} airports")
    
    # Clean and transform
    airports = []
    sqlite_airports = []
    
    for _, row in df.iterrows():
        iata = row.get("IATA", "")
        
        # Only add if has valid IATA code
        if not iata or str(iata).lower() in ["", "nan", "none"]:
            continue
            
        airport = {
            "airport_id": iata,
            "name": row.get("AirportName", ""),
            "iata": iata,
            "icao": row.get("ICAO", ""),
            "city": row.get("City_Name", ""),
            "country": row.get("Country_Name", ""),
            "country_code": row.get("Country_CodeA2", ""),
            "timezone": row.get("TimeZone", ""),
            "latitude": float(row.get("GeoPointLat", 0)) if pd.notna(row.get("GeoPointLat")) else 0,
            "longitude": float(row.get("GeoPointLong", 0)) if pd.notna(row.get("GeoPointLong")) else 0
        }
        airports.append(airport)
        
        # SQLModel entity
        if SQLMODEL_AVAILABLE:
            sqlite_airports.append(Airport(
                iata=iata,
                icao=row.get("ICAO", "") or None,
                name=row.get("AirportName", ""),
                city=row.get("City_Name", ""),
                country=row.get("Country_Name", ""),
                country_code=row.get("Country_CodeA2", "") or None,
                timezone=row.get("TimeZone", "") or None,
                latitude=float(row.get("GeoPointLat", 0)) if pd.notna(row.get("GeoPointLat")) else 0,
                longitude=float(row.get("GeoPointLong", 0)) if pd.notna(row.get("GeoPointLong")) else 0
            ))
    
    # Insert to MongoDB
    collection = db["airports"]
    collection.drop()
    if airports:
        collection.insert_many(airports)
        collection.create_index("iata", unique=True)
    
    # Insert to SQLite
    if SQLMODEL_AVAILABLE and sqlite_airports:
        engine = get_engine()
        with Session(engine) as session:
            # Clear existing
            session.query(Airport).delete()
            session.commit()
            # Insert new
            for airport in sqlite_airports:
                session.add(airport)
            session.commit()
        print(f"Imported {len(sqlite_airports)} airports to SQLite")
    
    print(f"Imported {len(airports)} airports to MongoDB")
    return len(airports)


def import_flights(db, filepath, limit=10000):
    """Import flights data to MongoDB and SQLite with Deal Score fields"""
    print(f"\n=== Importing Flights from {filepath} ===")
    
    df = pd.read_csv(filepath, nrows=limit)
    print(f"Loaded {len(df)} flights")
    
    # Set random seed for reproducibility
    random.seed(42)
    
    flights = []
    sqlite_flights = []
    
    for idx, row in df.iterrows():
        source = row.get("source_city", "")
        dest = row.get("destination_city", "")
        price = float(row.get("price", 0)) if pd.notna(row.get("price")) else 0
        
        # Generate Deal Score fields based on flight_id hash for consistency
        hash_val = hash(f"FL{idx:06d}") % 100
        
        # 1. Discount: 5% to 30% (Assignment: >=15% below 30-day avg)
        discount_percent = 5 + (hash_val % 26)
        avg_30d_price = price / (1 - discount_percent / 100) if discount_percent < 100 else price * 1.2
        
        # 2. Inventory scarcity (Assignment: limited inventory)
        available_seats = 3 + (hash_val % 50)
        
        # 3. Promo (Assignment: promo end date, -10% to -25% dips)
        has_promo = hash_val % 3 == 0
        promo_end_date = None
        if has_promo:
            days_until_end = 1 + (hash_val % 14)
            promo_end_date = (datetime.now() + timedelta(days=days_until_end)).isoformat()
        
        # Parse stops
        stops = 0 if row.get("stops") == "zero" else (1 if row.get("stops") == "one" else 2)
        
        # Build tags
        tags = []
        if stops == 0:
            tags.append("direct-flight")
        if has_promo:
            tags.append("promo")
        if row.get("class", "").lower() == "business":
            tags.append("business-class")
        
        # Calculate Deal Score (0-100)
        discount_score = min(30, discount_percent)
        scarcity_score = 20 if available_seats < 10 else (10 if available_seats < 20 else 0)
        promo_score = 15 if has_promo else 0
        direct_score = 10 if stops == 0 else 0
        deal_score = min(95, max(30, 25 + discount_score + scarcity_score + promo_score + direct_score))
        
        origin_code = CITY_TO_AIRPORT.get(source, source[:3].upper() if source else "XXX")
        dest_code = CITY_TO_AIRPORT.get(dest, dest[:3].upper() if dest else "XXX")
        
        flight = {
            "flight_id": f"FL{idx:06d}",
            "airline": row.get("airline", "Unknown"),
            "flight_number": row.get("flight", ""),
            "origin": origin_code,
            "origin_city": source,
            "destination": dest_code,
            "destination_city": dest,
            "departure_time": row.get("departure_time", ""),
            "arrival_time": row.get("arrival_time", ""),
            "duration": float(row.get("duration", 0)) if pd.notna(row.get("duration")) else 0,
            "stops": stops,
            "class": row.get("class", "Economy"),
            "price": price,
            "days_left": int(row.get("days_left", 30)) if pd.notna(row.get("days_left")) else 30,
            # Deal Score fields
            "avg_30d_price": round(avg_30d_price, 2),
            "discount_percent": discount_percent,
            "available_seats": available_seats,
            "has_promo": has_promo,
            "promo_end_date": promo_end_date,
            "deal_score": deal_score,
            "tags": tags,
            "rating": 4.0
        }
        flights.append(flight)
        
        # SQLModel entity
        if SQLMODEL_AVAILABLE:
            sqlite_flights.append(FlightDeal(
                flight_id=f"FL{idx:06d}",
                origin=origin_code,
                origin_city=source,
                destination=dest_code,
                destination_city=dest,
                airline=row.get("airline", "Unknown"),
                flight_number=row.get("flight", "") or None,
                departure_time=row.get("departure_time", "") or None,
                arrival_time=row.get("arrival_time", "") or None,
                duration=float(row.get("duration", 0)) if pd.notna(row.get("duration")) else 0,
                stops=stops,
                flight_class=row.get("class", "Economy"),
                price=price,
                avg_30d_price=round(avg_30d_price, 2),
                discount_percent=discount_percent,
                available_seats=available_seats,
                has_promo=has_promo,
                promo_end_date=promo_end_date,
                deal_score=deal_score,
                tags=json.dumps(tags),
                rating=4.0,
                days_left=int(row.get("days_left", 30)) if pd.notna(row.get("days_left")) else 30
            ))
    
    # Insert to MongoDB
    collection = db["flights"]
    collection.drop()
    if flights:
        collection.insert_many(flights)
        collection.create_index("flight_id", unique=True)
        collection.create_index("origin")
        collection.create_index("destination")
        collection.create_index("price")
        collection.create_index("deal_score")
    
    # Insert to SQLite
    if SQLMODEL_AVAILABLE and sqlite_flights:
        engine = get_engine()
        with Session(engine) as session:
            session.query(FlightDeal).delete()
            session.commit()
            for flight in sqlite_flights:
                session.add(flight)
            session.commit()
        print(f"Imported {len(sqlite_flights)} flights to SQLite")
    
    print(f"Imported {len(flights)} flights to MongoDB")
    return len(flights)


def import_hotels(db, filepath, limit=10000):
    """
    Import hotels data to MongoDB and SQLite with:
    - Deal Score fields
    - Indian city mapping (Assignment: match with flights)
    - Neighbourhood (Assignment requirement)
    - Near-transit tag (Assignment requirement)
    """
    print(f"\n=== Importing Hotels from {filepath} ===")
    
    df = pd.read_csv(filepath, nrows=limit * 2)
    print(f"Loaded {len(df)} hotel bookings")
    
    random.seed(123)
    
    hotels = []
    sqlite_hotels = []
    seen_hotels = set()
    skipped_zero_price = 0
    
    for idx, row in df.iterrows():
        hotel_type = row.get("hotel", "Hotel")
        country_code = row.get("country", "Unknown")
        
        hotel_key = f"{hotel_type}_{country_code}_{idx}"
        if hotel_key in seen_hotels:
            continue
        seen_hotels.add(hotel_key)
        
        raw_adr = row.get("adr")
        if pd.isna(raw_adr) or float(raw_adr) <= 0:
            skipped_zero_price += 1
            continue
        
        adr = float(raw_adr)
        hotel_idx = len(hotels)
        hash_val = hash(f"HT{hotel_idx:06d}") % 100
        
        # Map to Indian city (Assignment: make hotels match flights)
        city_info = get_indian_city(country_code, hotel_idx)
        city = city_info["city"]
        city_code = city_info["code"]
        
        # Get neighbourhood (Assignment requirement)
        neighbourhood = get_neighbourhood(city, hotel_idx)
        
        # Deal Score fields
        discount_percent = 5 + (hash_val % 31)  # 5% to 35%
        avg_30d_price = adr / (1 - discount_percent / 100) if discount_percent < 100 else adr * 1.2
        available_rooms = 2 + (hash_val % 20)
        
        has_promo = hash_val % 4 == 0
        promo_end_date = None
        if has_promo:
            days_until_end = 1 + (hash_val % 10)
            promo_end_date = (datetime.now() + timedelta(days=days_until_end)).isoformat()
        
        # Star rating
        star_rating = 4 if hotel_type == "Resort Hotel" and adr > 150 else (3 if adr > 100 else 2)
        
        # Amenities
        amenities = []
        meal = row.get("meal", "")
        if meal in ["BB", "HB", "FB"]:
            amenities.append("breakfast")
        if row.get("required_car_parking_spaces", 0) > 0:
            amenities.append("parking")
        if hotel_type == "Resort Hotel":
            amenities.extend(["pool", "spa"])
        amenities.append("wifi")
        
        is_refundable = row.get("deposit_type", "") == "No Deposit"
        
        # Near transit (Assignment requirement) - 40% chance
        near_transit = hash_val % 5 < 2
        
        # Pet friendly - based on hotel type
        pet_friendly = hotel_type == "Resort Hotel" and hash_val % 3 == 0
        
        # Build tags (Assignment: Pet-friendly, Near transit, Breakfast)
        tags = list(amenities)
        if is_refundable:
            tags.append("refundable")
        if near_transit:
            tags.append("near-transit")
        if pet_friendly:
            tags.append("pet-friendly")
        
        # Calculate Deal Score
        discount_score = min(35, discount_percent)
        scarcity_score = 20 if available_rooms < 5 else (10 if available_rooms < 10 else 0)
        promo_score = 15 if has_promo else 0
        star_score = star_rating * 3
        refund_score = 5 if is_refundable else 0
        deal_score = min(95, max(30, 15 + discount_score + scarcity_score + promo_score + star_score + refund_score))
        
        # Listing date (Assignment requirement)
        listing_date = datetime.now().strftime("%Y-%m-%d")
        
        hotel = {
            "hotel_id": f"HT{hotel_idx:06d}",
            "name": f"{hotel_type} - {city} {neighbourhood}",
            "hotel_type": hotel_type,
            "city": city,  # Indian city
            "city_code": city_code,
            "country": "India",  # Mapped to India
            "original_country": country_code,  # Keep original for reference
            "neighbourhood": neighbourhood,  # Assignment requirement!
            "star_rating": star_rating,
            "price_per_night": round(adr, 2),
            "amenities": amenities,
            "room_type": row.get("reserved_room_type", "Standard"),
            "meal_plan": meal,
            "is_refundable": is_refundable,
            "pet_friendly": pet_friendly,
            "near_transit": near_transit,  # Assignment requirement!
            "parking_available": "parking" in amenities,
            "breakfast_included": "breakfast" in amenities,
            # Deal Score fields
            "avg_30d_price": round(avg_30d_price, 2),
            "discount_percent": discount_percent,
            "available_rooms": available_rooms,
            "has_promo": has_promo,
            "promo_end_date": promo_end_date,
            "deal_score": deal_score,
            "tags": tags,
            "rating": round(3.5 + (star_rating * 0.3), 1),
            "total_reviews": 50 + (hash_val * 5),
            "listing_date": listing_date
        }
        hotels.append(hotel)
        
        # SQLModel entity
        if SQLMODEL_AVAILABLE:
            sqlite_hotels.append(HotelDeal(
                hotel_id=f"HT{hotel_idx:06d}",
                name=f"{hotel_type} - {city} {neighbourhood}",
                hotel_type=hotel_type,
                city=city,
                city_code=city_code,
                country="India",
                neighbourhood=neighbourhood,
                price_per_night=round(adr, 2),
                avg_30d_price=round(avg_30d_price, 2),
                discount_percent=discount_percent,
                available_rooms=available_rooms,
                has_promo=has_promo,
                promo_end_date=promo_end_date,
                deal_score=deal_score,
                star_rating=star_rating,
                room_type=row.get("reserved_room_type", "Standard"),
                meal_plan=meal or None,
                amenities=json.dumps(amenities),
                tags=json.dumps(tags),
                is_refundable=is_refundable,
                pet_friendly=pet_friendly,
                parking_available="parking" in amenities,
                breakfast_included="breakfast" in amenities,
                near_transit=near_transit,
                rating=round(3.5 + (star_rating * 0.3), 1),
                total_reviews=50 + (hash_val * 5),
                listing_date=listing_date
            ))
        
        if len(hotels) >= limit:
            break
    
    print(f"Skipped {skipped_zero_price} hotels with zero/null price")
    
    # Insert to MongoDB
    collection = db["hotels"]
    collection.drop()
    if hotels:
        collection.insert_many(hotels)
        collection.create_index("hotel_id", unique=True)
        collection.create_index("city")
        collection.create_index("city_code")
        collection.create_index("price_per_night")
        collection.create_index("star_rating")
        collection.create_index("deal_score")
    
    # Insert to SQLite
    if SQLMODEL_AVAILABLE and sqlite_hotels:
        engine = get_engine()
        with Session(engine) as session:
            session.query(HotelDeal).delete()
            session.commit()
            for hotel in sqlite_hotels:
                session.add(hotel)
            session.commit()
        print(f"Imported {len(sqlite_hotels)} hotels to SQLite")
    
    print(f"Imported {len(hotels)} hotels to MongoDB")
    return len(hotels)


def generate_ssn():
    """Generate fake SSN"""
    return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"


def import_users(mysql_conn, filepath, limit=10000):
    """Import users from hotel bookings CSV"""
    print(f"\n=== Importing Users from {filepath} ===")
    
    if not mysql_conn:
        print("Skipping user import (No MySQL connection)")
        return 0
        
    df = pd.read_csv(filepath, nrows=limit)
    print(f"Loaded {len(df)} rows for user extraction")
    
    cursor = mysql_conn.cursor()
    count = 0
    seen_emails = set()
    
    sql = """
    INSERT IGNORE INTO users (
        user_id, first_name, last_name, 
        address_line1, city, state_code, zip_code,
        phone_number, email, password_hash, role,
        created_at_utc, updated_at_utc
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'user', NOW(), NOW())
    """
    
    for _, row in df.iterrows():
        name = row.get("name", "")
        email = row.get("email", "")
        phone = row.get("phone-number", "")
        
        if not name or not email or email in seen_emails:
            continue
            
        seen_emails.add(email)
        
        parts = name.split(" ")
        first_name = parts[0]
        last_name = " ".join(parts[1:]) if len(parts) > 1 else "Doe"
        
        user_id = generate_ssn()
        password_hash = "$2b$10$X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7.X7."
        
        values = (
            user_id, first_name, last_name,
            "123 Main St", "San Francisco", "CA", "94105",
            phone, email, password_hash
        )
        
        try:
            cursor.execute(sql, values)
            count += 1
        except Exception as e:
            print(f"Error inserting user {email}: {e}")
            
        if count >= limit:
            break
            
    mysql_conn.commit()
    cursor.close()
    
    print(f"Imported {count} users into MySQL")
    return count


def main():
    """Main import function"""
    print("=" * 60)
    print("Kayak Data Import Script")
    print("Importing to: MongoDB + SQLite (SQLModel)")
    print("=" * 60)
    
    # Initialize SQLite database
    if SQLMODEL_AVAILABLE:
        print("\nInitializing SQLite database...")
        init_db()
        print("SQLite database initialized")
    else:
        print("\nWarning: SQLModel not available, skipping SQLite import")
    
    # Connect to Databases
    mongo_db = connect_mongo()
    mysql_conn = connect_mysql()
    
    # File paths
    airports_file = os.path.join(DATA_DIR, "airports.csv")
    flights_file = os.path.join(DATA_DIR, "Clean_Dataset.csv")
    hotels_file = os.path.join(DATA_DIR, "hotel_booking.csv")
    
    # Import data
    total = 0
    
    if os.path.exists(airports_file):
        total += import_airports(mongo_db, airports_file)
    else:
        print(f"Warning: {airports_file} not found")
    
    if os.path.exists(flights_file):
        total += import_flights(mongo_db, flights_file, limit=10000)
    else:
        print(f"Warning: {flights_file} not found")
    
    if os.path.exists(hotels_file):
        total += import_hotels(mongo_db, hotels_file, limit=10000)
        total += import_users(mysql_conn, hotels_file, limit=10000)
    else:
        print(f"Warning: {hotels_file} not found")
    
    if mysql_conn:
        mysql_conn.close()
    
    print("\n" + "=" * 60)
    print(f"Import Complete! Total records processed: {total}")
    print("=" * 60)
    
    # Show sample data
    print("\n=== Sample Data (MongoDB) ===")
    
    print("\nAirports (first 3):")
    for doc in mongo_db["airports"].find().limit(3):
        print(f"  {doc.get('iata')}: {doc.get('name')} - {doc.get('city')}, {doc.get('country')}")
    
    print("\nFlights (first 5):")
    for doc in mongo_db["flights"].find().limit(5):
        print(f"  {doc.get('flight_id')}: {doc.get('origin')} -> {doc.get('destination')} | ${doc.get('price')} | Score: {doc.get('deal_score')}")
    
    print("\nHotels (first 5):")
    for doc in mongo_db["hotels"].find().limit(5):
        print(f"  {doc.get('hotel_id')}: {doc.get('name')} | {doc.get('city')} ({doc.get('city_code')}) | {doc.get('neighbourhood')} | ${doc.get('price_per_night')}/night | Score: {doc.get('deal_score')}")
    
    # Show SQLite stats
    if SQLMODEL_AVAILABLE:
        print("\n=== SQLite Database Stats ===")
        from models.database import get_db_stats
        stats = get_db_stats()
        for table, count in stats.items():
            print(f"  {table}: {count} records")


if __name__ == "__main__":
    main()
