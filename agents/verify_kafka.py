import json
import os
import asyncio
from kafka import KafkaConsumer

TOPIC = "deals.scored"
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")

async def verify_topic(topic_name):
    print(f"🕵️‍♀️ Verifying data in topic '{topic_name}'...")
    try:
        consumer = KafkaConsumer(
            topic_name,
            bootstrap_servers=BOOTSTRAP_SERVERS.split(','),
            auto_offset_reset='earliest',
            enable_auto_commit=False,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            consumer_timeout_ms=3000
        )
        
        count = 0
        found_car = False
        for message in consumer:
            count += 1
            data = message.value
            
            # Handle wrapped format for deals.scored
            if topic_name == "deals.scored" and "attrs" in data:
                payload = data["attrs"]
                l_type = payload.get('listing_type', 'unknown')
                d_id = payload.get('deal_id', 'unknown')
                score = data.get('score', 'N/A')
            else:
                l_type = data.get('listing_type', 'unknown')
                d_id = data.get('deal_id', 'unknown')
                score = data.get('deal_score', 'N/A')
            
            if l_type == 'car':
                print(f"   ✅ Found CAR in '{topic_name}': ID={d_id} | Score={score}")
                found_car = True
                break
            # elif count < 20:
            #    print(f"   ℹ️  Skipping {l_type} (ID={d_id})")
        
        if not found_car:
            print(f"   ❌ No CAR found in '{topic_name}' (checked {count} messages)")
        
        if count == 0:
            print(f"   ❌ No messages found in '{topic_name}'")
            
    except Exception as e:
        print(f"   ❌ Error checking '{topic_name}': {e}")

async def verify():
    print(f"🚀 Starting Pipeline Verification (Bootstrap: {BOOTSTRAP_SERVERS})")
    await verify_topic("raw_supplier_feeds")
    await verify_topic("deals.normalized")
    await verify_topic("deals.scored")
    print("🏁 Verification Complete")

if __name__ == "__main__":
    asyncio.run(verify())
