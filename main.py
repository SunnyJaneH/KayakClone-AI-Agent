"""
AI Recommendation Service - FastAPI Application
Main entry point for the AI service

Integrates:
- Concierge Agent (chat)
- Deals Agent (background worker)
- Bundles API
- Watches API
- Price Analysis API
- Quotes API
- WebSocket Events
"""

import os
import sys
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

# Add the ai directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Configure loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/ai_service_{time}.log",
    rotation="500 MB",
    retention="10 days",
    level="DEBUG"
)


# ============================================
# Configuration
# ============================================

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_ENV = os.getenv("API_ENV", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:5173")

# Feature flags
ENABLE_DEALS_AGENT = os.getenv("ENABLE_DEALS_AGENT", "true").lower() == "true"
ENABLE_WEBSOCKET = os.getenv("ENABLE_WEBSOCKET", "true").lower() == "true"


# ============================================
# Import Routers and Services
# ============================================

# API Routers
try:
    from api.bundles import router as bundles_router
    BUNDLES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Bundles router not available: {e}")
    BUNDLES_AVAILABLE = False
    bundles_router = None

try:
    from api.watches import router as watches_router, watch_store
    WATCHES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Watches router not available: {e}")
    WATCHES_AVAILABLE = False
    watches_router = None
    watch_store = None

try:
    from api.price_analysis import router as price_analysis_router
    PRICE_ANALYSIS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Price analysis router not available: {e}")
    PRICE_ANALYSIS_AVAILABLE = False
    price_analysis_router = None

try:
    from api.quotes import router as quotes_router
    QUOTES_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Quotes router not available: {e}")
    QUOTES_AVAILABLE = False
    quotes_router = None

try:
    from api.chat import router as chat_router
    CHAT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Chat router not available: {e}")
    CHAT_AVAILABLE = False
    chat_router = None

# WebSocket Events
try:
    from api.events_websocket import events_manager, websocket_endpoint, router as events_router
    EVENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Events WebSocket not available: {e}")
    EVENTS_AVAILABLE = False
    events_manager = None
    events_router = None

# Background Services
try:
    from agents.deals_agent_runner import deals_agent, start_deals_agent, stop_deals_agent
    DEALS_AGENT_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Deals agent not available: {e}")
    DEALS_AGENT_AVAILABLE = False
    deals_agent = None

# Concierge Agent (for inline chat endpoint)
try:
    from agents.concierge_agent import concierge_agent, process_chat
    CONCIERGE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Concierge agent not available: {e}")
    CONCIERGE_AVAILABLE = False
    concierge_agent = None
    async def process_chat(query, user_id, session_id=None):
        return {"response": "AI service initializing...", "session_id": session_id}

# Session Store
try:
    from interfaces.session_store import session_store
    SESSION_AVAILABLE = True
except ImportError:
    SESSION_AVAILABLE = False
    session_store = None

# Deals Cache
try:
    from interfaces.deals_cache import deals_cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    deals_cache = None


# ============================================
# Lifespan Handler
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler
    Initializes and cleans up resources
    """
    # ========== STARTUP ==========
    logger.info("=" * 50)
    logger.info("Starting AI Recommendation Service...")
    logger.info(f"Environment: {API_ENV}")
    logger.info(f"CORS Origins: {CORS_ORIGINS}")
    logger.info("=" * 50)
    
    # Log available features
    features = {
        "Bundles API": BUNDLES_AVAILABLE,
        "Watches API": WATCHES_AVAILABLE,
        "Price Analysis": PRICE_ANALYSIS_AVAILABLE,
        "Quotes API": QUOTES_AVAILABLE,
        "Chat API": CHAT_AVAILABLE,
        "WebSocket Events": EVENTS_AVAILABLE and ENABLE_WEBSOCKET,
        "Deals Agent": DEALS_AGENT_AVAILABLE and ENABLE_DEALS_AGENT,
        "Concierge Agent": CONCIERGE_AVAILABLE,
        "Session Store": SESSION_AVAILABLE,
        "Deals Cache": CACHE_AVAILABLE,
    }
    
    logger.info("Feature Status:")
    for feature, available in features.items():
        status = "✅" if available else "❌"
        logger.info(f"  {status} {feature}")
    
    # Start Deals Agent background worker
    if DEALS_AGENT_AVAILABLE and ENABLE_DEALS_AGENT:
        try:
            await start_deals_agent()
            logger.info("Deals Agent started")
        except Exception as e:
            logger.error(f"Failed to start Deals Agent: {e}")
    
    # Register watch callbacks for WebSocket
    if watch_store and events_manager:
        watch_store.register_trigger_callback(events_manager.handle_watch_triggered)
        logger.info("Watch callbacks registered with Events manager")
    
    logger.info("AI Service startup complete")
    logger.info("=" * 50)
    
    yield
    
    # ========== SHUTDOWN ==========
    logger.info("=" * 50)
    logger.info("Shutting down AI Service...")
    
    # Stop Deals Agent
    if DEALS_AGENT_AVAILABLE and deals_agent:
        try:
            await stop_deals_agent()
            logger.info("Deals Agent stopped")
        except Exception as e:
            logger.error(f"Error stopping Deals Agent: {e}")
    
    # Close WebSocket connections
    if events_manager:
        await events_manager.shutdown()
        logger.info("WebSocket connections closed")
    
    logger.info("AI Service shutdown complete")
    logger.info("=" * 50)


# ============================================
# Create FastAPI Application
# ============================================

app = FastAPI(
    title="AI Recommendation Service",
    description="""
    Intelligent travel recommendation engine with conversational AI.
    
    ## Features
    - **Chat**: Natural language travel queries
    - **Bundles**: Flight + Hotel package recommendations
    - **Watches**: Price and availability alerts
    - **Price Analysis**: Deal validation and comparison
    - **Quotes**: Complete booking quotes
    - **WebSocket**: Real-time event notifications
    
    ## User Journeys
    1. Tell me what I should book
    2. Refine without starting over
    3. Keep an eye on it
    4. Decide with confidence
    5. Book or hand off cleanly
    """,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)


# ============================================
# CORS Middleware
# ============================================

cors_origins = [origin.strip() for origin in CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Register Routers
# ============================================

if BUNDLES_AVAILABLE and bundles_router:
    app.include_router(bundles_router)
    logger.info("Registered: Bundles API")

if WATCHES_AVAILABLE and watches_router:
    app.include_router(watches_router)
    logger.info("Registered: Watches API")

if PRICE_ANALYSIS_AVAILABLE and price_analysis_router:
    app.include_router(price_analysis_router)
    logger.info("Registered: Price Analysis API")

if QUOTES_AVAILABLE and quotes_router:
    app.include_router(quotes_router)
    logger.info("Registered: Quotes API")

if CHAT_AVAILABLE and chat_router:
    app.include_router(chat_router)
    logger.info("Registered: Chat API")

if EVENTS_AVAILABLE and events_router:
    app.include_router(events_router)
    logger.info("Events router registered")


# ============================================
# Core Endpoints
# ============================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "AI Recommendation Service",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "endpoints": {
            "chat": "/api/ai/chat",
            "bundles": "/api/ai/bundles",
            "watches": "/api/ai/watches",
            "price_analysis": "/api/ai/price-analysis",
            "quotes": "/api/ai/quotes",
            "events": "/api/ai/events (WebSocket)"
        }
    }


@app.get("/api/ai/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ai-recommendation-service",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "features": {
            "bundles": BUNDLES_AVAILABLE,
            "watches": WATCHES_AVAILABLE,
            "price_analysis": PRICE_ANALYSIS_AVAILABLE,
            "quotes": QUOTES_AVAILABLE,
            "chat": CHAT_AVAILABLE or CONCIERGE_AVAILABLE,
            "websocket": EVENTS_AVAILABLE and ENABLE_WEBSOCKET,
            "deals_agent": DEALS_AGENT_AVAILABLE and ENABLE_DEALS_AGENT
        }
    }


@app.get("/api/ai/status")
async def service_status():
    """Detailed service status"""
    status = {
        "service": "ai-recommendation-service",
        "version": "2.0.0",
        "environment": API_ENV,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {}
    }
    
    # Check Deals Agent
    if DEALS_AGENT_AVAILABLE and deals_agent:
        status["components"]["deals_agent"] = {
            "running": deals_agent.running,
            "status": "active" if deals_agent.running else "stopped"
        }
    
    # Check WebSocket connections
    if events_manager:
        status["components"]["websocket"] = {
            "active_connections": len(events_manager.active_connections),
            "status": "active"
        }
    
    # Check Deals Cache
    if CACHE_AVAILABLE and deals_cache:
        stats = deals_cache.get_stats()
        status["components"]["deals_cache"] = {
            "total_deals": stats.get("total_deals", 0),
            "status": "active"
        }
    
    # Check Session Store
    if SESSION_AVAILABLE and session_store:
        status["components"]["session_store"] = {
            "active_sessions": len(session_store._sessions) if hasattr(session_store, '_sessions') else "unknown",
            "status": "active"
        }
    
    return status


# ============================================
# Inline Chat Endpoint (if chat router not available)
# ============================================

if not CHAT_AVAILABLE:
    from pydantic import BaseModel
    from typing import Optional, List
    
    class ChatRequest(BaseModel):
        query: str
        user_id: str
        session_id: Optional[str] = None
        preferences: dict = {}
    
    class ChatResponse(BaseModel):
        response: str
        session_id: Optional[str] = None
        user_id: str
        type: str = "response"
        bundles: List[dict] = []
        timestamp: str
    
    @app.post("/api/ai/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest):
        """
        Chat with AI assistant
        
        Supports natural language travel queries.
        """
        try:
            result = await process_chat(
                query=request.query,
                user_id=request.user_id,
                session_id=request.session_id
            )
            
            return ChatResponse(
                response=result.get("response", "I'm here to help with travel recommendations!"),
                session_id=result.get("session_id"),
                user_id=request.user_id,
                type=result.get("type", "response"),
                bundles=result.get("bundles", []),
                timestamp=datetime.utcnow().isoformat()
            )
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)  # Include full traceback
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Return error response (200 status with error type, not 500)
            return ChatResponse(
                response="I apologize, but I encountered an error. Please try again.",
                session_id=request.session_id,
                user_id=request.user_id,
                type="error",
                bundles=[],
                timestamp=datetime.utcnow().isoformat()
            )


# ============================================
# WebSocket Endpoint
# ============================================

if EVENTS_AVAILABLE and ENABLE_WEBSOCKET:
    from fastapi import Query

    @app.websocket("/api/ai/events")
    async def websocket_events(websocket: WebSocket, user_id: str = Query(...)):
        """
        WebSocket endpoint for real-time events.
        
        Connect with: ws://host/api/ai/events?user_id=xxx
        
        Event types:
        - price_alert: Price dropped below threshold
        - inventory_alert: Low inventory warning
        - deal_found: New deal discovered
        - watch_triggered: User's watch triggered
        """
        await websocket_endpoint(websocket, user_id=user_id)
else:
    @app.websocket("/api/ai/events")
    async def websocket_events_disabled(websocket: WebSocket):
        """WebSocket disabled"""
        await websocket.accept()
        await websocket.send_json({
            "type": "error",
            "message": "WebSocket events are not enabled"
        })
        await websocket.close()


# ============================================
# Legacy Endpoints (backward compatibility)
# ============================================

@app.post("/api/ai/recommendations")
async def get_recommendations_legacy(request: dict):
    """
    Legacy recommendations endpoint.
    Use /api/ai/bundles for new integrations.
    """
    destination = request.get("destination", "")
    user_id = request.get("user_id", "")
    
    # Redirect to bundles if available
    if BUNDLES_AVAILABLE:
        from api.bundles import get_bundles
        try:
            result = await get_bundles(
                destination=destination,
                user_id=user_id
            )
            return {
                "recommendations": [b.model_dump() for b in result.bundles],
                "destination": destination,
                "user_id": user_id,
                "total_count": result.total_count,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Legacy recommendations error: {e}")
    
    # Fallback response
    return {
        "recommendations": [],
        "destination": destination,
        "user_id": user_id,
        "total_count": 0,
        "status": "success",
        "message": "Use /api/ai/bundles for bundle recommendations"
    }


@app.post("/api/ai/score")
async def score_deal_legacy(request: dict):
    """
    Legacy score endpoint.
    Use /api/ai/price-analysis for new integrations.
    """
    return {
        "flight_score": 75,
        "hotel_score": 75,
        "bundle_score": 75,
        "recommendation": "Use /api/ai/price-analysis/{type}/{id} for detailed analysis",
        "status": "success"
    }


# ============================================
# Error Handlers
# ============================================

from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc) if API_ENV == "development" else "An unexpected error occurred",
            "timestamp": datetime.utcnow().isoformat()
        }
    )


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    # Create logs directory
    os.makedirs("logs", exist_ok=True)
    
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=API_ENV == "development",
        log_level="info"
    )
