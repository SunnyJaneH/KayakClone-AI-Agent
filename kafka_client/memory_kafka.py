"""
Memory-based Kafka Implementation
Week 1-2: Use this for independent development
Week 3: Switch to RealKafka when teammates provide Kafka server
"""

import json
from pathlib import Path
from queue import Queue
from typing import List
from loguru import logger

from .interface import KafkaInterface
from .message_schemas import (
    ListingEvent,
    DealScoredEvent,
    DealTaggedEvent,
    DealEvent
)


class MemoryKafka(KafkaInterface):
    """
    In-memory implementation of Kafka for Week 1-2 development
    
    Features:
    - Loads test data from JSON files
    - Uses Python Queue to simulate Kafka topics
    - Allows independent development without real Kafka
    - Easy to switch to RealKafka later (just change config)
    
    Usage:
        kafka = MemoryKafka(data_dir="data/mock")
        listings = kafka.consume_listings()
    """
    
    def __init__(self, data_dir: str = "data/mock"):
        """
        Initialize MemoryKafka with test data
        
        Args:
            data_dir: Directory containing mock_data.json
        """
        self.data_dir = Path(data_dir)
        
        # Create in-memory queues for each topic
        self.listing_queue = Queue()
        self.deal_scored_queue = Queue()
        self.deal_tagged_queue = Queue()
        self.deal_events_queue = Queue()
        
        # Load test data
        self._load_test_data()
        
        logger.info(f"MemoryKafka initialized with data from {self.data_dir}")
    
    def _load_test_data(self):
        """
        Load test data from JSON file into listing queue
        """
        mock_data_file = self.data_dir / "mock_data.json"
        
        if not mock_data_file.exists():
            logger.warning(f"Mock data file not found: {mock_data_file}")
            logger.warning("Creating empty queues. You can add data dynamically.")
            return
        
        try:
            with open(mock_data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load listings into queue
            listings = data.get("listings", [])
            for listing_data in listings:
                listing = ListingEvent(**listing_data)
                self.listing_queue.put(listing)
            
            logger.info(f"Loaded {len(listings)} listings into memory queue")
            
        except Exception as e:
            logger.error(f"Error loading mock data: {e}")
            raise
    
    # ============================================
    # Consumer Methods
    # ============================================
    
    def consume_listings(self) -> List[ListingEvent]:
        """
        Consume all available listing events from queue
        
        Returns:
            List[ListingEvent]: List of listing events (may be empty)
        """
        results = []
        while not self.listing_queue.empty():
            listing = self.listing_queue.get()
            results.append(listing)
            logger.debug(f"Consumed listing: {listing.listingId}")
        
        if results:
            logger.info(f"Consumed {len(results)} listing events")
        
        return results
    
    def consume_deal_events(self) -> List[DealEvent]:
        """
        Consume all available deal events from queue
        
        Returns:
            List[DealEvent]: List of deal events
        """
        results = []
        while not self.deal_events_queue.empty():
            event = self.deal_events_queue.get()
            results.append(event)
        
        if results:
            logger.info(f"Consumed {len(results)} deal events")
        
        return results
    
    # ============================================
    # Producer Methods
    # ============================================
    
    def publish_deal_scored(self, event: DealScoredEvent) -> None:
        """
        Publish deal scored event to queue
        
        Args:
            event: Deal scored event
        """
        self.deal_scored_queue.put(event)
        logger.info(f"Published deal_scored: {event.listingId} (score: {event.dealScore})")
    
    def publish_deal_tagged(self, event: DealTaggedEvent) -> None:
        """
        Publish deal tagged event to queue
        
        Args:
            event: Deal tagged event
        """
        self.deal_tagged_queue.put(event)
        logger.info(f"Published deal_tagged: {event.listingId} (tags: {event.tags})")
    
    def publish_deal_event(self, event: DealEvent) -> None:
        """
        Publish final deal event to queue
        
        Args:
            event: Final deal event
        """
        self.deal_events_queue.put(event)
        logger.info(f"Published deal_event: {event.listingId} (isDeal: {event.isDeal})")
    
    # ============================================
    # Utility Methods
    # ============================================
    
    def close(self) -> None:
        """
        Close connections (no-op for memory implementation)
        """
        logger.info("MemoryKafka closed (no actual connections to close)")
    
    def health_check(self) -> bool:
        """
        Health check (always healthy for memory implementation)
        
        Returns:
            bool: Always True
        """
        return True
    
    # ============================================
    # Debug/Testing Methods
    # ============================================
    
    def reset_queues(self):
        """
        Clear all queues and reload test data
        Useful for testing
        """
        self.listing_queue = Queue()
        self.deal_scored_queue = Queue()
        self.deal_tagged_queue = Queue()
        self.deal_events_queue = Queue()
        self._load_test_data()
        logger.info("All queues reset and data reloaded")
    
    def add_listing(self, listing: ListingEvent):
        """
        Manually add a listing to the queue
        Useful for testing specific scenarios
        
        Args:
            listing: ListingEvent to add
        """
        self.listing_queue.put(listing)
        logger.debug(f"Manually added listing: {listing.listingId}")
    
    def get_queue_sizes(self) -> dict:
        """
        Get current size of all queues
        Useful for debugging
        
        Returns:
            dict: Queue names and their sizes
        """
        return {
            "listings": self.listing_queue.qsize(),
            "deal_scored": self.deal_scored_queue.qsize(),
            "deal_tagged": self.deal_tagged_queue.qsize(),
            "deal_events": self.deal_events_queue.qsize()
        }
    
    def __repr__(self) -> str:
        """String representation"""
        sizes = self.get_queue_sizes()
        return f"MemoryKafka(queues={sizes})"


# ============================================
# Example Usage
# ============================================

if __name__ == "__main__":
    # Example: How to use MemoryKafka
    
    # Initialize
    kafka = MemoryKafka(data_dir="data/mock")
    
    # Check queue sizes
    print(f"Queue sizes: {kafka.get_queue_sizes()}")
    
    # Consume listings
    listings = kafka.consume_listings()
    print(f"Consumed {len(listings)} listings")
    
    # Process first listing
    if listings:
        listing = listings[0]
        print(f"First listing: {listing.listingId} - ${listing.price}")
        
        # Simulate Deals Agent processing
        deal_scored = DealScoredEvent(
            listingId=listing.listingId,
            dealScore=85,
            isDeal=True,
            priceAdvantageScore=40,
            scarcityScore=30,
            ratingScore=15
        )
        kafka.publish_deal_scored(deal_scored)
        
        # Publish tagged event
        deal_tagged = DealTaggedEvent(
            listingId=listing.listingId,
            tags=["deal", "limited_availability"]
        )
        kafka.publish_deal_tagged(deal_tagged)
    
    # Check queue sizes again
    print(f"Queue sizes after processing: {kafka.get_queue_sizes()}")
    
    # Close
    kafka.close()
