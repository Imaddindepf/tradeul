"""
Filter Engine
Declarative filter system for ScannerTicker.

Supports inverted ranges (min > max) for OR/outside-range logic,
matching Tradeul behavior: min=5, max=-5 → value ≥ 5 OR value ≤ -5.
"""

from typing import Optional, List, Any
from datetime import datetime

import sys
sys.path.append('/app')

from shared.models.scanner import ScannerTicker, FilterConfig, FilterParameters
from shared.enums.market_session import MarketSession
from shared.utils.logger import get_logger

logger = get_logger(__name__)


FILTER_DEFINITIONS = [
    # (param_min_name, param_max_name, ticker_field_name, allow_none)
    # allow_none=True means ticker_value=None passes the filter
    ('min_rvol', 'max_rvol', 'rvol', True),
    ('min_price', 'max_price', 'price', False),
    ('min_spread', 'max_spread', 'spread', False),
    ('min_bid_size', 'max_bid_size', 'bid_size', False),
    ('min_ask_size', 'max_ask_size', 'ask_size', False),
    ('min_distance_from_nbbo', 'max_distance_from_nbbo', 'distance_from_nbbo', False),
    ('min_volume', None, 'volume_today', False),
    ('min_minute_volume', None, 'minute_volume', False),
    ('min_avg_volume_5d', 'max_avg_volume_5d', 'avg_volume_5d', False),
    ('min_avg_volume_10d', 'max_avg_volume_10d', 'avg_volume_10d', False),
    ('min_avg_volume_3m', 'max_avg_volume_3m', 'avg_volume_3m', False),
    ('min_dollar_volume', 'max_dollar_volume', 'dollar_volume', False),
    ('min_volume_today_pct', 'max_volume_today_pct', 'volume_today_pct', False),
    ('min_volume_yesterday_pct', 'max_volume_yesterday_pct', 'volume_yesterday_pct', False),
    ('min_change_percent', 'max_change_percent', 'change_percent', False),
    ('min_change_from_open', 'max_change_from_open', 'change_from_open', False),
    ('min_change_from_open_dollars', 'max_change_from_open_dollars', 'change_from_open_dollars', False),
    ('min_price_from_high', 'max_price_from_high', 'price_from_high', False),
    ('min_price_from_low', 'max_price_from_low', 'price_from_low', False),
    ('min_price_from_intraday_high', 'max_price_from_intraday_high', 'price_from_intraday_high', False),
    ('min_price_from_intraday_low', 'max_price_from_intraday_low', 'price_from_intraday_low', False),
    ('min_market_cap', 'max_market_cap', 'market_cap', False),
    ('min_float', 'max_float', 'free_float', False),
    # Volume window % (Tradeul style)
    ('min_vol_1min_pct', 'max_vol_1min_pct', 'vol_1min_pct', False),
    ('min_vol_5min_pct', 'max_vol_5min_pct', 'vol_5min_pct', False),
    ('min_vol_10min_pct', 'max_vol_10min_pct', 'vol_10min_pct', False),
    ('min_vol_15min_pct', 'max_vol_15min_pct', 'vol_15min_pct', False),
    ('min_vol_30min_pct', 'max_vol_30min_pct', 'vol_30min_pct', False),
    # Price range windows
    ('min_range_2min', 'max_range_2min', 'range_2min', False),
    ('min_range_5min', 'max_range_5min', 'range_5min', False),
    ('min_range_15min', 'max_range_15min', 'range_15min', False),
    ('min_range_30min', 'max_range_30min', 'range_30min', False),
    ('min_range_60min', 'max_range_60min', 'range_60min', False),
    ('min_range_120min', 'max_range_120min', 'range_120min', False),
    ('min_range_2min_pct', 'max_range_2min_pct', 'range_2min_pct', False),
    ('min_range_5min_pct', 'max_range_5min_pct', 'range_5min_pct', False),
    ('min_range_15min_pct', 'max_range_15min_pct', 'range_15min_pct', False),
    ('min_range_30min_pct', 'max_range_30min_pct', 'range_30min_pct', False),
    ('min_range_60min_pct', 'max_range_60min_pct', 'range_60min_pct', False),
    ('min_range_120min_pct', 'max_range_120min_pct', 'range_120min_pct', False),
]


def check_min_max(
    ticker_value: Optional[Any],
    min_value: Optional[Any],
    max_value: Optional[Any],
    allow_none_ticker: bool = False,
) -> bool:
    """
    Check if ticker_value passes a min/max range filter.

    When both bounds are set and min > max, uses OR/outside-range logic
    (Tradeul style): value >= min OR value <= max.
    Otherwise uses standard AND/inside-range: min <= value <= max.
    """
    if min_value is None and max_value is None:
        return True

    if ticker_value is None:
        return allow_none_ticker

    if min_value is not None and max_value is not None and min_value > max_value:
        return ticker_value >= min_value or ticker_value <= max_value

    if min_value is not None and ticker_value < min_value:
        return False
    if max_value is not None and ticker_value > max_value:
        return False
    return True


# Backward-compat alias used by scanner_engine
_check_min_max = check_min_max


def apply_filter(
    ticker: ScannerTicker,
    params: FilterParameters,
    current_session: Optional[MarketSession] = None,
) -> bool:
    """Apply all FilterParameters to a ticker. Returns True if it passes ALL filters."""
    try:
        for min_param, max_param, ticker_field, allow_none in FILTER_DEFINITIONS:
            min_val = getattr(params, min_param, None) if min_param else None
            max_val = getattr(params, max_param, None) if max_param else None
            ticker_val = getattr(ticker, ticker_field, None)

            if not check_min_max(ticker_val, min_val, max_val, allow_none_ticker=allow_none):
                return False

        if params.max_data_age_seconds is not None:
            if ticker.last_trade_timestamp is not None:
                current_time_ns = datetime.now().timestamp() * 1_000_000_000
                age_seconds = (current_time_ns - ticker.last_trade_timestamp) / 1_000_000_000
                if age_seconds > params.max_data_age_seconds:
                    return False
            else:
                return False

        if params.sectors and ticker.sector not in params.sectors:
            return False
        if params.industries and ticker.industry not in params.industries:
            return False
        if params.exchanges and ticker.exchange not in params.exchanges:
            return False

        security_type_filter = getattr(params, 'security_type', None)
        if security_type_filter and isinstance(security_type_filter, str) and security_type_filter.strip():
            if ticker.security_type != security_type_filter.strip():
                return False

        if current_session == MarketSession.POST_MARKET:
            if not check_min_max(
                ticker.postmarket_change_percent,
                params.min_postmarket_change_percent,
                params.max_postmarket_change_percent,
            ):
                return False
            if not check_min_max(
                ticker.postmarket_volume,
                params.min_postmarket_volume,
                params.max_postmarket_volume,
            ):
                return False

        return True

    except Exception as e:
        logger.error("Error applying filter", error=str(e))
        return False


class FilterEngine:
    """
    Declarative filter engine for the Scanner.

    Usage:
        engine = FilterEngine(current_session)
        if engine.passes_filter(ticker, filter_config):
            ...
    """

    def __init__(self, current_session: Optional[MarketSession] = None):
        self.current_session = current_session

    def set_session(self, session: MarketSession) -> None:
        self.current_session = session

    def passes_filter(self, ticker: ScannerTicker, filter_config: FilterConfig) -> bool:
        if not filter_config.enabled:
            return True
        if not filter_config.applies_to_session(self.current_session):
            return True
        return apply_filter(ticker, filter_config.parameters, self.current_session)

    def passes_all_filters(self, ticker: ScannerTicker, filters: List[FilterConfig]) -> bool:
        return all(self.passes_filter(ticker, fc) for fc in filters)
