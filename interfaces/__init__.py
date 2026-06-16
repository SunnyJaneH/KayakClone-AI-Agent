# interfaces/__init__.py
"""
Interfaces Package

Contains data stores and caches:
- session_store: Session state management
- deals_cache: Scored deals cache
- policy_store: Listing policies
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session_store import session_store, SessionStore
    from .deals_cache import deals_cache, DealsCache, Deal, search_deals, get_deals_for_bundle
    from .policy_store import policy_store, PolicyStore, PolicyInfo, answer_policy_question

__all__ = [
    "session_store",
    "SessionStore",
    "deals_cache",
    "DealsCache",
    "Deal",
    "search_deals",
    "get_deals_for_bundle",
    "policy_store",
    "PolicyStore",
    "PolicyInfo",
    "answer_policy_question"
]
