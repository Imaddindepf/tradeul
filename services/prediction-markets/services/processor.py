"""
Event Processor Service
Transforms raw Polymarket data into processed models with calculated metrics
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
)
from models.categories import DEFAULT_CATEGORIES
from clients.polymarket import PolymarketClient
from services.classifier import CategoryClassifier


logger = structlog.get_logger(__name__)


class EventProcessor:
    """
    Processes raw Polymarket events into frontend-ready format
    - Calculates price changes from history
    - Groups events by category/subcategory
    - Handles market aggregation
    """
    
    def __init__(
        self,
        polymarket_client: PolymarketClient,
        classifier: CategoryClassifier,
    ):
        self.client = polymarket_client
        self.classifier = classifier
    
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
        Process and categorize a list of events
        
        Args:
            events: Raw events from Polymarket
            fetch_price_history: Whether to fetch price histories
            max_history_markets: Max markets to fetch history for
        
        Returns:
            PredictionMarketsResponse with categorized events
        """
        # Filter and classify events
        classified = self.classifier.filter_and_classify_events(events)
        
        if not classified:
            return PredictionMarketsResponse()
        
        # Collect token IDs for price history
        price_histories: Dict[str, PriceHistory] = {}
        
        if fetch_price_history:
            token_ids: List[str] = []
            for event, _, _, _ in classified[:max_history_markets]:
                if event.markets:
                    for market in event.markets[:5]:  # Max 5 markets per event
                        token_id = market.get_yes_token_id()
                        if token_id:
                            token_ids.append(token_id)
            
            if token_ids:
                price_histories = await self.client.get_price_histories_batch(
                    token_ids[:max_history_markets],
                    interval="max",
                    max_concurrent=20
                )
        
        # Process events and group by category
        category_events: Dict[str, Dict[Optional[str], List[ProcessedEvent]]] = defaultdict(
            lambda: defaultdict(list)
        )
        total_markets = 0
        
        for event, category, subcategory, score in classified:
            processed = self._process_event(
                event, category, subcategory, score, price_histories
            )
            if processed:
                category_events[category][subcategory].append(processed)
                total_markets += len(processed.markets)
        
        # Build category groups
        category_groups: List[CategoryGroup] = []
        
        # Sort categories by priority
        category_order = {
            cat.name: cat.priority
            for cat in DEFAULT_CATEGORIES.values()
        }
        category_order["Other"] = 999
        
        sorted_categories = sorted(
            category_events.keys(),
            key=lambda c: category_order.get(c, 100)
        )
        
        for category_name in sorted_categories:
            subcats = category_events[category_name]
            
            for subcategory_name, events_list in subcats.items():
                if not events_list:
                    continue
                
                display_name = category_name
                if subcategory_name:
                    display_name = f"{category_name} - {subcategory_name}"
                
                total_volume = sum(
                    e.total_volume or 0 for e in events_list
                )
                
                category_groups.append(CategoryGroup(
                    category=category_name,
                    subcategory=subcategory_name,
                    display_name=display_name,
                    events=events_list,
                    total_events=len(events_list),
                    total_volume=total_volume,
                ))
        
        logger.info(
            "events_processed",
            total_events=len(classified),
            total_markets=total_markets,
            categories=len(category_groups)
        )
        
        return PredictionMarketsResponse(
            categories=category_groups,
            total_events=len(classified),
            total_markets=total_markets,
        )
