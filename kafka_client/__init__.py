"""
Kafka Integration Module
Provides abstraction layer for Kafka messaging
"""

from .interface import KafkaInterface
from .message_schemas import (
    ListingEvent,
    DealScoredEvent,
    DealTaggedEvent,
    DealEvent
)
from .memory_kafka import MemoryKafka

__all__ = [
    "KafkaInterface",
    "ListingEvent",
    "DealScoredEvent",
    "DealTaggedEvent",
    "DealEvent",
    "MemoryKafka"
]
