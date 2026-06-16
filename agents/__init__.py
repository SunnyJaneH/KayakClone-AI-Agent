# agents/__init__.py
"""
AI Agents Package

Contains the core AI agents:
- ConciergeAgent: Chat-facing agent for user interactions
- DealsAgent: Background worker for deal processing
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .concierge_agent_v2 import concierge_agent, process_chat, ConciergeAgent
    from .deals_agent_runner import deals_agent, start_deals_agent, stop_deals_agent, DealsAgentRunner

__all__ = [
    "concierge_agent",
    "process_chat",
    "ConciergeAgent",
    "deals_agent",
    "start_deals_agent",
    "stop_deals_agent",
    "DealsAgentRunner"
]
