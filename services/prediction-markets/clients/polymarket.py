"""
Polymarket API Client
Async HTTP client for Gamma and CLOB APIs
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
import structlog

from config import settings
from models.polymarket import (
    PolymarketEvent,
    PolymarketTag,
    PriceHistory,
    PricePoint,
)


logger = structlog.get_logger(__name__)


class PolymarketClient:
    """
    Async client for Polymarket APIs
    - Gamma API: Event/market discovery and metadata
    - CLOB API: Price data and order books
    """
    
    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._gamma_url = settings.polymarket_gamma_url
        self._clob_url = settings.polymarket_clob_url
        self._timeout = settings.polymarket_timeout
    
    async def connect(self) -> None:
        """Initialize HTTP client"""
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            headers={
                "Accept": "application/json",
                "User-Agent": "Tradeul/1.0"
            }
        )
        logger.info("polymarket_client_connected")
    
    async def disconnect(self) -> None:
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("polymarket_client_disconnected")
    
    @property
    def client(self) -> httpx.AsyncClient:
        if not self._http_client:
            raise RuntimeError("Client not connected. Call connect() first.")
        return self._http_client
    
    # =========================================================================
    # GAMMA API - Events and Markets
    # =========================================================================
    
    async def get_events(
        self,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
        tag_slug: Optional[str] = None,
        order: str = "volume",
        ascending: bool = False,
    ) -> List[PolymarketEvent]:
        """
        Fetch events from Gamma API
        
        Args:
            active: Only active events
            closed: Include closed events
            limit: Max events per request
            offset: Pagination offset
            tag_slug: Filter by tag
            order: Sort field (volume, createdAt, etc.)
            ascending: Sort direction
        
        Returns:
            List of PolymarketEvent objects
        """
        params: Dict[str, Any] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": str(ascending).lower(),
        }
        
        if tag_slug:
            params["tag_slug"] = tag_slug
        
        try:
            response = await self.client.get(
                f"{self._gamma_url}/events",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            events = []
            
            for event_data in data:
                try:
                    event = PolymarketEvent.model_validate(event_data)
                    events.append(event)
                except Exception as e:
                    logger.warning(
                        "event_parse_error",
                        event_id=event_data.get("id"),
                        error=str(e)
                    )
                    continue
            
            logger.debug(
                "gamma_events_fetched",
                count=len(events),
                params=params
            )
            
            return events
            
        except httpx.HTTPStatusError as e:
            logger.error(
                "gamma_api_http_error",
                status_code=e.response.status_code,
                url=str(e.request.url)
            )
            return []
        except Exception as e:
            logger.error("gamma_api_error", error=str(e))
            return []
    
    async def get_events_by_tag(
        self,
        tag_slug: str,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
    ) -> List[PolymarketEvent]:
        """
        Fetch events filtered by a specific tag.
        
        Args:
            tag_slug: Tag slug to filter by
            active: Only active events
            closed: Include closed events
            limit: Max events to fetch
        
        Returns:
            List of PolymarketEvent objects with this tag
        """
        try:
            response = await self.client.get(
                f"{self._gamma_url}/events",
                params={
                    "tag_slug": tag_slug,
                    "active": str(active).lower(),
                    "closed": str(closed).lower(),
                    "limit": limit,
                    "order": "volume",
                    "ascending": "false"
                }
            )
            response.raise_for_status()
            
            data = response.json()
            events = []
            
            for event_data in data:
                try:
                    event = PolymarketEvent.model_validate(event_data)
                    events.append(event)
                except Exception as e:
                    continue
            
            logger.debug("events_fetched_by_tag", tag=tag_slug, count=len(events))
            return events
            
        except Exception as e:
            logger.warning("events_by_tag_error", tag=tag_slug, error=str(e))
            return []

    async def get_all_events(
        self,
        active: bool = True,
        closed: bool = False,
        max_events: int = 500,
    ) -> List[PolymarketEvent]:
        """
        Fetch all events with pagination
        
        Args:
            active: Only active events
            closed: Include closed events
            max_events: Maximum total events to fetch
        
        Returns:
            List of all PolymarketEvent objects
        """
        all_events: List[PolymarketEvent] = []
        offset = 0
        page_size = 100
        
        while len(all_events) < max_events:
            events = await self.get_events(
                active=active,
                closed=closed,
                limit=page_size,
                offset=offset
            )
            
            if not events:
                break
            
            all_events.extend(events)
            offset += page_size
            
            if len(events) < page_size:
                break
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)
        
        logger.info(
            "gamma_all_events_fetched",
            total=len(all_events)
        )
        
        return all_events[:max_events]
    
    async def fetch_events_by_categories(
        self,
        categories: List[str],
        exclude_categories: List[str] = None,
        active: bool = True,
        closed: bool = False,
        max_events: int = 1000,
        events_per_category: int = 100,
    ) -> List[PolymarketEvent]:
        """
        Fetch events by Polymarket's native categories.
        
        Simple approach: use Polymarket's own category slugs directly.
        No LLM needed - categories come from Polymarket frontend.
        
        Args:
            categories: List of Polymarket category slugs to fetch
            exclude_categories: Categories to exclude from results
            active: Only active events
            closed: Include closed events
            max_events: Maximum total events to return
            events_per_category: Max events per category
        
        Returns:
            Deduplicated list of events, sorted by volume
        """
        seen_ids = set()
        all_events: List[PolymarketEvent] = []
        exclude_set = set(exclude_categories or [])
        
        logger.info(
            "fetch_by_categories_started",
            categories=categories,
            exclude=list(exclude_set)
        )
        
        # Fetch from each category concurrently
        semaphore = asyncio.Semaphore(10)
        
        async def fetch_category(category: str) -> tuple:
            async with semaphore:
                events = await self.get_events_by_tag(
                    tag_slug=category,
                    active=active,
                    closed=closed,
                    limit=events_per_category
                )
                return (category, events)
        
        tasks = [fetch_category(cat) for cat in categories]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and deduplicate
        category_counts = {}
        for result in results:
            if isinstance(result, Exception):
                logger.warning("category_fetch_error", error=str(result))
                continue
            
            category, events = result
            category_counts[category] = len(events)
            
            for event in events:
                if event.id not in seen_ids:
                    # Skip if event has excluded category tags
                    event_tags = set(event.get_tag_slugs())
                    if not (event_tags & exclude_set):
                        seen_ids.add(event.id)
                        all_events.append(event)
        
        # Sort by volume
        all_events.sort(key=lambda e: e.volume or 0, reverse=True)
        
        logger.info(
            "fetch_by_categories_completed",
            total_events=len(all_events),
            by_category=category_counts
        )
        
        return all_events[:max_events]
    
    async def get_event_by_slug(self, slug: str) -> Optional[PolymarketEvent]:
        """Fetch single event by slug"""
        try:
            response = await self.client.get(
                f"{self._gamma_url}/events",
                params={"slug": slug}
            )
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                return PolymarketEvent.model_validate(data[0])
            return None
            
        except Exception as e:
            logger.error("gamma_event_fetch_error", slug=slug, error=str(e))
            return None
    
    async def get_tags(self) -> List[PolymarketTag]:
        """Fetch all available tags"""
        try:
            response = await self.client.get(f"{self._gamma_url}/tags")
            response.raise_for_status()
            
            data = response.json()
            tags = []
            
            for tag_data in data:
                try:
                    tag = PolymarketTag.model_validate(tag_data)
                    tags.append(tag)
                except Exception:
                    continue
            
            logger.info("gamma_tags_fetched", count=len(tags))
            return tags
            
        except Exception as e:
            logger.error("gamma_tags_error", error=str(e))
            return []
    
    async def get_series(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetch series (grouped related events)
        
        Returns:
            List of series objects
        """
        try:
            response = await self.client.get(
                f"{self._gamma_url}/series",
                params={"limit": limit, "offset": offset}
            )
            response.raise_for_status()
            
            data = response.json()
            logger.debug("gamma_series_fetched", count=len(data))
            return data
            
        except Exception as e:
            logger.error("gamma_series_error", error=str(e))
            return []
    
    async def get_series_by_id(self, series_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single series by ID"""
        try:
            response = await self.client.get(f"{self._gamma_url}/series/{series_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("gamma_series_by_id_error", series_id=series_id, error=str(e))
            return None
    
    async def get_comments(
        self,
        asset_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch comments for an asset/event
        
        Args:
            asset_id: Optional asset/event ID filter
            limit: Max comments
        
        Returns:
            List of comment objects
        """
        try:
            params: Dict[str, Any] = {"limit": limit}
            if asset_id:
                params["asset"] = asset_id
            
            response = await self.client.get(
                f"{self._gamma_url}/comments",
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            logger.debug("gamma_comments_fetched", count=len(data))
            return data
            
        except Exception as e:
            logger.error("gamma_comments_error", error=str(e))
            return []
    
    async def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single event by ID from Gamma API"""
        try:
            response = await self.client.get(f"{self._gamma_url}/events/{event_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("gamma_event_by_id_error", event_id=event_id, error=str(e))
            return None
    
    # =========================================================================
    # DATA API - User positions, top holders, etc.
    # =========================================================================
    
    async def get_top_holders(
        self,
        market_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Get top holders for a market
        
        Args:
            market_id: Market/condition ID
            limit: Max holders to return
        
        Returns:
            List of holder objects with address and position
        """
        try:
            response = await self.client.get(
                f"{settings.polymarket_data_url}/top-holders",
                params={"market": market_id, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("data_api_top_holders_error", market_id=market_id, error=str(e))
            return []
    
    async def get_live_volume(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get live trading volume for an event
        
        Returns:
            Dict with volume data or None
        """
        try:
            response = await self.client.get(
                f"{settings.polymarket_data_url}/volume",
                params={"event": event_id}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("data_api_live_volume_error", event_id=event_id, error=str(e))
            return None
    
    async def get_open_interest(self) -> Optional[Dict[str, Any]]:
        """Get open interest across all markets"""
        try:
            response = await self.client.get(f"{settings.polymarket_data_url}/open-interest")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("data_api_open_interest_error", error=str(e))
            return None
    
    # =========================================================================
    # CLOB API - Price History
    # =========================================================================
    
    async def get_price_history(
        self,
        token_id: str,
        interval: str = "max",
        fidelity: int = 60,
    ) -> Optional[PriceHistory]:
        """
        Fetch price history for a market token
        
        Args:
            token_id: CLOB token ID
            interval: Time interval (1m, 1h, 6h, 1d, 1w, max)
            fidelity: Resolution in minutes
        
        Returns:
            PriceHistory object or None
        """
        try:
            response = await self.client.get(
                f"{self._clob_url}/prices-history",
                params={
                    "market": token_id,
                    "interval": interval,
                    "fidelity": fidelity
                }
            )
            response.raise_for_status()
            
            data = response.json()
            history_data = data.get("history", [])
            
            if not history_data:
                return None
            
            price_points = []
            for point in history_data:
                try:
                    price_points.append(PricePoint(t=point["t"], p=point["p"]))
                except (KeyError, ValueError):
                    continue
            
            return PriceHistory(history=price_points)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # No history available for this token
                return None
            logger.warning(
                "clob_price_history_error",
                token_id=token_id[:20] + "...",
                status_code=e.response.status_code
            )
            return None
        except Exception as e:
            logger.warning(
                "clob_price_history_error",
                token_id=token_id[:20] + "...",
                error=str(e)
            )
            return None
    
    async def get_price_histories_batch(
        self,
        token_ids: List[str],
        interval: str = "max",
        max_concurrent: int = 10,
    ) -> Dict[str, PriceHistory]:
        """
        Fetch price histories for multiple tokens concurrently
        
        Args:
            token_ids: List of CLOB token IDs
            interval: Time interval
            max_concurrent: Max concurrent requests
        
        Returns:
            Dict mapping token_id to PriceHistory
        """
        results: Dict[str, PriceHistory] = {}
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_one(token_id: str) -> None:
            async with semaphore:
                history = await self.get_price_history(token_id, interval)
                if history:
                    results[token_id] = history
        
        tasks = [fetch_one(tid) for tid in token_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info(
            "clob_batch_histories_fetched",
            requested=len(token_ids),
            fetched=len(results)
        )
        
        return results
    
    async def get_current_price(self, token_id: str) -> Optional[float]:
        """Get current price for a token"""
        try:
            response = await self.client.get(
                f"{self._clob_url}/price",
                params={"token_id": token_id}
            )
            response.raise_for_status()
            
            data = response.json()
            return float(data.get("price", 0))
            
        except Exception as e:
            logger.warning(
                "clob_current_price_error",
                token_id=token_id[:20] + "...",
                error=str(e)
            )
            return None
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> Dict[str, bool]:
        """Check API connectivity"""
        results = {"gamma": False, "clob": False}
        
        try:
            response = await self.client.get(
                f"{self._gamma_url}/events",
                params={"limit": 1}
            )
            results["gamma"] = response.status_code == 200
        except Exception:
            pass
        
        try:
            # CLOB doesn't have a dedicated health endpoint
            # Just check if we can reach it
            response = await self.client.get(f"{self._clob_url}/")
            results["clob"] = response.status_code in [200, 404]
        except Exception:
            pass
        
        return results


# Singleton instance
polymarket_client = PolymarketClient()
