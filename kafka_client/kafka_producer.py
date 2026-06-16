"""
Kafka Producer Wrapper
Async wrapper for producing messages to Kafka topics
"""

import asyncio
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime

from kafka import KafkaProducer
from kafka.errors import KafkaError

from config import settings

logger = logging.getLogger(__name__)


class KafkaProducerWrapper:
    """
    Async wrapper for Kafka producer
    
    Provides async methods for sending messages to Kafka topics
    Message format aligned with middleware kafka.js
    """
    
    def __init__(
        self,
        bootstrap_servers: str = None,
        client_id: str = "ai-deals-agent",
        acks: str = "all",
        retries: int = 3
    ):
        """
        Initialize Kafka producer
        
        Args:
            bootstrap_servers: Kafka broker addresses
            client_id: Client identifier
            acks: Acknowledgment level (0, 1, all)
            retries: Number of retries on failure
        """
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.client_id = client_id
        self.acks = acks
        self.retries = retries
        
        self._producer: Optional[KafkaProducer] = None
    
    async def start(self):
        """Start the Kafka producer"""
        if self._producer:
            return
        
        try:
            loop = asyncio.get_event_loop()
            self._producer = await loop.run_in_executor(
                None,
                self._create_producer
            )
            
            logger.info(f"Kafka producer started, connected to: {self.bootstrap_servers}")
            
        except KafkaError as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise
    
    def _create_producer(self) -> KafkaProducer:
        """Create the underlying KafkaProducer"""
        return KafkaProducer(
            bootstrap_servers=self.bootstrap_servers.split(","),
            client_id=self.client_id,
            acks=self.acks,
            retries=self.retries,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            max_block_ms=10000,
            request_timeout_ms=30000
        )
    
    async def stop(self):
        """Stop the Kafka producer"""
        if self._producer:
            try:
                loop = asyncio.get_event_loop()
                # Flush pending messages
                await loop.run_in_executor(None, self._producer.flush)
                await loop.run_in_executor(None, self._producer.close)
                logger.info("Kafka producer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")
            finally:
                self._producer = None
    
    async def send(
        self,
        topic: str,
        value: Dict,
        key: Optional[str] = None,
        headers: Optional[List[tuple]] = None
    ) -> bool:
        """
        Send a message to a Kafka topic
        
        Args:
            topic: Target topic name
            value: Message value (dict)
            key: Optional message key for partitioning
            headers: Optional message headers
        
        Returns:
            True if successful, False otherwise
        """
        if not self._producer:
            logger.error("Kafka producer not started")
            return False
        
        try:
            # Add timestamp if not present
            if isinstance(value, dict) and "timestamp" not in value:
                value["timestamp"] = datetime.now().isoformat()
            
            loop = asyncio.get_event_loop()
            
            def _send():
                future = self._producer.send(
                    topic,
                    value=value,
                    key=key,
                    headers=headers
                )
                # Wait for send to complete
                record_metadata = future.get(timeout=10)
                return record_metadata
            
            metadata = await loop.run_in_executor(None, _send)
            
            logger.debug(
                f"Sent message to {topic} "
                f"partition {metadata.partition} "
                f"offset {metadata.offset}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to {topic}: {e}")
            return False
    
    async def send_scored_deal(
        self,
        key: str,
        score: int,
        reason: str,
        attrs: Dict
    ) -> bool:
        """
        Send a scored deal to deals.scored topic
        
        Message format (aligned with middleware):
        {
            "key": "flight_123",
            "score": 78,
            "reason": "Good price for nonstop flight",
            "ts": "2025-11-08T10:31:00Z",
            "attrs": { ... }
        }
        
        Args:
            key: Deal identifier
            score: Deal score (0-100)
            reason: Scoring reason/explanation
            attrs: Original deal attributes
        
        Returns:
            True if successful
        """
        message = {
            "key": key,
            "score": score,
            "reason": reason,
            "ts": datetime.now().isoformat(),
            "attrs": attrs
        }
        
        return await self.send(
            topic=settings.KAFKA_DEALS_SCORED_TOPIC,
            value=message,
            key=key
        )
    
    async def send_tagged_deal(
        self,
        key: str,
        tags: List[str],
        attrs: Dict
    ) -> bool:
        """
        Send a tagged deal to deals.tagged topic
        
        Message format (aligned with middleware):
        {
            "key": "flight_123",
            "tags": ["excellent_deal", "nonstop"],
            "ts": "2025-11-08T10:31:00Z",
            "attrs": { ... }
        }
        
        Args:
            key: Deal identifier
            tags: List of tags
            attrs: Original deal attributes
        
        Returns:
            True if successful
        """
        message = {
            "key": key,
            "tags": tags,
            "ts": datetime.now().isoformat(),
            "attrs": attrs
        }
        
        return await self.send(
            topic=settings.KAFKA_DEALS_TAGGED_TOPIC,
            value=message,
            key=key
        )
    
    async def send_deal_event(
        self,
        key: str,
        event_type: str,
        payload: Dict,
        score: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Send a deal event to deal.events topic
        
        Event types (aligned with MongoDB init.js):
        - deal_detected
        - deal_scored
        - deal_tagged
        - price_drop
        - inventory_low
        - watch_alert
        
        Message format:
        {
            "key": "flight_123",
            "event_type": "deal_scored",
            "ts": "2025-11-08T10:31:00Z",
            "score": 78,
            "tags": ["excellent_deal"],
            "payload": { ... }
        }
        
        Args:
            key: Deal/entity identifier
            event_type: Type of event
            payload: Event payload data
            score: Optional score
            tags: Optional tags
        
        Returns:
            True if successful
        """
        message = {
            "key": key,
            "event_type": event_type,
            "ts": datetime.now().isoformat(),
            "payload": payload
        }
        
        if score is not None:
            message["score"] = score
        
        if tags:
            message["tags"] = tags
        
        return await self.send(
            topic=settings.KAFKA_DEAL_EVENTS_TOPIC,
            value=message,
            key=key
        )
    
    async def send_batch(
        self,
        topic: str,
        messages: List[Dict],
        key_field: str = "key"
    ) -> int:
        """
        Send a batch of messages to a topic
        
        Args:
            topic: Target topic
            messages: List of message dicts
            key_field: Field to use as message key
        
        Returns:
            Number of successfully sent messages
        """
        if not self._producer:
            logger.error("Kafka producer not started")
            return 0
        
        success_count = 0
        
        for message in messages:
            key = message.get(key_field) if key_field else None
            
            if await self.send(topic, message, key):
                success_count += 1
        
        # Flush to ensure all messages are sent
        await self.flush()
        
        logger.info(f"Sent batch of {success_count}/{len(messages)} messages to {topic}")
        
        return success_count
    
    async def flush(self, timeout: float = 10.0):
        """
        Flush all pending messages
        
        Args:
            timeout: Timeout in seconds
        """
        if self._producer:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._producer.flush(timeout=timeout)
            )
    
    @property
    def is_connected(self) -> bool:
        """Check if producer is connected"""
        return self._producer is not None
