"""
AI Service Configuration
Loads settings from environment variables
"""

import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Application settings loaded from environment"""
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    
    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    KAFKA_CONSUMER_GROUP: str = os.getenv("KAFKA_CONSUMER_GROUP", "ai-deals-agent")
    
    # Kafka Topics - aligned with middleware kafka.js
    KAFKA_DEALS_RAW_TOPIC: str = os.getenv("KAFKA_DEALS_RAW_TOPIC", "raw_supplier_feeds")
    KAFKA_DEALS_NORMALIZED_TOPIC: str = os.getenv("KAFKA_DEALS_NORMALIZED_TOPIC", "deals.normalized")
    KAFKA_DEALS_SCORED_TOPIC: str = os.getenv("KAFKA_DEALS_SCORED_TOPIC", "deals.scored")
    KAFKA_DEALS_TAGGED_TOPIC: str = os.getenv("KAFKA_DEALS_TAGGED_TOPIC", "deals.tagged")
    KAFKA_DEAL_EVENTS_TOPIC: str = os.getenv("KAFKA_DEAL_EVENTS_TOPIC", "deal.events")
    
    # Additional Kafka Topics from middleware
    KAFKA_USER_EVENTS_TOPIC: str = "user.events"
    KAFKA_BOOKING_EVENTS_TOPIC: str = "booking.events"
    KAFKA_LISTING_EVENTS_TOPIC: str = "listing.events"
    KAFKA_SEARCH_UPDATES_TOPIC: str = "search.updates"
    
    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_TTL: int = int(os.getenv("REDIS_TTL", "300"))
    
    # MySQL Configuration - Separate databases per middleware schema
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "password")
    
    # Separate database names (as per middleware mysql-init.sql)
    DB_NAME_USERS: str = os.getenv("DB_NAME_USERS", "kayak_users")
    DB_NAME_BOOKINGS: str = os.getenv("DB_NAME_BOOKINGS", "kayak_bookings")
    DB_NAME_BILLING: str = os.getenv("DB_NAME_BILLING", "kayak_billing")
    
    # MongoDB Configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "kayak_doc")
    MONGO_DB_SEARCH: str = os.getenv("MONGO_DB_SEARCH", "kayak_search")
    
    # Ollama Configuration (for local embeddings)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "mxbai-embed-large")
    
    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_ENV: str = os.getenv("API_ENV", "development")
    
    # CORS Configuration
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
    
    # JWT Configuration (aligned with middleware)
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-key-change-in-production")
    JWT_EXPIRY: str = os.getenv("JWT_EXPIRY", "24h")
    
    # Performance Settings
    BUNDLE_MATCHING_INTERVAL: int = int(os.getenv("BUNDLE_MATCHING_INTERVAL", "30"))
    CACHE_TTL: int = int(os.getenv("CACHE_TTL", "300"))
    MAX_RECOMMENDATIONS: int = int(os.getenv("MAX_RECOMMENDATIONS", "20"))
    SEMANTIC_SIMILARITY_THRESHOLD: float = float(os.getenv("SEMANTIC_SIMILARITY_THRESHOLD", "0.85"))
    
    # Database Connection Pool Settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_POOL_MAX_OVERFLOW: int = int(os.getenv("DB_POOL_MAX_OVERFLOW", "10"))
    DB_QUERY_TIMEOUT: int = int(os.getenv("DB_QUERY_TIMEOUT", "5"))
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    @property
    def redis_url(self) -> str:
        """Get Redis connection URL"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    def get_mysql_config(self, database: str = None) -> dict:
        """
        Get MySQL connection configuration
        
        Args:
            database: Database name (users, bookings, or billing)
        
        Returns:
            MySQL connection config dict
        """
        db_name = database
        if database == "users":
            db_name = self.DB_NAME_USERS
        elif database == "bookings":
            db_name = self.DB_NAME_BOOKINGS
        elif database == "billing":
            db_name = self.DB_NAME_BILLING
        
        return {
            "host": self.DB_HOST,
            "port": self.DB_PORT,
            "user": self.DB_USER,
            "password": self.DB_PASSWORD,
            "database": db_name or self.DB_NAME_USERS,
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci"
        }


# Global settings instance
settings = Settings()
