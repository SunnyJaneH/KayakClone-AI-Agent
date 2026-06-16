"""
AI Chat API Endpoints
FastAPI routes for Concierge Agent
"""

import uuid
import time
from typing import Dict
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger

from schemas.ai_schemas import (
    SessionCreateResponse,
    QueryRequest,
    QueryResponse,
    ParsedIntent,
    BundleResponse,
    FlightInfo,
    HotelInfo,
    WatchRequest,
    WatchResponse,
    ErrorResponse
)
from llm.intent_parser import IntentParser
from algorithms.bundle_matcher import find_best_bundles
from kafka.memory_kafka import MemoryKafka
from kafka.message_schemas import ListingEvent


# Create router
router = APIRouter(prefix="/api/v1/ai", tags=["AI"])

# Global state (in production, use proper session management)
active_sessions: Dict[str, dict] = {}
intent_parser = IntentParser(use_cache=True)


# ============================================
# Session Management
# ============================================

@router.post("/sessions", response_model=SessionCreateResponse)
async def create_session():
    """
    Create a new conversation session
    
    Returns:
        SessionCreateResponse: New session ID
    """
    session_id = f"session-{uuid.uuid4().hex[:12]}"
    
    active_sessions[session_id] = {
        "created_at": time.time(),
        "queries": [],
        "watches": []
    }
    
    logger.info(f"Created session: {session_id}")
    
    return SessionCreateResponse(sessionId=session_id)


# ============================================
# Query Endpoint
# ============================================

@router.post("/sessions/{session_id}/query", response_model=QueryResponse)
async def query(session_id: str, request: QueryRequest):
    """
    Process natural language travel query
    
    Args:
        session_id: Session identifier
        request: Query request with natural language query
    
    Returns:
        QueryResponse: Bundle recommendations
    
    Example:
        POST /api/v1/ai/sessions/abc123/query
        {
            "query": "Find cheap flights from SFO to Miami under $800"
        }
    """
    start_time = time.time()
    
    # Validate session
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Parse intent using LLM
        logger.info(f"[{session_id}] Processing query: '{request.query}'")
        parsed_intent = intent_parser.parse(request.query)
        
        # Get available listings from MemoryKafka
        kafka = MemoryKafka(data_dir='../data/mock')
        listings = kafka.consume_listings()
        
        # Separate flights and hotels
        flights = []
        hotels = []
        
        for listing in listings:
            if listing.listingType == "flight":
                flights.append({
                    "listingId": listing.listingId,
                    "departure": listing.departure,
                    "arrival": listing.arrival,
                    "date": listing.date,
                    "airline": listing.airline,
                    "price": listing.price,
                    "avg_30d_price": listing.avg_30d_price,
                    "availability": listing.availability,
                    "rating": listing.rating,
                    "duration": listing.duration or 0,
                    "stops": listing.stops or 0,
                    "has_promotion": listing.has_promotion
                })
            elif listing.listingType == "hotel":
                hotels.append({
                    "listingId": listing.listingId,
                    "hotelName": listing.hotelName,
                    "city": listing.city,
                    "price": listing.price,
                    "avg_30d_price": listing.avg_30d_price,
                    "availability": listing.availability,
                    "rating": listing.rating,
                    "starRating": listing.starRating,
                    "amenities": listing.amenities or [],
                    "policies": listing.policies or {},
                    "location": listing.location or {},
                    "has_promotion": listing.has_promotion
                })
        
        # Find best bundles
        user_query_dict = {
            "origin": parsed_intent.get("origin"),
            "destination": parsed_intent.get("destination"),
            "dates": parsed_intent.get("dates"),
            "budget": parsed_intent.get("budget"),
            "constraints": parsed_intent.get("constraints", [])
        }
        
        bundle_results = find_best_bundles(
            flights=flights,
            hotels=hotels,
            user_query=user_query_dict,
            top_k=3
        )
        
        # Convert to response format
        bundles = []
        for bundle in bundle_results:
            bundles.append(BundleResponse(
                bundleId=bundle["bundleId"],
                totalPrice=bundle["totalPrice"],
                savings=bundle["savings"],
                dealScore=bundle["dealScore"],
                fitScore=bundle["fitScore"],
                combinedScore=bundle["combinedScore"],
                explanation=bundle["explanation"],
                flight=FlightInfo(**bundle["flight"]),
                hotel=HotelInfo(**bundle["hotel"])
            ))
        
        processing_time = time.time() - start_time
        
        logger.info(
            f"[{session_id}] Returning {len(bundles)} bundles "
            f"(processing: {processing_time:.2f}s)"
        )
        
        # Store query in session
        active_sessions[session_id]["queries"].append({
            "query": request.query,
            "intent": parsed_intent,
            "results": len(bundles)
        })
        
        return QueryResponse(
            sessionId=session_id,
            query=request.query,
            parsedIntent=ParsedIntent(**parsed_intent),
            bundles=bundles,
            totalResults=len(bundles),
            processingTime=round(processing_time, 2)
        )
        
    except Exception as e:
        logger.error(f"[{session_id}] Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Watch Endpoint
# ============================================

@router.post("/sessions/{session_id}/watch", response_model=WatchResponse)
async def create_watch(session_id: str, request: WatchRequest):
    """
    Create a watch for price alerts
    
    Args:
        session_id: Session identifier
        request: Watch request with listing ID and target price
    
    Returns:
        WatchResponse: Watch confirmation
    """
    # Validate session
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    watch_id = f"watch-{uuid.uuid4().hex[:12]}"
    
    # Store watch
    watch_info = {
        "watch_id": watch_id,
        "listing_id": request.listingId,
        "target_price": request.targetPrice,
        "created_at": time.time()
    }
    
    active_sessions[session_id]["watches"].append(watch_info)
    
    logger.info(
        f"[{session_id}] Created watch: {watch_id} for {request.listingId} "
        f"(target: ${request.targetPrice})"
    )
    
    return WatchResponse(
        watchId=watch_id,
        listingId=request.listingId,
        targetPrice=request.targetPrice
    )


# ============================================
# WebSocket Endpoint
# ============================================

@router.websocket("/sessions/{session_id}/events")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time notifications
    
    Sends:
    - DEAL_UPDATE: New deals matching user preferences
    - WATCH_NOTIFICATION: Price alerts for watched listings
    """
    await websocket.accept()
    logger.info(f"[{session_id}] WebSocket connected")
    
    try:
        # Send welcome message
        await websocket.send_json({
            "eventType": "CONNECTION_ESTABLISHED",
            "sessionId": session_id,
            "message": "Connected to AI Service notifications"
        })
        
        # Keep connection alive and send updates
        while True:
            # In production, this would:
            # 1. Listen to Kafka for new deals
            # 2. Check if deals match user's session preferences
            # 3. Send DEAL_UPDATE notifications
            # 4. Monitor watched listings for price changes
            # 5. Send WATCH_NOTIFICATION when price drops
            
            # For now, keep connection alive
            data = await websocket.receive_text()
            
            # Echo back (for testing)
            await websocket.send_json({
                "eventType": "ECHO",
                "message": f"Received: {data}"
            })
            
    except WebSocketDisconnect:
        logger.info(f"[{session_id}] WebSocket disconnected")
    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}")
        await websocket.close()
