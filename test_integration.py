"""
Integration Test Script
Tests connectivity to all services: MySQL, Redis, Kafka, MongoDB
Run this after starting docker-compose to verify everything works
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add ai directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")

def print_result(name: str, success: bool, message: str = ""):
    status = "[PASS]" if success else "[FAIL]"
    color = "\033[92m" if success else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status}{reset} {name}")
    if message:
        print(f"       {message}")

async def test_mysql():
    """Test MySQL connections to kayak_users and kayak_bookings"""
    print_header("Testing MySQL Connection")
    
    try:
        import mysql.connector
        from dotenv import load_dotenv
        load_dotenv()
        
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = int(os.getenv("DB_PORT", "3306"))
        DB_USER = os.getenv("DB_USER", "root")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
        DB_NAME_USERS = os.getenv("DB_NAME_USERS", "kayak_users")
        DB_NAME_BOOKINGS = os.getenv("DB_NAME_BOOKINGS", "kayak_bookings")
        
        # Test kayak_users database
        try:
            conn = mysql.connector.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME_USERS
            )
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT COUNT(*) as count FROM users")
            result = cursor.fetchone()
            print_result(
                f"MySQL {DB_NAME_USERS}.users",
                True,
                f"Found {result['count']} users"
            )
            
            cursor.execute("DESCRIBE users")
            columns = [row['Field'] for row in cursor.fetchall()]
            has_camel_case = 'firstName' in columns or 'userId' in columns
            print_result(
                "Table uses camelCase",
                has_camel_case,
                f"Columns: {', '.join(columns[:5])}..."
            )
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print_result(f"MySQL {DB_NAME_USERS}", False, str(e))
            return False
        
        # Test kayak_bookings database
        try:
            conn = mysql.connector.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME_BOOKINGS
            )
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT COUNT(*) as count FROM bookings")
            result = cursor.fetchone()
            print_result(
                f"MySQL {DB_NAME_BOOKINGS}.bookings",
                True,
                f"Found {result['count']} bookings"
            )
            
            cursor.execute("SELECT COUNT(*) as count FROM inventory")
            result = cursor.fetchone()
            print_result(
                f"MySQL {DB_NAME_BOOKINGS}.inventory",
                True,
                f"Found {result['count']} inventory items"
            )
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print_result(f"MySQL {DB_NAME_BOOKINGS}", False, str(e))
            return False
        
        return True
        
    except ImportError:
        print_result("MySQL", False, "mysql-connector-python not installed")
        return False
    except Exception as e:
        print_result("MySQL", False, str(e))
        return False

async def test_redis():
    """Test Redis connection"""
    print_header("Testing Redis Connection")
    
    try:
        import redis
        from dotenv import load_dotenv
        load_dotenv()
        
        REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
        REDIS_DB = int(os.getenv("REDIS_DB", "0"))
        
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        
        ping_result = r.ping()
        print_result("Redis PING", ping_result, "PONG received")
        
        test_key = "ai_test_key"
        test_value = f"test_value_{datetime.now().isoformat()}"
        r.set(test_key, test_value, ex=60)
        retrieved = r.get(test_key)
        
        set_get_ok = retrieved.decode() == test_value if retrieved else False
        print_result("Redis SET/GET", set_get_ok)
        
        r.delete(test_key)
        
        return True
        
    except ImportError:
        print_result("Redis", False, "redis package not installed")
        return False
    except Exception as e:
        print_result("Redis", False, str(e))
        return False

async def test_kafka():
    """Test Kafka connection"""
    print_header("Testing Kafka Connection")
    
    try:
        # Import kafka-python directly (avoid local kafka folder conflict)
        import importlib
        kafka_module = importlib.import_module('kafka.producer')
        KafkaProducer = kafka_module.KafkaProducer
        
        kafka_consumer_module = importlib.import_module('kafka.consumer')
        KafkaConsumer = kafka_consumer_module.KafkaConsumer
        
        from dotenv import load_dotenv
        load_dotenv()
        
        KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        bootstrap_servers = KAFKA_BOOTSTRAP_SERVERS.split(",")
        
        # Test producer connection
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                request_timeout_ms=5000,
                api_version_auto_timeout_ms=5000
            )
            print_result("Kafka Producer", True, f"Connected to {KAFKA_BOOTSTRAP_SERVERS}")
            producer.close()
        except Exception as e:
            print_result("Kafka Producer", False, str(e))
            return False
        
        # Test consumer connection
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=bootstrap_servers,
                consumer_timeout_ms=1000,
                api_version_auto_timeout_ms=5000
            )
            topics = consumer.topics()
            print_result(
                "Kafka Consumer",
                True,
                f"Found {len(topics)} topics: {', '.join(list(topics)[:5]) if topics else 'none yet'}"
            )
            consumer.close()
        except Exception as e:
            print_result("Kafka Consumer", False, str(e))
            return False
        
        # Check required topics
        required_topics = [
            os.getenv("KAFKA_DEALS_NORMALIZED_TOPIC", "deals.normalized"),
            os.getenv("KAFKA_DEALS_SCORED_TOPIC", "deals.scored"),
            os.getenv("KAFKA_DEALS_TAGGED_TOPIC", "deals.tagged"),
            os.getenv("KAFKA_DEAL_EVENTS_TOPIC", "deal.events")
        ]
        
        consumer = KafkaConsumer(bootstrap_servers=bootstrap_servers)
        existing_topics = consumer.topics()
        consumer.close()
        
        for topic in required_topics:
            exists = topic in existing_topics
            status = "exists" if exists else "will be auto-created"
            print_result(f"Topic: {topic}", True, status)
        
        return True
        
    except ImportError as e:
        print_result("Kafka", False, f"kafka-python not installed: {e}")
        print("       Run: pip install kafka-python")
        return False
    except Exception as e:
        print_result("Kafka", False, str(e))
        return False

async def test_mongodb():
    """Test MongoDB connection"""
    print_header("Testing MongoDB Connection")
    
    try:
        from pymongo import MongoClient
        from pymongo.errors import ServerSelectionTimeoutError
        from dotenv import load_dotenv
        load_dotenv()
        
        MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        MONGO_DB = os.getenv("MONGO_DB", "kayak_doc")
        
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        
        client.admin.command('ping')
        print_result("MongoDB PING", True)
        
        db = client[MONGO_DB]
        collections = db.list_collection_names()
        print_result(
            f"MongoDB {MONGO_DB}",
            True,
            f"Collections: {', '.join(collections) if collections else 'none'}"
        )
        
        if 'deal_events' in collections:
            count = db.deal_events.count_documents({})
            print_result("deal_events collection", True, f"{count} documents")
        else:
            db.create_collection('deal_events')
            print_result("deal_events collection", True, "Created (was missing)")
        
        client.close()
        return True
        
    except ImportError:
        print_result("MongoDB", False, "pymongo not installed")
        return False
    except Exception as e:
        print_result("MongoDB", False, str(e))
        return False

async def test_data_interface():
    """Test DataInterface queries"""
    print_header("Testing DataInterface")
    
    try:
        import mysql.connector
        from dotenv import load_dotenv
        load_dotenv()
        
        DB_HOST = os.getenv("DB_HOST", "localhost")
        DB_PORT = int(os.getenv("DB_PORT", "3306"))
        DB_USER = os.getenv("DB_USER", "root")
        DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
        DB_NAME_USERS = os.getenv("DB_NAME_USERS", "kayak_users")
        DB_NAME_BOOKINGS = os.getenv("DB_NAME_BOOKINGS", "kayak_bookings")
        
        # Test 1: Get user by ID
        conn = mysql.connector.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME_USERS
        )
        cursor = conn.cursor(dictionary=True)
        
        test_user_id = "123-45-6789"
        cursor.execute("""
            SELECT userId, firstName, lastName, email, role
            FROM users WHERE userId = %s
        """, (test_user_id,))
        user = cursor.fetchone()
        
        print_result(
            f"get_user_by_id('{test_user_id}')",
            user is not None,
            f"Found: {user['firstName']} {user['lastName']}" if user else "Not found"
        )
        
        cursor.close()
        conn.close()
        
        # Test 2: Get booking history
        conn = mysql.connector.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, database=DB_NAME_BOOKINGS
        )
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT COUNT(*) as count FROM bookings WHERE userId = %s
        """, (test_user_id,))
        result = cursor.fetchone()
        print_result("get_booking_history()", True, f"Found {result['count']} bookings for user")
        
        # Test 3: Get inventory
        cursor.execute("SELECT COUNT(*) as count FROM inventory WHERE listingType = 'hotel'")
        result = cursor.fetchone()
        print_result("get_inventory(listing_type='hotel')", True, f"Found {result['count']} hotel inventory records")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print_result("DataInterface", False, str(e))
        return False

async def test_api_imports():
    """Test API imports"""
    print_header("Testing API Imports")
    
    try:
        from dotenv import load_dotenv
        print_result("dotenv", True)
        
        import fastapi
        print_result("fastapi", True)
        
        import pydantic
        print_result("pydantic", True)
        
        return True
        
    except ImportError as e:
        print_result("API Imports", False, str(e))
        return False

async def main():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("  AI SERVICE INTEGRATION TESTS")
    print("="*60)
    print(f"  Time: {datetime.now().isoformat()}")
    print("="*60)
    
    results = {}
    
    results["MySQL"] = await test_mysql()
    results["Redis"] = await test_redis()
    results["Kafka"] = await test_kafka()
    results["MongoDB"] = await test_mongodb()
    results["DataInterface"] = await test_data_interface()
    results["API Imports"] = await test_api_imports()
    
    print_header("TEST SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for name, success in results.items():
        print_result(name, success)
    
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} passed")
    print(f"{'='*60}\n")
    
    if passed == total:
        print("\033[92m  All tests passed! Ready for integration.\033[0m\n")
        return 0
    else:
        print("\033[91m  Some tests failed. Check the errors above.\033[0m\n")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
