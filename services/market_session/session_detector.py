"""
Session Detector
Handles market session detection and management
"""

import asyncio
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Dict, Any
import pytz
import httpx
from dateutil import parser as date_parser

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.market import (
    MarketStatus,
    MarketHoliday,
    SessionChangeEvent,
    TradingDay,
    TimeSlot
)
from shared.enums.market_session import MarketSession
from shared.utils.redis_client import RedisClient
from shared.utils.logger import get_logger
from shared.events import EventBus, create_day_changed_event, create_session_changed_event

logger = get_logger(__name__)


class SessionDetector:
    """
    Detects and manages market sessions
    """
    
    def __init__(self, redis_client: RedisClient, event_bus: Optional[EventBus] = None):
        self.redis = redis_client
        self.event_bus = event_bus
        self.et_tz = pytz.timezone('America/New_York')
        self.last_session: Optional[MarketSession] = None
        self.last_trading_date: Optional[date] = None
        self.session_change_count = 0
        
        # Parse market hours from settings
        self.pre_market_start = self._parse_time(settings.pre_market_start)
        self.market_open = self._parse_time(settings.market_open)
        self.market_close = self._parse_time(settings.market_close)
        self.post_market_end = self._parse_time(settings.post_market_end)
    
    @staticmethod
    def _parse_time(time_str: str) -> time:
        """Parse time string (HH:MM) to time object"""
        hour, minute = map(int, time_str.split(':'))
        return time(hour, minute)
    
    async def initialize(self) -> None:
        """Initialize the detector"""
        logger.info("Initializing SessionDetector")
        
        # Load current session from Redis or detect
        await self._load_or_detect_session()
        
        # Load holidays from Polygon if available
        await self._load_holidays_from_polygon()
        
        logger.info(
            "SessionDetector initialized",
            session=self.last_session,
            trading_date=self.last_trading_date
        )
    
    async def _load_or_detect_session(self) -> None:
        """Load session from Redis or detect current session"""
        # Try to load from Redis
        cached_session = await self.redis.get(f"{settings.key_prefix_market}:session:current")
        
        if cached_session:
            self.last_session = MarketSession(cached_session)
            logger.info("Loaded session from cache", session=self.last_session)
        else:
            # Detect current session
            status = await self._detect_current_session()
            self.last_session = status.current_session
            self.last_trading_date = status.trading_date
            await self._save_session_to_redis(status)
            logger.info("Detected initial session", session=self.last_session)
    
    async def _load_holidays_from_polygon(self) -> None:
        """Load market holidays from Polygon API"""
        try:
            url = "https://api.polygon.io/v1/marketstatus/upcoming"
            params = {"apiKey": settings.polygon_api_key}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Parse holidays (Polygon returns dict with numeric keys)
                    from shared.models.polygon import PolygonMarketHolidaysResponse
                    holidays_response = PolygonMarketHolidaysResponse.from_dict_response(data)
                    
                    # Cache holidays in Redis
                    await self._cache_holidays(holidays_response.holidays)
                    
                    logger.info(
                        "Loaded holidays from Polygon",
                        count=len(holidays_response.holidays)
                    )
                else:
                    logger.warning("Failed to load holidays from Polygon", status=response.status_code)
        
        except Exception as e:
            logger.error("Error loading holidays from Polygon", error=str(e))
    
    async def _cache_holidays(self, holidays: List) -> None:
        """Cache holidays in Redis for fast lookup"""
        try:
            # Store as hash: holiday_date -> holiday_data
            for holiday in holidays:
                # Only cache NYSE/NASDAQ
                if holiday.exchange in ["NYSE", "NASDAQ"]:
                    key = f"{settings.key_prefix_market}:holiday:{holiday.date}:{holiday.exchange}"
                    await self.redis.set(
                        key,
                        {
                            "name": holiday.name,
                            "status": holiday.status,
                            "exchange": holiday.exchange,
                            "open": holiday.open,
                            "close": holiday.close
                        },
                        ttl=86400 * 30  # Cache for 30 days
                    )
            
            logger.info(f"Cached {len(holidays)} holidays in Redis")
        
        except Exception as e:
            logger.error("Error caching holidays", error=str(e))
    
    def _get_current_et_time(self) -> datetime:
        """Get current time in ET timezone"""
        return datetime.now(self.et_tz)
    
    async def _is_trading_day(self, target_date: date) -> bool:
        """
        Check if a date is a trading day
        
        Rules:
        - Not Saturday or Sunday
        - Not a market holiday
        """
        # Check if weekend
        if target_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            return False
        
        # Check if holiday
        is_holiday = await self._check_if_holiday(target_date)
        if is_holiday:
            return False
        
        return True
    
    async def _check_if_holiday(self, target_date: date) -> bool:
        """Check if date is a market holiday"""
        try:
            date_str = target_date.strftime('%Y-%m-%d')
            
            # Check both NYSE and NASDAQ
            for exchange in ["NYSE", "NASDAQ"]:
                key = f"{settings.key_prefix_market}:holiday:{date_str}:{exchange}"
                holiday_data = await self.redis.get(key, deserialize=True)
                
                if holiday_data and holiday_data.get("status") == "closed":
                    return True
            
            return False
        
        except Exception as e:
            logger.error("Error checking holiday", date=target_date, error=str(e))
            return False
    
    async def _check_if_early_close(self, target_date: date) -> tuple[bool, Optional[str]]:
        """
        Check if date has early close
        
        Returns:
            (is_early_close, close_time_iso)
        """
        try:
            date_str = target_date.strftime('%Y-%m-%d')
            
            # Check both NYSE and NASDAQ
            for exchange in ["NYSE", "NASDAQ"]:
                key = f"{settings.key_prefix_market}:holiday:{date_str}:{exchange}"
                holiday_data = await self.redis.get(key, deserialize=True)
                
                if holiday_data and holiday_data.get("status") == "early-close":
                    return (True, holiday_data.get("close"))
            
            return (False, None)
        
        except Exception as e:
            logger.error("Error checking early close", date=target_date, error=str(e))
            return (False, None)
    
    async def _detect_current_session(self) -> MarketStatus:
        """
        Detect current market session using Polygon's real-time API
        Falls back to time-based calculation if API fails
        """
        now_et = self._get_current_et_time()
        current_date = now_et.date()
        current_time = now_et.time()
        
        # Try to get real-time status from Polygon first
        polygon_status = await self._fetch_polygon_market_status()
        
        if polygon_status:
            # Use Polygon's real-time status (source of truth)
            current_session = polygon_status.get_market_session_enum()
            logger.debug(
                "Using Polygon real-time status",
                session=current_session,
                polygon_market=polygon_status.market,
                early_hours=polygon_status.earlyHours,
                after_hours=polygon_status.afterHours
            )
        else:
            # Fallback to time-based calculation
            logger.warning("Polygon API unavailable, using time-based detection")
            is_trading = await self._is_trading_day(current_date)
            
            if not is_trading:
                current_session = MarketSession.CLOSED
            else:
                # Check for early close
                is_early, early_close_time = await self._check_if_early_close(current_date)
                market_close = self.market_close
                if is_early and early_close_time:
                    try:
                        close_dt = date_parser.parse(early_close_time)
                        market_close = close_dt.time()
                    except:
                        pass
                
                current_session = self._get_session_from_time(current_time, market_close)
        
        # Get additional context
        is_trading = await self._is_trading_day(current_date)
        is_holiday = await self._check_if_holiday(current_date)
        is_early, early_close_time = await self._check_if_early_close(current_date)
        
        # Adjust market close for early close
        market_close = self.market_close
        if is_early and early_close_time:
            try:
                close_dt = date_parser.parse(early_close_time)
                market_close = close_dt.time()
            except:
                pass
        
        # Calculate next session
        next_session, next_time = self._get_next_session(current_session, current_time, market_close)
        seconds_until_next = self._seconds_until(current_time, next_time) if next_time else None
        
        return MarketStatus(
            timestamp=now_et,
            current_session=current_session,
            trading_date=current_date,
            is_trading_day=is_trading,
            is_holiday=is_holiday,
            pre_market_start=self.pre_market_start,
            market_open=self.market_open,
            market_close=market_close,
            post_market_end=self.post_market_end,
            next_session=next_session,
            next_session_time=next_time,
            seconds_until_next_session=seconds_until_next
        )
    
    async def _fetch_polygon_market_status(self):
        """
        Fetch real-time market status from Polygon
        Endpoint: GET /v1/marketstatus/now
        
        Returns:
            PolygonMarketStatus or None if failed
        """
        try:
            url = "https://api.polygon.io/v1/marketstatus/now"
            params = {"apiKey": settings.polygon_api_key}
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    from shared.models.polygon import PolygonMarketStatus as PolyStatus
                    return PolyStatus(**data)
                else:
                    logger.warning(
                        "Failed to fetch Polygon market status",
                        status_code=response.status_code
                    )
                    return None
        
        except Exception as e:
            logger.error("Error fetching Polygon market status", error=str(e))
            return None
    
    def _get_session_from_time(
        self, 
        current_time: time,
        market_close: Optional[time] = None
    ) -> MarketSession:
        """Determine session from time"""
        close_time = market_close or self.market_close
        
        if current_time < self.pre_market_start:
            return MarketSession.CLOSED
        elif current_time < self.market_open:
            return MarketSession.PRE_MARKET
        elif current_time < close_time:
            return MarketSession.MARKET_OPEN
        elif current_time < self.post_market_end:
            return MarketSession.POST_MARKET
        else:
            return MarketSession.CLOSED
    
    def _get_next_session(
        self,
        current_session: MarketSession,
        current_time: time,
        market_close: Optional[time] = None
    ) -> tuple[Optional[MarketSession], Optional[time]]:
        """Get next session and its start time"""
        close_time = market_close or self.market_close
        
        if current_session == MarketSession.CLOSED:
            if current_time < self.pre_market_start:
                return (MarketSession.PRE_MARKET, self.pre_market_start)
            else:
                # After post-market, next is pre-market tomorrow
                return (MarketSession.PRE_MARKET, self.pre_market_start)
        elif current_session == MarketSession.PRE_MARKET:
            return (MarketSession.MARKET_OPEN, self.market_open)
        elif current_session == MarketSession.MARKET_OPEN:
            return (MarketSession.POST_MARKET, close_time)
        elif current_session == MarketSession.POST_MARKET:
            return (MarketSession.CLOSED, self.post_market_end)
        
        return (None, None)
    
    @staticmethod
    def _seconds_until(current_time: time, target_time: time) -> int:
        """Calculate seconds until target time"""
        current_seconds = current_time.hour * 3600 + current_time.minute * 60 + current_time.second
        target_seconds = target_time.hour * 3600 + target_time.minute * 60 + target_time.second
        
        if target_seconds > current_seconds:
            return target_seconds - current_seconds
        else:
            # Target is tomorrow
            return (86400 - current_seconds) + target_seconds
    
    async def check_and_update_session(self, force: bool = False) -> Optional[SessionChangeEvent]:
        """
        Check if session has changed and emit event if so
        
        Args:
            force: Force update even if session hasn't changed
        
        Returns:
            SessionChangeEvent if session changed, None otherwise
        """
        status = await self._detect_current_session()
        
        # Check if session changed
        session_changed = self.last_session != status.current_session
        
        # Check if day changed
        day_changed = self.last_trading_date != status.trading_date
        
        if session_changed or day_changed or force:
            event = SessionChangeEvent(
                from_session=self.last_session or status.current_session,
                to_session=status.current_session,
                timestamp=status.timestamp,
                trading_date=status.trading_date,
                is_new_day=day_changed,
                should_clear_buffers=day_changed,
                should_reload_universe=day_changed or (
                    status.current_session == MarketSession.PRE_MARKET and
                    self.last_session == MarketSession.CLOSED
                ),
                should_reset_rvol=day_changed or (
                    status.current_session == MarketSession.PRE_MARKET
                )
            )
            
            # Update state
            self.last_session = status.current_session
            self.last_trading_date = status.trading_date
            self.session_change_count += 1
            
            # Save to Redis
            await self._save_session_to_redis(status)
            
            # Publish event
            await self._publish_session_change_event(event)
            
            logger.info(
                "Session changed",
                from_session=event.from_session,
                to_session=event.to_session,
                is_new_day=event.is_new_day
            )
            
            return event
        
        return None
    
    async def _save_session_to_redis(self, status: MarketStatus) -> None:
        """Save current session to Redis"""
        await self.redis.set(
            f"{settings.key_prefix_market}:session:current",
            status.current_session.value,
            ttl=settings.cache_ttl_market_status
        )
        
        await self.redis.set(
            f"{settings.key_prefix_market}:session:status",
            status.model_dump(mode='json'),
            ttl=settings.cache_ttl_market_status
        )
    
    async def _publish_session_change_event(self, event: SessionChangeEvent) -> None:
        """Publish session change event to Redis"""
        # Publish to channel (legacy)
        await self.redis.publish(
            "events:session_change",
            event.model_dump(mode='json')
        )
        
        # Add to stream (legacy)
        await self.redis.xadd(
            settings.stream_session_events,
            event.model_dump(mode='json'),
            maxlen=1000
        )
        
        # NUEVO: Publicar eventos al Event Bus
        if self.event_bus:
            # Evento de cambio de sesión
            session_event = create_session_changed_event(
                new_session=event.to_session.value,
                previous_session=event.from_session.value,
                trading_date=str(event.trading_date)
            )
            await self.event_bus.publish(session_event)
            
            # Evento de cambio de día (si aplica)
            if event.is_new_day:
                day_event = create_day_changed_event(
                    new_date=str(event.trading_date),
                    previous_date=str(event.trading_date - timedelta(days=1)),
                    session=event.to_session.value
                )
                await self.event_bus.publish(day_event)
        
        logger.info("Published session change event", event=event.model_dump())
    
    async def get_current_status(self) -> MarketStatus:
        """Get current market status"""
        return await self._detect_current_session()
    
    async def get_trading_day(self, target_date: date) -> TradingDay:
        """Get trading day information"""
        is_trading = self._is_trading_day(target_date)
        
        return TradingDay(
            date=target_date,
            is_trading_day=is_trading,
            is_holiday=False,  # TODO: Check holidays
            is_early_close=False,
            pre_market_start=self.pre_market_start,
            market_open=self.market_open,
            market_close=self.market_close,
            post_market_end=self.post_market_end
        )
    
    async def get_upcoming_holidays(self, days_ahead: int = 30) -> List[MarketHoliday]:
        """Get upcoming market holidays from cache"""
        holidays = []
        
        try:
            today = date.today()
            
            # Check next N days
            for i in range(days_ahead):
                check_date = today + timedelta(days=i)
                date_str = check_date.strftime('%Y-%m-%d')
                
                # Check NYSE (primary exchange)
                key = f"{settings.key_prefix_market}:holiday:{date_str}:NYSE"
                holiday_data = await self.redis.get(key, deserialize=True)
                
                if holiday_data:
                    from shared.models.market import MarketHoliday
                    
                    is_early = holiday_data.get("status") == "early-close"
                    early_time = None
                    
                    if is_early and holiday_data.get("close"):
                        try:
                            close_dt = date_parser.parse(holiday_data["close"])
                            early_time = close_dt.time()
                        except:
                            pass
                    
                    holiday = MarketHoliday(
                        date=check_date,
                        name=holiday_data.get("name", ""),
                        exchange="NYSE",
                        is_early_close=is_early,
                        early_close_time=early_time
                    )
                    holidays.append(holiday)
            
            return holidays
        
        except Exception as e:
            logger.error("Error getting upcoming holidays", error=str(e))
            return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        status = await self.get_current_status()
        
        return {
            "current_session": status.current_session,
            "trading_date": status.trading_date.isoformat(),
            "is_trading_day": status.is_trading_day,
            "session_changes": self.session_change_count,
            "uptime_seconds": 0,  # TODO: Track uptime
        }

