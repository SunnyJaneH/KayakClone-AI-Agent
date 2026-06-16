"""
Data Interface - Database Access Layer
Adapted for middleware schema with camelCase fields and separate databases
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

import mysql.connector
from mysql.connector import pooling, Error as MySQLError

from ..config import settings

logger = logging.getLogger(__name__)


class DataInterface:
    """
    Data interface for accessing user and booking data
    
    Connects to middleware's MySQL databases:
    - kayak_users: User profiles and authentication
    - kayak_bookings: Booking history and inventory
    - kayak_billing: Payment information
    
    Note: Uses camelCase field names as per middleware schema
    """
    
    def __init__(self):
        """Initialize database connection pools"""
        self._pools: Dict[str, pooling.MySQLConnectionPool] = {}
        self._initialized = False
    
    def _ensure_connected(self):
        """Ensure connection pools are initialized"""
        if self._initialized:
            return
        
        try:
            # Create connection pool for users database
            self._pools["users"] = pooling.MySQLConnectionPool(
                pool_name="users_pool",
                pool_size=settings.DB_POOL_SIZE,
                **settings.get_mysql_config("users")
            )
            
            # Create connection pool for bookings database
            self._pools["bookings"] = pooling.MySQLConnectionPool(
                pool_name="bookings_pool",
                pool_size=settings.DB_POOL_SIZE,
                **settings.get_mysql_config("bookings")
            )
            
            self._initialized = True
            logger.info("DataInterface connected to MySQL databases")
            
        except MySQLError as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise
    
    def _get_connection(self, database: str = "users"):
        """
        Get a connection from the pool
        
        Args:
            database: Which database pool to use (users, bookings, billing)
        
        Returns:
            MySQL connection
        """
        self._ensure_connected()
        
        pool = self._pools.get(database)
        if not pool:
            raise ValueError(f"Unknown database: {database}")
        
        return pool.get_connection()
    
    async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """
        Get user by userId (SSN format)
        
        Args:
            user_id: User ID in SSN format (###-##-####)
        
        Returns:
            User dict or None
        """
        try:
            conn = self._get_connection("users")
            cursor = conn.cursor(dictionary=True)
            
            # Query using camelCase field names (middleware schema)
            query = """
                SELECT 
                    userId,
                    firstName,
                    lastName,
                    email,
                    phone,
                    address,
                    role,
                    createdAt,
                    updatedAt
                FROM users
                WHERE userId = %s
            """
            
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if row:
                # Parse JSON address field
                if row.get("address") and isinstance(row["address"], str):
                    try:
                        row["address"] = json.loads(row["address"])
                    except json.JSONDecodeError:
                        pass
                
                return row
            
            return None
            
        except MySQLError as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    async def get_user_preferences(self, user_id: str) -> Optional[Dict]:
        """
        Get user preferences
        
        Since middleware schema doesn't have a preferences field,
        we infer preferences from booking history
        
        Args:
            user_id: User ID (SSN format)
        
        Returns:
            Inferred preferences dict
        """
        try:
            # Get user basic info
            user = await self.get_user_by_id(user_id)
            
            # Get booking history to infer preferences
            bookings = await self.get_booking_history(user_id, limit=20)
            
            # Infer preferences from booking patterns
            preferences = self._infer_preferences_from_bookings(bookings)
            
            return {
                "user_id": user_id,
                "user_name": f"{user.get('firstName', '')} {user.get('lastName', '')}" if user else None,
                "email": user.get("email") if user else None,
                "preferences": preferences,
                "inferred": True  # Flag that these are inferred, not explicit
            }
            
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")
            return None
    
    def _infer_preferences_from_bookings(self, bookings: List[Dict]) -> Dict:
        """
        Infer user preferences from booking history
        
        Args:
            bookings: List of past bookings
        
        Returns:
            Inferred preferences dict
        """
        if not bookings:
            return {
                "budget": "medium",
                "interests": [],
                "preferred_listing_types": []
            }
        
        # Analyze booking patterns
        total_spent = sum(b.get("totalPrice", 0) for b in bookings)
        avg_price = total_spent / len(bookings) if bookings else 0
        
        # Determine budget level
        if avg_price < 200:
            budget = "budget"
        elif avg_price < 500:
            budget = "medium"
        else:
            budget = "luxury"
        
        # Get preferred listing types
        listing_types = [b.get("listingType") for b in bookings if b.get("listingType")]
        type_counts = {}
        for lt in listing_types:
            type_counts[lt] = type_counts.get(lt, 0) + 1
        
        preferred_types = sorted(type_counts.keys(), key=lambda x: type_counts[x], reverse=True)
        
        # Extract destinations/interests from booking details
        interests = []
        for booking in bookings:
            details = booking.get("additionalDetails", {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except:
                    details = {}
            
            if details.get("destination"):
                interests.append(details["destination"])
        
        return {
            "budget": budget,
            "avg_booking_price": round(avg_price, 2),
            "total_bookings": len(bookings),
            "preferred_listing_types": preferred_types[:3],
            "interests": list(set(interests))[:5]
        }
    
    async def get_booking_history(
        self,
        user_id: str,
        limit: int = 10,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        Get user's booking history
        
        Args:
            user_id: User ID (SSN format)
            limit: Max number of bookings to return
            status: Filter by status (pending, confirmed, cancelled)
        
        Returns:
            List of booking dicts
        """
        try:
            conn = self._get_connection("bookings")
            cursor = conn.cursor(dictionary=True)
            
            # Build query with camelCase fields
            query = """
                SELECT 
                    bookingId,
                    userId,
                    listingType,
                    listingId,
                    startDate,
                    endDate,
                    guests,
                    totalPrice,
                    status,
                    additionalDetails,
                    createdAt,
                    updatedAt
                FROM bookings
                WHERE userId = %s
            """
            
            params = [user_id]
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            query += " ORDER BY createdAt DESC LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            # Parse JSON fields
            for row in rows:
                if row.get("additionalDetails") and isinstance(row["additionalDetails"], str):
                    try:
                        row["additionalDetails"] = json.loads(row["additionalDetails"])
                    except json.JSONDecodeError:
                        pass
                
                # Convert dates to strings for JSON serialization
                for date_field in ["startDate", "endDate", "createdAt", "updatedAt"]:
                    if row.get(date_field) and hasattr(row[date_field], "isoformat"):
                        row[date_field] = row[date_field].isoformat()
            
            return rows
            
        except MySQLError as e:
            logger.error(f"Error getting booking history: {e}")
            return []
    
    async def get_inventory(
        self,
        listing_type: Optional[str] = None,
        listing_id: Optional[str] = None
    ) -> List[Dict]:
        """
        Get inventory information
        
        Args:
            listing_type: Filter by type (hotel, flight, car)
            listing_id: Filter by specific listing
        
        Returns:
            List of inventory records
        """
        try:
            conn = self._get_connection("bookings")
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    inventoryId,
                    listingType,
                    listingId,
                    availableCount,
                    pricePerUnit,
                    createdAt,
                    updatedAt
                FROM inventory
                WHERE 1=1
            """
            
            params = []
            
            if listing_type:
                query += " AND listingType = %s"
                params.append(listing_type)
            
            if listing_id:
                query += " AND listingId = %s"
                params.append(listing_id)
            
            query += " ORDER BY listingType, listingId"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return rows
            
        except MySQLError as e:
            logger.error(f"Error getting inventory: {e}")
            return []
    
    async def get_user_booking_summary(self, user_id: str) -> Optional[Dict]:
        """
        Get user booking summary statistics
        
        Args:
            user_id: User ID (SSN format)
        
        Returns:
            Summary dict with booking stats
        """
        try:
            conn = self._get_connection("bookings")
            cursor = conn.cursor(dictionary=True)
            
            # Use the view created in mysql-init.sql
            query = """
                SELECT 
                    userId,
                    total_bookings,
                    total_spent,
                    last_booking_date
                FROM user_booking_summary
                WHERE userId = %s
            """
            
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            return row
            
        except MySQLError as e:
            logger.error(f"Error getting booking summary: {e}")
            return None
    
    async def search_users(
        self,
        email: Optional[str] = None,
        name: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search for users
        
        Args:
            email: Email to search for (partial match)
            name: Name to search for (partial match)
            limit: Max results
        
        Returns:
            List of matching users
        """
        try:
            conn = self._get_connection("users")
            cursor = conn.cursor(dictionary=True)
            
            query = """
                SELECT 
                    userId,
                    firstName,
                    lastName,
                    email,
                    role,
                    createdAt
                FROM users
                WHERE 1=1
            """
            
            params = []
            
            if email:
                query += " AND email LIKE %s"
                params.append(f"%{email}%")
            
            if name:
                query += " AND (firstName LIKE %s OR lastName LIKE %s)"
                params.extend([f"%{name}%", f"%{name}%"])
            
            query += " LIMIT %s"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            cursor.close()
            conn.close()
            
            return rows
            
        except MySQLError as e:
            logger.error(f"Error searching users: {e}")
            return []
    
    async def health_check(self) -> Dict[str, bool]:
        """
        Check database connectivity
        
        Returns:
            Dict with health status for each database
        """
        status = {
            "users_db": False,
            "bookings_db": False
        }
        
        try:
            # Check users database
            conn = self._get_connection("users")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            status["users_db"] = True
        except Exception as e:
            logger.error(f"Users DB health check failed: {e}")
        
        try:
            # Check bookings database
            conn = self._get_connection("bookings")
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            status["bookings_db"] = True
        except Exception as e:
            logger.error(f"Bookings DB health check failed: {e}")
        
        return status
    
    def close(self):
        """Close all connection pools"""
        # Connection pools don't have explicit close in mysql-connector
        self._initialized = False
        self._pools = {}
        logger.info("DataInterface connections closed")


# Singleton instance
_data_interface_instance: Optional[DataInterface] = None


def get_data_interface() -> DataInterface:
    """Get singleton instance of DataInterface"""
    global _data_interface_instance
    if _data_interface_instance is None:
        _data_interface_instance = DataInterface()
    return _data_interface_instance
