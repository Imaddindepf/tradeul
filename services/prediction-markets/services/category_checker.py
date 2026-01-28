"""
Polymarket Category Checker

Periodically checks Polymarket's frontend for new/removed categories.
Alerts if there are categories we might want to add.

Runs daily - no LLM needed, just scrapes their frontend.
"""

import httpx
import re
from typing import List, Dict, Set
from datetime import datetime
import structlog

from config_categories import INCLUDE_CATEGORIES, EXCLUDE_CATEGORIES

logger = structlog.get_logger(__name__)


async def fetch_polymarket_categories() -> List[Dict[str, str]]:
    """
    Fetch current categories from Polymarket's frontend.
    
    Returns list of {slug, label} dicts.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get("https://polymarket.com")
            response.raise_for_status()
            
            # Extract categories from HTML
            # Pattern: "slug":"category-slug","label":"Category Label"
            pattern = r'"slug":"([^"]+)","label":"([^"]+)"'
            matches = re.findall(pattern, response.text)
            
            categories = []
            seen = set()
            for slug, label in matches:
                if slug not in seen and slug != "all":
                    categories.append({"slug": slug, "label": label})
                    seen.add(slug)
            
            return categories
            
    except Exception as e:
        logger.error("fetch_categories_error", error=str(e))
        return []


async def check_categories() -> Dict:
    """
    Compare Polymarket's current categories with our config.
    
    Returns:
        {
            "polymarket_categories": [...],  # All from Polymarket
            "our_categories": [...],          # What we're using
            "new_categories": [...],          # New ones we might want
            "missing_from_polymarket": [...], # Ones we have that don't exist
            "checked_at": "..."
        }
    """
    polymarket_cats = await fetch_polymarket_categories()
    polymarket_slugs = {c["slug"] for c in polymarket_cats}
    
    our_include = set(INCLUDE_CATEGORIES)
    our_exclude = set(EXCLUDE_CATEGORIES)
    our_all = our_include | our_exclude
    
    # Find new categories from Polymarket that we don't have
    new_categories = []
    for cat in polymarket_cats:
        if cat["slug"] not in our_all:
            new_categories.append(cat)
    
    # Find categories we have that don't exist in Polymarket
    missing = [slug for slug in our_all if slug not in polymarket_slugs]
    
    result = {
        "polymarket_categories": polymarket_cats,
        "our_include": list(our_include),
        "our_exclude": list(our_exclude),
        "new_categories": new_categories,
        "missing_from_polymarket": missing,
        "checked_at": datetime.utcnow().isoformat(),
    }
    
    # Log alerts
    if new_categories:
        logger.warning(
            "new_polymarket_categories_found",
            count=len(new_categories),
            categories=[c["slug"] for c in new_categories[:10]]
        )
    
    if missing:
        logger.warning(
            "categories_missing_from_polymarket",
            missing=missing
        )
    
    return result


# Categorías que probablemente son de interés financiero (para sugerir)
FINANCIAL_KEYWORDS = [
    "econ", "financ", "fed", "rate", "trade", "tariff", "tax",
    "crypto", "bitcoin", "eth", "defi",
    "elect", "politic", "trump", "biden", "presid",
    "war", "conflict", "militar", "nato", "ukrain", "russia", "china", "iran",
    "tech", "ai", "openai", "apple", "google", "microsoft",
    "ipo", "earning", "stock", "market"
]


async def suggest_categories() -> List[Dict]:
    """
    Suggest new categories that might be of financial interest.
    
    Returns list of {slug, label, reason} for suggested additions.
    """
    result = await check_categories()
    suggestions = []
    
    for cat in result["new_categories"]:
        slug_lower = cat["slug"].lower()
        label_lower = cat["label"].lower()
        
        # Check if matches financial keywords
        for keyword in FINANCIAL_KEYWORDS:
            if keyword in slug_lower or keyword in label_lower:
                suggestions.append({
                    "slug": cat["slug"],
                    "label": cat["label"],
                    "reason": f"Matches keyword: {keyword}"
                })
                break
    
    return suggestions
