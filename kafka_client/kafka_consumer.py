"""
Kafka Consumer Wrapper
Async wrapper for consuming messages from Kafka topics
"""

import asyncio
import logging
import json
from typing import List, Optional, AsyncIterator, Dict, Any

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from config import settings

logger = logging.getLogger(__name__)


class KafkaConsumerWrapper:
    """
    Async wrapper for Kafka consumer
    
    Provides async iteration over messages from subscribed topics
    """
    
    def __init__(
        self,
        topics: List[str],
        group_id: str = None,
        bootstrap_servers: str = None,
        auto_offset_reset: str = "latest",
        enable_auto_commit: bool = True
    ):
        """
        Initialize Kafka consumer
        
        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            bootstrap_servers: Kafka broker addresses
            auto_offset_reset: Where to start reading (earliest/latest)
            enable_auto_commit: Auto commit offsets
        """
        self.topics = topics
        self.group_id = group_id or settings.KAFKA_CONSUMER_GROUP
        self.bootstrap_servers = bootstrap_servers or settings.KAFKA_BOOTSTRAP_SERVERS
        self.auto_offset_reset = auto_offset_reset
        self.enable_auto_commit = enable_auto_commit
        
        self._consumer: Optional[KafkaConsumer] = None
        self._running = False
    
    async def start(self):
        """Start the Kafka consumer"""
        if self._consumer:
            return
        
        try:
            # Create consumer in thread pool (kafka-python is synchronous)
            loop = asyncio.get_event_loop()
            self._consumer = await loop.run_in_executor(
                None,
                self._create_consumer
            )
            
            self._running = True
            logger.info(f"Kafka consumer started, subscribed to: {self.topics}")
            
        except KafkaError as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise
    
    def _create_consumer(self) -> KafkaConsumer:
        """Create the underlying KafkaConsumer"""
        return KafkaConsumer(
            *self.topics,
            bootstrap_servers=self.bootstrap_servers.split(","),
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=self.enable_auto_commit,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else None,
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            session_timeout_ms=30000,
            heartbeat_interval_ms=3000,
            max_poll_interval_ms=300000,
            consumer_timeout_ms=1000  # 1 second timeout for polling
        )
    
    async def stop(self):
        """Stop the Kafka consumer"""
        self._running = False
        
        if self._consumer:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._consumer.close)
                logger.info("Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka consumer: {e}")
            finally:
                self._consumer = None
    
    def __aiter__(self) -> AsyncIterator[Dict]:
        """Allow async iteration over messages"""
        return self
    
    async def __anext__(self) -> Dict:
        """Get next message asynchronously"""
        if not self._running or not self._consumer:
            raise StopAsyncIteration
        
        loop = asyncio.get_event_loop()
        
        while self._running:
            try:
                # Poll for messages in thread pool
                message = await loop.run_in_executor(
                    None,
                    self._poll_message
                )
                
                if message is not None:
                    return message
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)
                
            except StopIteration:
                raise StopAsyncIteration
            except Exception as e:
                logger.error(f"Error polling Kafka message: {e}")
                await asyncio.sleep(1)  # Back off on error
        
        raise StopAsyncIteration
    
    def _poll_message(self) -> Optional[Dict]:
        """
        Poll for a single message (synchronous)
        
        Returns:
            Message value dict or None
        """
        if not self._consumer:
            return None
        
        try:
            # Poll with timeout
            records = self._consumer.poll(timeout_ms=1000, max_records=1)
            
            for topic_partition, messages in records.items():
                for message in messages:
                    logger.debug(
                        f"Received message from {topic_partition.topic} "
                        f"partition {topic_partition.partition} "
                        f"offset {message.offset}"
                    )
                    
                    # Return the message value (already deserialized)
                    value = message.value
                    
                    # Add metadata
                    if isinstance(value, dict):
                        value["_kafka_topic"] = topic_partition.topic
                        value["_kafka_partition"] = topic_partition.partition
                        value["_kafka_offset"] = message.offset
                        value["_kafka_key"] = message.key
                        value["_kafka_timestamp"] = message.timestamp
                    
                    return value
            
            return None
            
        except Exception as e:
            logger.error(f"Error in poll_message: {e}")
            return None
    
    async def consume_batch(self, max_records: int = 100, timeout_ms: int = 5000) -> List[Dict]:
        """
        Consume a batch of messages
        
        Args:
            max_records: Maximum records to fetch
            timeout_ms: Timeout in milliseconds
        
        Returns:
            List of message dicts
        """
        if not self._consumer:
            return []
        
        loop = asyncio.get_event_loop()
        
        def _poll_batch():
            messages = []
            records = self._consumer.poll(timeout_ms=timeout_ms, max_records=max_records)
            
            for topic_partition, msgs in records.items():
                for msg in msgs:
                    value = msg.value
                    if isinstance(value, dict):
                        value["_kafka_topic"] = topic_partition.topic
                        value["_kafka_key"] = msg.key
                    messages.append(value)
            
            return messages
        
        return await loop.run_in_executor(None, _poll_batch)
    
    async def commit(self):
        """Manually commit offsets"""
        if self._consumer and not self.enable_auto_commit:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._consumer.commit)
    
    async def seek_to_beginning(self):
        """Seek to beginning of all partitions"""
        if self._consumer:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._consumer.seek_to_beginning()
            )
    
    async def seek_to_end(self):
        """Seek to end of all partitions"""
        if self._consumer:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._consumer.seek_to_end()
            )
    
    @property
    def is_running(self) -> bool:
        """Check if consumer is running"""
        return self._running and self._consumer is not None
