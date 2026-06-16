# api/chat.py
"""
Chat API Endpoint
Main conversational interface for the AI Concierge.

Supports all 5 user journeys:
1. Tell me what I should book
2. Refine without starting over
3. Keep an eye on it
4. Decide with confidence
5. Book or hand off cleanly
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from loguru import logger

# Import Concierge Agent
try:
    from agents.concierge_agent import concierge_agent, process_chat
    CONCIERGE_AVAILABLE = True
except ImportError:
    CONCIERGE_AVAILABLE = False
    concierge_agent = None

# Import Session Store
try:
    from interfaces.session_store import session_store
    SESSION_AVAILABLE = True
except ImportError:
    SESSION_AVAILABLE = False
    session_store = None


router = APIRouter(prefix="/api/ai", tags=["chat"])


# ============================================
# Request/Response Models
# ============================================

class ChatMessage(BaseModel):
    """Single chat message"""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ChatRequest(BaseModel):
    """Chat request model"""
    query: str = Field(..., min_length=1, max_length=2000, description="User's message")
    user_id: str = Field(..., description="User identifier")
    session_id: Optional[str] = Field(None, description="Session ID for context continuity")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User preferences")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class BundlePreview(BaseModel):
    """Preview of a bundle in chat response"""
    bundle_id: str
    name: str
    total_price: float
    deal_score: int
    why_this: str
    what_to_watch: str


class ChatResponse(BaseModel):
    """Chat response model"""
    response: str = Field(..., description="AI assistant's response")
    session_id: Optional[str] = Field(None, description="Session ID for continuation")
    user_id: str
    
    # Response metadata
    type: str = Field("response", description="Response type: response, clarification, recommendations, quote, etc.")
    confidence: float = Field(0.9, ge=0, le=1)
    
    # Recommendations (if applicable)
    bundles: List[BundlePreview] = Field(default_factory=list)
    
    # Parsed intent (for debugging/transparency)
    parsed_intent: Optional[Dict[str, Any]] = None
    
    # Changes from previous (for "Refine without starting over")
    changes: Optional[List[Dict[str, Any]]] = None
    
    # Suggested follow-ups
    suggestions: List[str] = Field(default_factory=list)
    
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ConversationHistory(BaseModel):
    """Conversation history response"""
    session_id: str
    user_id: str
    messages: List[ChatMessage]
    search_params: Dict[str, Any] = {}
    created_at: str
    last_activity: str


class SuggestionRequest(BaseModel):
    """Request for follow-up suggestions"""
    session_id: Optional[str] = None
    user_id: str
    context: str = ""


# ============================================
# Helper Functions
# ============================================

def generate_suggestions(response_type: str, context: Dict = None) -> List[str]:
    """Generate contextual follow-up suggestions"""
    
    if response_type == "recommendations":
        return [
            "Tell me more about option 1",
            "Is this a good deal?",
            "Watch the price for me",
            "Get me a full quote",
            "Show me pet-friendly options"
        ]
    
    if response_type == "clarification":
        return [
            "Miami",
            "New York",
            "Los Angeles",
            "Anywhere warm",
            "Somewhere cheap"
        ]
    
    if response_type == "price_analysis":
        return [
            "Book it",
            "Show me alternatives",
            "Watch for a better price",
            "What's the cancellation policy?"
        ]
    
    if response_type == "quote":
        return [
            "Book now",
            "What if I need to cancel?",
            "Are there cheaper options?",
            "Add travel insurance"
        ]
    
    if response_type == "watch_created":
        return [
            "Show me my watches",
            "Search for something else",
            "What deals do you have today?"
        ]
    
    # Default suggestions
    return [
        "Find me a trip to Miami",
        "What's the best deal right now?",
        "I need a pet-friendly hotel",
        "Show me weekend getaways"
    ]


def format_bundles_for_response(bundles: List[Dict]) -> List[BundlePreview]:
    """Convert bundle dicts to BundlePreview models"""
    previews = []
    
    for b in bundles[:5]:  # Limit to 5
        explanation = b.get("explanation", {})
        previews.append(BundlePreview(
            bundle_id=b.get("bundle_id", ""),
            name=b.get("name", "Travel Package"),
            total_price=b.get("total_price", 0),
            deal_score=b.get("deal_score", 70),
            why_this=explanation.get("why_this", "Good value"),
            what_to_watch=explanation.get("what_to_watch", "Book soon")
        ))
    
    return previews


# ============================================
# API Endpoints
# ============================================

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with AI travel assistant.
    
    Supports natural language queries for:
    - Finding flights and hotels
    - Refining search with constraints
    - Setting price/availability watches
    - Getting price analysis
    - Generating booking quotes
    
    Example queries:
    - "Find me a trip to Miami next weekend under $1000"
    - "Make it pet-friendly"
    - "Is this a good deal?"
    - "Watch the price for me"
    - "Book it"
    """
    logger.info(f"Chat request: user={request.user_id}, query={request.query[:50]}...")
    
    try:
        if CONCIERGE_AVAILABLE and concierge_agent:
            # Use the full Concierge Agent
            # Note: process_message signature is (user_id, query, session_id)
            result = await concierge_agent.process_message(
                user_id=request.user_id,
                query=request.query,
                session_id=request.session_id
            )
        else:
            # Fallback to basic process_chat
            result = await process_chat(
                query=request.query,
                user_id=request.user_id,
                session_id=request.session_id
            )
        
        # Extract response components
        response_text = result.get("response", "I'm here to help with travel planning!")
        response_type = result.get("type", "response")
        bundles = result.get("bundles", [])
        changes = result.get("changes")
        parsed_intent = result.get("parsed_intent")
        tool_used = result.get("tool_used")  # Extract tool_used for debugging
        
        # Log tool usage for debugging
        if tool_used:
            logger.info(f"Tool used: {tool_used}, bundles found: {len(bundles)}")
        
        # Generate suggestions based on response type
        suggestions = generate_suggestions(response_type, result)
        
        # Format bundles
        bundle_previews = format_bundles_for_response(bundles) if bundles else []
        
        return ChatResponse(
            response=response_text,
            session_id=result.get("session_id", request.session_id),
            user_id=request.user_id,
            type=response_type,
            confidence=0.9,
            bundles=bundle_previews,
            parsed_intent=parsed_intent,
            changes=changes,
            suggestions=suggestions,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)  # Include full traceback
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Return error response (200 status with error type, not 500)
        return ChatResponse(
            response="I apologize, but I encountered an error processing your request. Please try again.",
            session_id=request.session_id,
            user_id=request.user_id,
            type="error",
            confidence=0.0,
            suggestions=["Try again", "Start a new search"],
            timestamp=datetime.utcnow().isoformat()
        )


@router.get("/chat/history/{session_id}", response_model=ConversationHistory)
async def get_chat_history(
    session_id: str,
    user_id: str = Query(..., description="User ID for validation")
):
    """
    Get conversation history for a session.
    
    Returns all messages and accumulated search parameters.
    """
    if not SESSION_AVAILABLE or not session_store:
        raise HTTPException(
            status_code=503,
            detail="Session store not available"
        )
    
    session = session_store.get_session(session_id)
    
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found"
        )
    
    # Validate user
    if session.get("user_id") != user_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )
    
    # Build message history
    messages = []
    for msg in session.get("messages", []):
        messages.append(ChatMessage(
            role=msg.get("role", "user"),
            content=msg.get("content", ""),
            timestamp=msg.get("timestamp", datetime.utcnow().isoformat())
        ))
    
    return ConversationHistory(
        session_id=session_id,
        user_id=user_id,
        messages=messages,
        search_params=session.get("search_params", {}),
        created_at=session.get("created_at", datetime.utcnow().isoformat()),
        last_activity=session.get("last_activity", datetime.utcnow().isoformat())
    )


@router.delete("/chat/session/{session_id}")
async def clear_session(
    session_id: str,
    user_id: str = Query(..., description="User ID for validation")
):
    """
    Clear a chat session.
    
    Removes all context and starts fresh.
    """
    if SESSION_AVAILABLE and session_store:
        # Validate ownership
        session = session_store.get_session(session_id)
        if session and session.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete session
        session_store.delete_session(session_id)
    
    return {
        "status": "cleared",
        "session_id": session_id,
        "message": "Session cleared. Start a new conversation!"
    }


@router.post("/chat/suggestions")
async def get_suggestions(request: SuggestionRequest):
    """
    Get contextual follow-up suggestions.
    
    Based on current session state and context.
    """
    suggestions = []
    
    # Get session context
    if SESSION_AVAILABLE and session_store and request.session_id:
        session = session_store.get_session(request.session_id)
        if session:
            params = session.get("search_params", {})
            
            # Destination-based suggestions
            if not params.get("destination"):
                suggestions.extend([
                    "Find me a trip to Miami",
                    "Show me deals to New York",
                    "Where can I go for under $500?"
                ])
            else:
                dest = params.get("destination")
                suggestions.extend([
                    f"Show me pet-friendly hotels in {dest}",
                    f"Find direct flights to {dest}",
                    "Is this a good deal?",
                    "Watch the price for me"
                ])
    
    # Default suggestions if none generated
    if not suggestions:
        suggestions = generate_suggestions("default")
    
    return {
        "suggestions": suggestions[:6],
        "session_id": request.session_id,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/chat/sessions")
async def list_user_sessions(
    user_id: str = Query(..., description="User ID")
):
    """
    List all active sessions for a user.
    """
    if not SESSION_AVAILABLE or not session_store:
        return {"sessions": [], "count": 0}
    
    sessions = session_store.get_user_sessions(user_id)
    
    return {
        "sessions": [
            {
                "session_id": s.get("session_id"),
                "created_at": s.get("created_at"),
                "last_activity": s.get("last_activity"),
                "destination": s.get("search_params", {}).get("destination")
            }
            for s in sessions
        ],
        "count": len(sessions),
        "user_id": user_id
    }


# ============================================
# Quick Action Endpoints
# ============================================

@router.post("/chat/quick/search")
async def quick_search(
    destination: str = Query(..., description="Destination"),
    user_id: str = Query(..., description="User ID"),
    budget: Optional[float] = Query(None, description="Max budget"),
    date_from: Optional[str] = Query(None, description="Departure date"),
    date_to: Optional[str] = Query(None, description="Return date")
):
    """
    Quick search without natural language.
    
    Directly creates a search from parameters.
    """
    # Build query from parameters
    query_parts = [f"Find me a trip to {destination}"]
    
    if date_from and date_to:
        query_parts.append(f"from {date_from} to {date_to}")
    
    if budget:
        query_parts.append(f"under ${budget}")
    
    query = " ".join(query_parts)
    
    # Process as chat
    request = ChatRequest(
        query=query,
        user_id=user_id
    )
    
    return await chat(request)


@router.post("/chat/quick/refine")
async def quick_refine(
    session_id: str = Query(..., description="Session to refine"),
    user_id: str = Query(..., description="User ID"),
    constraint: str = Query(..., description="Constraint to add (e.g., 'pet-friendly')")
):
    """
    Quick refinement of existing search.
    
    Adds a constraint without full natural language.
    """
    # Build refinement query
    query = f"Make it {constraint}"
    
    request = ChatRequest(
        query=query,
        user_id=user_id,
        session_id=session_id
    )
    
    return await chat(request)


@router.post("/chat/quick/watch")
async def quick_watch(
    session_id: str = Query(..., description="Session with recommendations"),
    user_id: str = Query(..., description="User ID"),
    threshold: Optional[float] = Query(None, description="Price threshold")
):
    """
    Quick watch creation for current recommendations.
    """
    query = "Watch the price for me"
    if threshold:
        query = f"Alert me if price drops below ${threshold}"
    
    request = ChatRequest(
        query=query,
        user_id=user_id,
        session_id=session_id
    )
    
    return await chat(request)


@router.post("/chat/quick/quote")
async def quick_quote(
    session_id: str = Query(..., description="Session with recommendations"),
    user_id: str = Query(..., description="User ID"),
    bundle_index: int = Query(0, ge=0, le=4, description="Which bundle (0-4)")
):
    """
    Quick quote for a specific bundle.
    """
    query = f"Get me a full quote for option {bundle_index + 1}"
    
    request = ChatRequest(
        query=query,
        user_id=user_id,
        session_id=session_id
    )
    
    return await chat(request)
