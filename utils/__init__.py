"""
Utilities Module
Helper functions for AI service
"""

from .ai_helpers import (
    auto_tag_deal,
    format_price,
    calculate_savings_percentage,
    truncate_text,
    extract_city_from_code,
    merge_tags,
    filter_deals_by_tags,
    sort_deals_by_score
)

__all__ = [
    "auto_tag_deal",
    "format_price",
    "calculate_savings_percentage",
    "truncate_text",
    "extract_city_from_code",
    "merge_tags",
    "filter_deals_by_tags",
    "sort_deals_by_score"
]
