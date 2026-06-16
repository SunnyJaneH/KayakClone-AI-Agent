# ai/__init__.py
"""
AI Recommendation Service Package

A comprehensive travel recommendation engine with:
- Conversational AI (Concierge Agent)
- Deal Detection & Scoring (Deals Agent)  
- Bundle Recommendations
- Price/Availability Watches
- Real-time WebSocket Events

User Journeys Supported:
1. Tell me what I should book
2. Refine without starting over
3. Keep an eye on it
4. Decide with confidence
5. Book or hand off cleanly
"""

__version__ = "2.0.0"
__author__ = "DATA 236 Team"

# Package structure:
# ai/
# ├── __init__.py           <- This file
# ├── main.py               <- FastAPI application entry
# ├── config.py             <- Configuration settings
# │
# ├── agents/               <- AI Agents
# │   ├── __init__.py
# │   ├── concierge_agent_v2.py  <- Chat-facing agent
# │   └── deals_agent_runner.py  <- Background Kafka worker
# │
# ├── api/                  <- FastAPI Routers
# │   ├── __init__.py
# │   ├── chat.py           <- /api/ai/chat
# │   ├── bundles.py        <- /api/ai/bundles
# │   ├── watches.py        <- /api/ai/watches
# │   ├── price_analysis.py <- /api/ai/price-analysis
# │   ├── quotes.py         <- /api/ai/quotes
# │   └── events_websocket.py <- WS /api/ai/events
# │
# ├── interfaces/           <- Data Stores
# │   ├── __init__.py
# │   ├── session_store.py  <- Session management
# │   ├── deals_cache.py    <- Scored deals cache
# │   └── policy_store.py   <- Listing policies
# │
# ├── llm/                  <- LLM Components
# │   ├── __init__.py
# │   ├── intent_parser.py  <- NL to structured intent
# │   ├── explainer.py      <- Generate explanations
# │   └── quote_generator.py <- Generate quotes
# │
# ├── schemas/              <- Pydantic Models
# │   ├── __init__.py
# │   └── ai_schemas.py     <- All schemas
# │
# ├── algorithms/           <- Scoring algorithms (existing)
# │   └── deal_scorer.py
# │
# └── kafka_client/         <- Kafka integration (existing)
#     ├── kafka_producer.py
#     └── kafka_consumer.py
