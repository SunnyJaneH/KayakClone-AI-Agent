import csv
import json
import time
import os
import asyncio
from datetime import datetime
from typing import Dict, Any

# Try to import Kafka producer from the project
try:
    from kafka_client.kafka_producer import KafkaProducerWrapper
    KAFKA_AVAILABLE = True
except ImportError:
    # Fallback for running as standalone script
    try:
        from kafka import KafkaProducer
        KAFKA_AVAILABLE = True
        STANDALONE = True
    except ImportError:
        KAFKA_AVAILABLE = False
        print("❌ Kafka not available. Please install kafka-python.")

# Configuration
FLIGHTS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data/Clean_Dataset.csv")
HOTELS_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data/hotel_booking.csv")
TOPIC = "raw_supplier_feeds"
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

async def ingest_flights(producer):
    """Read flights CSV and publish to Kafka"""
    if not os.path.exists(FLIGHTS_CSV):
        print(f"⚠️ Flights CSV not found at {FLIGHTS_CSV}")
        return

    print(f"✈️  Ingesting Flights from {FLIGHTS_CSV}...")
    count = 0
    
    # Check if we are using the wrapper (which has 'send_scored_deal') or raw client
    is_wrapper = hasattr(producer, 'send_scored_deal')
    
    with open(FLIGHTS_CSV, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Derive amenities
            amenities = []
            if row.get("class") == "Business":
                amenities.append("Business Class")
            if row.get("stops") == "zero":
                amenities.append("Direct Flight")
                
            # Map CSV fields to our schema
            message = {
                "source": "kaggle_flights",
                "listing_type": "flight",
                "data": {
                    "flight_id": row.get("flight"),
                    "airline": row.get("airline"),
                    "origin": row.get("source_city"),
                    "destination": row.get("destination_city"),
                    "departure_time": row.get("departure_time"),
                    "arrival_time": row.get("arrival_time"),
                    "duration": row.get("duration"),
                    "stops": row.get("stops"),
                    "price": row.get("price"),
                    "class": row.get("class"),
                    "days_left": row.get("days_left"),
                    "amenities": amenities
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to Kafka
            if is_wrapper:
                await producer.send(TOPIC, message)
            else:
                producer.send(TOPIC, value=message)
            
            count += 1
            if count % 100 == 0:
                print(f"   Sent {count} flights...", end='\r')
                await asyncio.sleep(0.01)
            
            if count >= 1: # Limit for demo (User requested 1)
                break
    
    print(f"\n✅ Sent {count} flight records.")

async def ingest_hotels(producer):
    """Read hotels CSV and publish to Kafka"""
    if not os.path.exists(HOTELS_CSV):
        print(f"⚠️ Hotels CSV not found at {HOTELS_CSV}")
        return

    print(f"🏨 Ingesting Hotels from {HOTELS_CSV}...")
    count = 0
    
    # Check if we are using the wrapper (which has 'send_scored_deal') or raw client
    is_wrapper = hasattr(producer, 'send_scored_deal')
    
    with open(HOTELS_CSV, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Create a unique ID since CSV doesn't have one
            hotel_id = f"hotel_{row.get('arrival_date_year')}_{count}"
            
            # Derive amenities
            amenities = []
            if int(row.get("required_car_parking_spaces", 0)) > 0:
                amenities.append("Parking")
            if row.get("meal") in ["BB", "HB", "FB"]:
                amenities.append("Breakfast")
            if row.get("hotel") == "Resort Hotel":
                amenities.append("Resort")
                amenities.append("Pool") # Assume resorts have pools
            
            message = {
                "source": "kaggle_hotels",
                "listing_type": "hotel",
                "data": {
                    "hotel_id": hotel_id,
                    "hotel_name": f"{row.get('hotel')} - {row.get('country')}", # Make name more descriptive
                    "hotel_type": row.get("hotel"), # Resort or City
                    "location": row.get("country"), # Map country to location for _normalize
                    "arrival_date": f"{row.get('arrival_date_year')}-{row.get('arrival_date_month')}-{row.get('arrival_date_day_of_month')}",
                    "stays_nights": int(row.get("stays_in_weekend_nights", 0)) + int(row.get("stays_in_week_nights", 0)),
                    "adults": row.get("adults"),
                    "children": row.get("children"),
                    "meal": row.get("meal"),
                    "price": row.get("adr"), # Average Daily Rate
                    "is_canceled": row.get("is_canceled"),
                    "customer_type": row.get("customer_type"),
                    "amenities": amenities
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Send to Kafka
            if is_wrapper:
                await producer.send(TOPIC, message)
            else:
                producer.send(TOPIC, value=message)
            
            count += 1
            if count % 100 == 0:
                print(f"   Sent {count} hotels...", end='\r')
                await asyncio.sleep(0.01)
                
            if count >= 1: # Limit for demo (User requested 1)
                break
    
    print(f"\n✅ Sent {count} hotel records.")

async def ingest_cars(producer):
    """Ingest mock car data (since CSV creation is blocked)"""
    print(f"🚗 Ingesting Cars (Mock Data)...")
    
    cars_data = [
        {"car_id": "car_001", "brand": "Toyota", "model": "Camry", "type": "Sedan", "location": "San Francisco", "price_per_day": 55, "seats": 5, "transmission": "Automatic"},
        {"car_id": "car_002", "brand": "Tesla", "model": "Model 3", "type": "Electric", "location": "New York", "price_per_day": 95, "seats": 5, "transmission": "Automatic"},
        {"car_id": "car_003", "brand": "Ford", "model": "Mustang", "type": "Convertible", "location": "Los Angeles", "price_per_day": 120, "seats": 4, "transmission": "Automatic"},
        {"car_id": "car_004", "brand": "Honda", "model": "CR-V", "type": "SUV", "location": "Miami", "price_per_day": 75, "seats": 5, "transmission": "Automatic"},
        {"car_id": "car_005", "brand": "Chevrolet", "model": "Tahoe", "type": "SUV", "location": "Chicago", "price_per_day": 110, "seats": 7, "transmission": "Automatic"}
    ]
    
    count = 0
    is_wrapper = hasattr(producer, 'send_scored_deal')
    
    for row in cars_data:
        # Derive amenities
        amenities = [row["transmission"], row["type"]]
        if row["seats"] >= 7:
            amenities.append("Family Friendly")
            
        message = {
            "source": "mock_cars",
            "listing_type": "car",
            "data": {
                "car_id": row["car_id"],
                "name": f"{row['brand']} {row['model']}",
                "type": row["type"],
                "location": row["location"],
                "price": row["price_per_day"],
                "seats": row["seats"],
                "transmission": row["transmission"],
                "amenities": amenities
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to Kafka
        if is_wrapper:
            await producer.send(TOPIC, message)
        else:
            producer.send(TOPIC, value=message)
        
        count += 1
        if count >= 1: # Limit for demo
            break
            
    print(f"✅ Sent {count} car records.")

async def main():
    print(f"🚀 Starting Real Data Ingestion to Kafka ({BOOTSTRAP_SERVERS})...")
    
    producer = None
    try:
        if 'KafkaProducerWrapper' in globals():
            producer = KafkaProducerWrapper(bootstrap_servers=BOOTSTRAP_SERVERS, client_id="csv-ingestor")
            await producer.start()
        else:
            from kafka import KafkaProducer
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP_SERVERS.split(','),
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        
        await ingest_flights(producer)
        await ingest_hotels(producer)
        await ingest_cars(producer)
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if producer and hasattr(producer, 'stop'):
            await producer.stop()
        elif producer:
            producer.close()

if __name__ == "__main__":
    asyncio.run(main())
