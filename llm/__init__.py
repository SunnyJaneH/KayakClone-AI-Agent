# llm/__init__.py
"""
LLM Components Package

Contains LLM-powered components:
- intent_parser: Parse natural language to structured intents
- explainer: Generate "Why this" and "What to watch" explanations
- quote_generator: Generate complete booking quotes
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .intent_parser import intent_parser, IntentParser, ParsedIntent
    from .explainer import explainer, Explainer, generate_explanation
    from .quote_generator import quote_generator, QuoteGenerator, generate_quote

__all__ = [
    "intent_parser",
    "IntentParser",
    "ParsedIntent",
    "explainer",
    "Explainer",
    "generate_explanation",
    "quote_generator",
    "QuoteGenerator",
    "generate_quote"
]
