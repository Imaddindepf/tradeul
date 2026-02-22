"""
Event Processor Service
Transforms raw Polymarket data into processed models with calculated metrics.

V3: 100% dynamic - uses Polymarket's native tags directly as categories.
    No hardcoded mappings. LLM decides which tags to fetch, Polymarket decides categories.
"""

from typing import Optional, List, Dict
from datetime import datetime
from collections import defaultdict
import structlog

from models.polymarket import PolymarketEvent, PolymarketMarket, PriceHistory
from models.processed import (
    ProcessedMarket,
    ProcessedEvent,
    CategoryGroup,
    PredictionMarketsResponse,
    MarketSource,
    TagInfo,
)
from config_categories import INCLUDE_CATEGORIES
from clients.polymarket import PolymarketClient


logger = structlog.get_logger(__name__)


class EventProcessor:
    """
    Processes raw Polymarket events into frontend-ready format.
    
    V3: 100% dynamic categorization:
    - Category = first tag with forceShow=True (Polymarket's primary category)
    - Fallback = first tag label
    - NO hardcoded mappings or priority lists
    """
    
    def __init__(self, polymarket_client: PolymarketClient):
        self.client = polymarket_client
    
    # Polymarket's main categories (from their navigation bar)
    # These are stable - Polymarket rarely adds new main categories
    # Tags to exclude from category display (internal/ticker-specific)
    EXCLUDE_TAG_SLUGS = {"hide-from-new", "equities"}

    # Set of configured category slugs for filtering
    CONFIGURED_SLUGS = set(INCLUDE_CATEGORIES)

    def _get_tag_info(self, event: PolymarketEvent) -> tuple:
        """
        Extract meaningful tag slugs and labels from an event.
        Returns (slugs: List[str], labels: List[str])
        Only includes tags that are in our configured categories.
        """
        tags = event.tags or []
        slugs = []
        labels = []
        for tag in tags:
            slug = (tag.slug or "").lower()
            if slug in self.EXCLUDE_TAG_SLUGS:
                continue
            if slug in self.CONFIGURED_SLUGS:
                slugs.append(slug)
                labels.append(tag.label or slug.replace("-", " ").title())
        return slugs, labels

    def _get_category_from_tags(self, event: PolymarketEvent) -> str:
        """
        Get category from Polymarket tags - scalable approach.
        
        Strategy:
        1. Use forceShow=true tag (Polymarket's explicit primary category)
        2. Find first tag matching Polymarket's main categories
        3. Fallback to first tag
        
        This is scalable because Polymarket's main categories are stable.
        """
        tags = event.tags or []
        
        # 1. Use forceShow=true (Polymarket's explicit choice)
        for tag in tags:
            if tag.force_show and tag.label:
                return tag.label
        
        # 2. Find first tag that's a main category
        for tag in tags:
            if tag.slug and tag.slug.lower() in self.MAIN_CATEGORIES:
                return tag.label or tag.slug.capitalize()
        
        # 3. Fallback to first tag
        if tags and tags[0].label:
            return tags[0].label
        
        return "Other"
    
    def _format_date_label(self, dt: Optional[datetime]) -> Optional[str]:
        """Format date as readable label (e.g., 'March 31, 2026')"""
        if not dt:
            return None
        return dt.strftime("%B %d, %Y")
    
    def _extract_date_from_question(self, question: str) -> Optional[str]:
        """Extract date portion from market question"""
        if not question:
            return None
        
        # Common patterns: "by March 31, 2026", "in 2025", "before July"
        import re
        
        # Pattern: "by/before/in Month Day, Year"
        match = re.search(
            r"(?:by|before|in)\s+(\w+\s+\d{1,2},?\s+\d{4})",
            question,
            re.IGNORECASE
        )
        if match:
            return match.group(1)
        
        # Pattern: "by/before end of Year"
        match = re.search(
            r"(?:by|before)?\s*end\s+of\s+(\d{4})",
            question,
            re.IGNORECASE
        )
        if match:
            return f"end of {match.group(1)}"
        
        # Pattern: just year
        match = re.search(r"in\s+(\d{4})\??$", question, re.IGNORECASE)
        if match:
            return match.group(1)
        
        return None
    
    def _calculate_price_changes(
        self,
        current_price: float,
        history: Optional[PriceHistory]
    ) -> Dict[str, Optional[float]]:
        """
        Calculate price changes from history
        
        Returns dict with:
        - change_1d: 1-day change
        - change_5d: 5-day change  
        - change_1m: 1-month change
        - low_30d: 30-day low
        - high_30d: 30-day high
        """
        result = {
            "change_1d": None,
            "change_5d": None,
            "change_1m": None,
            "low_30d": None,
            "high_30d": None,
        }
        
        if not history or not history.history:
            return result
        
        # Get prices at different time points
        price_1d = history.get_price_at_days_ago(1)
        price_5d = history.get_price_at_days_ago(5)
        price_30d = history.get_price_at_days_ago(30)
        
        # Calculate changes (in percentage points, not percent)
        if price_1d is not None:
            result["change_1d"] = round((current_price - price_1d) * 100, 1)
        
        if price_5d is not None:
            result["change_5d"] = round((current_price - price_5d) * 100, 1)
        
        if price_30d is not None:
            result["change_1m"] = round((current_price - price_30d) * 100, 1)
        
        # 30-day range
        min_price = history.get_min_price()
        max_price = history.get_max_price()
        
        if min_price is not None:
            result["low_30d"] = round(min_price * 100, 1)
        
        if max_price is not None:
            result["high_30d"] = round(max_price * 100, 1)
        
        return result
    
    def _process_market(
        self,
        market: PolymarketMarket,
        price_history: Optional[PriceHistory] = None,
    ) -> Optional[ProcessedMarket]:
        """Process a single market into frontend format"""
        
        # Get current probability
        probability = market.get_yes_probability()
        if probability is None:
            return None
        
        # Use API-provided changes if available, otherwise calculate
        changes = {}
        if market.one_day_price_change is not None:
            changes["change_1d"] = round(market.one_day_price_change * 100, 1)
            changes["change_5d"] = (
                round(market.one_week_price_change * 100, 1)
                if market.one_week_price_change else None
            )
            changes["change_1m"] = (
                round(market.one_month_price_change * 100, 1)
                if market.one_month_price_change else None
            )
            changes["low_30d"] = None
            changes["high_30d"] = None
        elif price_history:
            changes = self._calculate_price_changes(probability, price_history)
        else:
            changes = {
                "change_1d": None,
                "change_5d": None,
                "change_1m": None,
                "low_30d": None,
                "high_30d": None,
            }
        
        # Parse volume
        volume = None
        if market.volume:
            try:
                volume = float(market.volume)
            except (ValueError, TypeError):
                pass
        
        # Generate date label
        date_label = self._extract_date_from_question(market.question or "")
        if not date_label and market.end_date:
            date_label = self._format_date_label(market.end_date)
        
        return ProcessedMarket(
            id=market.id,
            question=market.question or "",
            probability=round(probability, 4),
            probability_pct=round(probability * 100, 1),
            change_1d=changes.get("change_1d"),
            change_5d=changes.get("change_5d"),
            change_1m=changes.get("change_1m"),
            low_30d=changes.get("low_30d"),
            high_30d=changes.get("high_30d"),
            volume=volume,
            end_date=market.end_date,
            end_date_label=date_label,
            source=MarketSource.POLYMARKET,
            clob_token_id=market.get_yes_token_id(),
        )
    
    def _process_event(
        self,
        event: PolymarketEvent,
        category: str,
        subcategory: Optional[str],
        relevance_score: float,
        price_histories: Optional[Dict[str, PriceHistory]] = None,
    ) -> Optional[ProcessedEvent]:
        """Process a single event with its markets"""
        
        if not event.markets:
            return None
        
        processed_markets: List[ProcessedMarket] = []
        
        for market in event.markets:
            # Skip closed/inactive markets
            if market.closed:
                continue
            
            # Get price history for this market if available
            history = None
            token_id = market.get_yes_token_id()
            if price_histories and token_id:
                history = price_histories.get(token_id)
            
            processed = self._process_market(market, history)
            if processed:
                processed_markets.append(processed)
        
        if not processed_markets:
            return None
        
        # Sort markets by end date (earliest first)
        # Handle timezone-aware and naive datetimes
        def sort_key(m):
            if m.end_date is None:
                return datetime.max
            # Convert to naive datetime for comparison
            if m.end_date.tzinfo is not None:
                return m.end_date.replace(tzinfo=None)
            return m.end_date
        
        processed_markets.sort(key=sort_key)
        
        return ProcessedEvent(
            id=event.id,
            title=event.title or "",
            slug=event.slug,
            category=category,
            subcategory=subcategory,
            tags=event.get_tag_labels(),
            total_volume=event.volume,
            volume_24h=event.volume_24hr,
            markets=processed_markets,
            relevance_score=relevance_score,
        )
    
    async def process_events(
        self,
        events: List[PolymarketEvent],
        fetch_price_history: bool = True,
        max_history_markets: int = 100,
    ) -> PredictionMarketsResponse:
        """
        Process events into flat list with multi-tag classification.

        V4: Tag-based — each event keeps ALL its tag slugs.
        Frontend filters client-side by tag. No single-category assignment.
        """
        if not events:
            return PredictionMarketsResponse()

        # Collect token IDs for price history
        price_histories: Dict[str, PriceHistory] = {}

        if fetch_price_history:
            token_ids: List[str] = []
            for event in events[:max_history_markets]:
                if event.markets:
                    for market in event.markets[:5]:
                        token_id = market.get_yes_token_id()
                        if token_id:
                            token_ids.append(token_id)

            if token_ids:
                price_histories = await self.client.get_price_histories_batch(
                    token_ids[:max_history_markets],
                    interval="max",
                    max_concurrent=20
                )

        # Process events flat — no single-category assignment
        all_processed: List[ProcessedEvent] = []
        total_markets = 0
        tag_counts: Dict[str, Dict] = {}  # slug -> {label, count, volume}

        for event in events:
            score = (event.volume or 0) / 1_000_000
            tag_slugs, tag_labels = self._get_tag_info(event)

            processed = self._process_event(
                event, None, None, score, price_histories
            )
            if processed:
                processed.tags = tag_slugs
                processed.tag_labels = tag_labels
                all_processed.append(processed)
                total_markets += len(processed.markets)

                # Accumulate tag counts
                ev_vol = event.volume or 0
                for slug, label in zip(tag_slugs, tag_labels):
                    if slug not in tag_counts:
                        tag_counts[slug] = {"label": label, "count": 0, "volume": 0.0}
                    tag_counts[slug]["count"] += 1
                    tag_counts[slug]["volume"] += ev_vol

        # Sort events by volume desc
        all_processed.sort(key=lambda e: e.total_volume or 0, reverse=True)

        # Build TagInfo list sorted by count desc
        tag_list: List[TagInfo] = []
        for slug, info in sorted(tag_counts.items(), key=lambda x: x[1]["count"], reverse=True):
            tag_list.append(TagInfo(
                slug=slug,
                label=info["label"],
                count=info["count"],
                total_volume=info["volume"],
            ))

        logger.info(
            "events_processed_v4",
            total_events=len(all_processed),
            total_markets=total_markets,
            tags=len(tag_list),
            top_tags=[t.slug for t in tag_list[:5]]
        )

        return PredictionMarketsResponse(
            events=all_processed,
            tags=tag_list,
            total_events=len(all_processed),
            total_markets=total_markets,
        )

