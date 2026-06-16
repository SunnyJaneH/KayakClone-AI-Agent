"""
Kafka Interface - Abstract Base Class
Defines the contract for Kafka interactions
Week 1: Use MemoryKafka implementation
Week 2: Create RealKafka implementation
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from .message_schemas import (
    ListingEvent,
    DealScoredEvent,
    DealTaggedEvent,
    DealEvent
)


class KafkaInterface(ABC):
    """
    Abstract interface for Kafka operations
    
    This abstraction allows us to:
    - Week 1: Use in-memory queue (MemoryKafka)
    - Week 2: Switch to real Kafka (RealKafka)
    - Without changing any other code!
    """
    
    # ============================================
    # Consumer Methods
    # ============================================
    
    @abstractmethod
    def consume_listings(self) -> List[ListingEvent]:
        """
        Consume listing events from Kafka topic: listing.events
        
        Returns:
            List[ListingEvent]: List of listing events
        """
        pass
    
    @abstractmethod
    def consume_deal_events(self) -> List[DealEvent]:
        """
        Consume final deal events from Kafka topic: deal.events
        
        Returns:
            List[DealEvent]: List of deal events
        """
        pass
    
    # ============================================
    # Producer Methods
    # ============================================
    
    @abstractmethod
    def publish_deal_scored(self, event: DealScoredEvent) -> None:
        """
        Publish deal score event to Kafka topic: deals.scored
        
        Args:
            event: Deal scored event with score and metadata
        """
        pass
    
    @abstractmethod
    def publish_deal_tagged(self, event: DealTaggedEvent) -> None:
        """
        Publish deal tagged event to Kafka topic: deals.tagged
        
        Args:
            event: Deal tagged event with tags
        """
        pass
    
    @abstractmethod
    def publish_deal_event(self, event: DealEvent) -> None:
        """
        Publish final deal event to Kafka topic: deal.events
        
        Args:
            event: Final deal event for frontend consumption
        """
        pass
    
    # ============================================
    # Utility Methods
    # ============================================
    
    @abstractmethod
    def close(self) -> None:
        """
        Close Kafka connections and cleanup resources
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if Kafka connection is healthy
        
        Returns:
            bool: True if healthy, False otherwise
        """
        pass
