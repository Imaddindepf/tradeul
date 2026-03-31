"""
Pydantic models for Scanner functionality
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator

from ..enums.market_session import MarketSession


# =============================================
# SCANNER TICKER (COMBINED DATA)
# =============================================

class ScannerTicker(BaseModel):
    """
    Combined data structure for a scanned ticker
    Merges real-time data from Polygon with historical/reference data
    """
    # Identity
    symbol: str = Field(..., description="Ticker symbol")
    timestamp: datetime = Field(default_factory=datetime.now, description="Scan timestamp")
    
    # Real-time market data
    price: float = Field(..., description="Current price")
    bid: Optional[float] = Field(None, description="Bid price")
    ask: Optional[float] = Field(None, description="Ask price")
    bid_size: Optional[int] = Field(None, description="Bid size in shares (demand)")
    ask_size: Optional[int] = Field(None, description="Ask size in shares (supply)")
    spread: Optional[float] = Field(None, description="Bid-Ask spread in cents")
    spread_percent: Optional[float] = Field(None, description="Spread as % of mid price")
    bid_ask_ratio: Optional[float] = Field(None, description="Bid/Ask size ratio (>1 = more demand)")
    distance_from_nbbo: Optional[float] = Field(None, description="Distance from inside market as % (0 = tradeable)")
    volume: int = Field(..., description="Current volume")
    volume_today: int = Field(..., description="Total volume today")
    minute_volume: Optional[int] = Field(None, description="Volume in last minute bar (min.v)")
    last_trade_timestamp: Optional[int] = Field(None, description="Last trade timestamp (nanoseconds)")
    
    # OHLC
    open: Optional[float] = Field(None, description="Open price")
    high: Optional[float] = Field(None, description="High price (regular market hours)")
    low: Optional[float] = Field(None, description="Low price (regular market hours)")
    
    # Intraday high/low (incluye pre-market, market hours, post-market)
    intraday_high: Optional[float] = Field(None, description="Intraday high (includes pre/post market)")
    intraday_low: Optional[float] = Field(None, description="Intraday low (includes pre/post market)")
    
    # Previous day reference
    prev_close: Optional[float] = Field(None, description="Previous close")
    prev_volume: Optional[int] = Field(None, description="Previous day volume")
    
    # Changes
    change: Optional[float] = Field(None, description="Price change from prev close")
    change_percent: Optional[float] = Field(None, description="Percentage change")
    
    # Gap metrics (NUEVOS - para categorías GAPPERS correctas)
    gap_percent: Optional[float] = Field(None, description="True gap % = (open - prev_close) / prev_close")
    change_from_open: Optional[float] = Field(None, description="Change from open % = (price - open) / open")
    change_from_open_dollars: Optional[float] = Field(None, description="Change from open $ = price - open")
    
    # Historical/Reference data - Average Daily Volume
    avg_volume_5d: Optional[int] = Field(None, description="5-day average daily volume")
    avg_volume_10d: Optional[int] = Field(None, description="10-day average daily volume")
    avg_volume_3m: Optional[int] = Field(None, description="3-month (~63 trading days) average daily volume")
    avg_volume_30d: Optional[int] = Field(None, description="30-day average volume (legacy)")
    
    # Dollar Volume = price × avg_volume_10d (liquidity metric in $/day)
    dollar_volume: Optional[float] = Field(None, description="Dollar volume (price × avg_volume_10d) in $/day")
    
    # Volume Today/Yesterday as % of avg_volume_10d
    volume_today_pct: Optional[float] = Field(None, description="Volume today as % of avg 10d (e.g. 150 = 150%)")
    volume_yesterday_pct: Optional[float] = Field(None, description="Volume yesterday as % of avg 10d")
    
    # Volume window metrics (volume traded in last N minutes)
    vol_1min: Optional[int] = Field(None, description="Volume traded in last 1 minute")
    vol_5min: Optional[int] = Field(None, description="Volume traded in last 5 minutes")
    vol_10min: Optional[int] = Field(None, description="Volume traded in last 10 minutes")
    vol_15min: Optional[int] = Field(None, description="Volume traded in last 15 minutes")
    vol_30min: Optional[int] = Field(None, description="Volume traded in last 30 minutes")
    
    # Volume window % metrics (vs avg_volume_10d, Trade Ideas style)
    vol_1min_pct: Optional[float] = Field(None, description="Volume 1min as % of expected (100=normal)")
    vol_5min_pct: Optional[float] = Field(None, description="Volume 5min as % of expected (100=normal)")
    vol_10min_pct: Optional[float] = Field(None, description="Volume 10min as % of expected (100=normal)")
    vol_15min_pct: Optional[float] = Field(None, description="Volume 15min as % of expected (100=normal)")
    vol_30min_pct: Optional[float] = Field(None, description="Volume 30min as % of expected (100=normal)")
    
    # Price range window metrics (Trade Ideas: Range2..Range120)
    range_2min: Optional[float] = Field(None, description="High-Low range ($) in last 2 minutes")
    range_5min: Optional[float] = Field(None, description="High-Low range ($) in last 5 minutes")
    range_15min: Optional[float] = Field(None, description="High-Low range ($) in last 15 minutes")
    range_30min: Optional[float] = Field(None, description="High-Low range ($) in last 30 minutes")
    range_60min: Optional[float] = Field(None, description="High-Low range ($) in last 60 minutes")
    range_120min: Optional[float] = Field(None, description="High-Low range ($) in last 120 minutes")
    range_2min_pct: Optional[float] = Field(None, description="2min range as % of ATR")
    range_5min_pct: Optional[float] = Field(None, description="5min range as % of ATR")
    range_15min_pct: Optional[float] = Field(None, description="15min range as % of ATR")
    range_30min_pct: Optional[float] = Field(None, description="30min range as % of ATR")
    range_60min_pct: Optional[float] = Field(None, description="60min range as % of ATR")
    range_120min_pct: Optional[float] = Field(None, description="120min range as % of ATR")
    
    # Price change window metrics (% change in last N minutes - per-second precision)
    chg_1min: Optional[float] = Field(None, description="Price change % in last 1 minute")
    chg_5min: Optional[float] = Field(None, description="Price change % in last 5 minutes")
    chg_10min: Optional[float] = Field(None, description="Price change % in last 10 minutes")
    chg_15min: Optional[float] = Field(None, description="Price change % in last 15 minutes")
    chg_30min: Optional[float] = Field(None, description="Price change % in last 30 minutes")
    
    free_float: Optional[int] = Field(None, description="Free float (shares available for public trading)")
    free_float_percent: Optional[float] = Field(None, description="Free float percentage from Polygon")
    float_rotation: Optional[float] = Field(None, description="Float rotation % = (volume_today / free_float) * 100")
    shares_outstanding: Optional[int] = Field(None, description="Shares outstanding")
    market_cap: Optional[int] = Field(None, description="Market capitalization")
    
    # Fundamental data
    security_type: Optional[str] = Field(None, description="Security type (CS, ETF, PFD, WARRANT)")
    sector: Optional[str] = Field(None, description="Sector")
    industry: Optional[str] = Field(None, description="Industry")
    exchange: Optional[str] = Field(None, description="Exchange")
    
    # Calculated indicators
    rvol: Optional[float] = Field(None, description="Relative volume")
    rvol_slot: Optional[float] = Field(None, description="RVOL for current slot")
    atr: Optional[float] = Field(None, description="Average True Range (14 periods)")
    atr_percent: Optional[float] = Field(None, description="ATR as % of price")
    price_from_high: Optional[float] = Field(None, description="% from day high (regular hours)")
    price_from_low: Optional[float] = Field(None, description="% from day low (regular hours)")
    price_from_intraday_high: Optional[float] = Field(None, description="% from intraday high (includes pre/post market)")
    price_from_intraday_low: Optional[float] = Field(None, description="% from intraday low (includes pre/post market)")
    
    # VWAP
    vwap: Optional[float] = Field(None, description="Volume Weighted Average Price (today)")
    price_vs_vwap: Optional[float] = Field(None, description="% distance from VWAP")
    
    # Pre-Market metrics (capturado al inicio de MARKET_OPEN, 09:30 ET)
    premarket_change_percent: Optional[float] = Field(None, description="% change during pre-market (4AM-9:30AM from prev_close)")
    
    # Post-Market metrics (activos solo durante POST_MARKET session 16:00-20:00 ET)
    postmarket_change_percent: Optional[float] = Field(None, description="% change from regular session close (day.c)")
    postmarket_volume: Optional[int] = Field(None, description="Volume traded in post-market only (min.av - day.v)")
    
    # Trades Anomaly Detection (Z-Score based)
    trades_today: Optional[int] = Field(None, description="Number of transactions today (Polygon day.n)")
    avg_trades_5d: Optional[float] = Field(None, description="Average trades per day (last 5 trading days)")
    trades_z_score: Optional[float] = Field(None, description="Z-Score = (trades_today - avg) / std")
    is_trade_anomaly: Optional[bool] = Field(None, description="True if Z-Score >= 3.0")
    
    # Streaming Technical Indicators (from BarEngine, AM.* 1-min bars, 100% coverage)
    rsi_14: Optional[float] = Field(None, description="RSI(14) on 1-minute bars")
    ema_9: Optional[float] = Field(None, description="EMA(9) on 1-minute closes")
    ema_20: Optional[float] = Field(None, description="EMA(20) on 1-minute closes")
    ema_50: Optional[float] = Field(None, description="EMA(50) on 1-minute closes")
    sma_5: Optional[float] = Field(None, description="SMA(5) on 1-minute closes")
    sma_8: Optional[float] = Field(None, description="SMA(8) on 1-minute closes")
    sma_20: Optional[float] = Field(None, description="SMA(20) on 1-minute closes")
    sma_50: Optional[float] = Field(None, description="SMA(50) on 1-minute closes")
    sma_200: Optional[float] = Field(None, description="SMA(200) on 1-minute closes")
    macd_line: Optional[float] = Field(None, description="MACD line (EMA12 - EMA26)")
    macd_signal: Optional[float] = Field(None, description="MACD signal line (EMA9 of MACD)")
    macd_hist: Optional[float] = Field(None, description="MACD histogram (MACD - Signal)")
    bb_upper: Optional[float] = Field(None, description="Bollinger Band upper (SMA20 + 2*StdDev)")
    bb_mid: Optional[float] = Field(None, description="Bollinger Band middle (SMA20)")
    bb_lower: Optional[float] = Field(None, description="Bollinger Band lower (SMA20 - 2*StdDev)")
    adx_14: Optional[float] = Field(None, description="ADX(14) - Average Directional Index")
    stoch_k: Optional[float] = Field(None, description="Stochastic %K(14,3,3)")
    stoch_d: Optional[float] = Field(None, description="Stochastic %D(14,3,3)")
    chg_60min: Optional[float] = Field(None, description="Price change % in last 60 minutes")
    vol_60min: Optional[int] = Field(None, description="Volume traded in last 60 minutes")
    
    # Daily Indicators (from screener / enriched cache)
    daily_sma_5: Optional[float] = Field(None, description="5-day SMA")
    daily_sma_8: Optional[float] = Field(None, description="8-day SMA")
    daily_sma_10: Optional[float] = Field(None, description="10-day SMA")
    daily_sma_20: Optional[float] = Field(None, description="20-day SMA")
    daily_sma_50: Optional[float] = Field(None, description="50-day SMA")
    daily_sma_200: Optional[float] = Field(None, description="200-day SMA")
    daily_rsi: Optional[float] = Field(None, description="Daily RSI(14)")
    daily_adx_14: Optional[float] = Field(None, description="Daily ADX(14)")
    daily_atr_percent: Optional[float] = Field(None, description="Daily ATR as % of price")
    daily_bb_position: Optional[float] = Field(None, description="Position in daily Bollinger Bands (0-100)")
    
    # 52-Week data
    high_52w: Optional[float] = Field(None, description="52-week high price")
    low_52w: Optional[float] = Field(None, description="52-week low price")
    from_52w_high: Optional[float] = Field(None, description="% distance from 52-week high")
    from_52w_low: Optional[float] = Field(None, description="% distance from 52-week low")
    
    # Multi-day changes (from screener / enriched cache)
    change_1d: Optional[float] = Field(None, description="1-day price change %")
    change_3d: Optional[float] = Field(None, description="3-day price change %")
    change_5d: Optional[float] = Field(None, description="5-day price change %")
    change_10d: Optional[float] = Field(None, description="10-day price change %")
    change_20d: Optional[float] = Field(None, description="20-day price change %")
    
    # Average volumes (extended)
    avg_volume_20d: Optional[int] = Field(None, description="20-day average daily volume")
    prev_day_volume: Optional[int] = Field(None, description="Previous day total volume")
    
    # Distance metrics (% from indicators)
    dist_from_vwap: Optional[float] = Field(None, description="% distance from VWAP")
    dist_sma_5: Optional[float] = Field(None, description="% distance from SMA(5)")
    dist_sma_8: Optional[float] = Field(None, description="% distance from SMA(8)")
    dist_sma_20: Optional[float] = Field(None, description="% distance from SMA(20)")
    dist_sma_50: Optional[float] = Field(None, description="% distance from SMA(50)")
    dist_sma_200: Optional[float] = Field(None, description="% distance from SMA(200)")
    dist_daily_sma_20: Optional[float] = Field(None, description="% distance from daily SMA(20)")
    dist_daily_sma_50: Optional[float] = Field(None, description="% distance from daily SMA(50)")
    
    # Derived / computed fields
    todays_range: Optional[float] = Field(None, description="Today's range (high - low) in $")
    todays_range_pct: Optional[float] = Field(None, description="Today's range as % of price")
    float_turnover: Optional[float] = Field(None, description="Volume / float shares ratio")
    pos_in_range: Optional[float] = Field(None, description="Position in day range (0-100%)")
    below_high: Optional[float] = Field(None, description="$ below day high")
    above_low: Optional[float] = Field(None, description="$ above day low")
    pos_of_open: Optional[float] = Field(None, description="Open position in day range (0-100%)")
    
    # Position in multi-period ranges
    pos_in_5d_range: Optional[float] = Field(None, description="Position in 5-day range (0-100%)")
    pos_in_10d_range: Optional[float] = Field(None, description="Position in 10-day range (0-100%)")
    pos_in_20d_range: Optional[float] = Field(None, description="Position in 20-day range (0-100%)")
    pos_in_3m_range: Optional[float] = Field(None, description="Position in 3-month range (0-100%)")
    pos_in_6m_range: Optional[float] = Field(None, description="Position in 6-month range (0-100%)")
    pos_in_9m_range: Optional[float] = Field(None, description="Position in 9-month range (0-100%)")
    pos_in_52w_range: Optional[float] = Field(None, description="Position in 52-week range (0-100%)")
    pos_in_2y_range: Optional[float] = Field(None, description="Position in 2-year range (0-100%)")
    pos_in_lifetime_range: Optional[float] = Field(None, description="Position in lifetime range (0-100%)")
    pos_in_prev_day_range: Optional[float] = Field(None, description="Position in previous day range (0-100%)")
    pos_in_consolidation: Optional[float] = Field(None, description="Position within consolidation range (0-100%)")
    consolidation_days: Optional[float] = Field(None, description="Number of days in consolidation")
    range_contraction: Optional[float] = Field(None, description="Range contraction ratio")
    lr_divergence_130: Optional[float] = Field(None, description="Linear regression divergence (130 periods)")
    change_prev_day_pct: Optional[float] = Field(None, description="Previous day % change")
    
    # Pre-market range metrics
    premarket_high: Optional[float] = Field(None, description="Pre-market high price")
    premarket_low: Optional[float] = Field(None, description="Pre-market low price")
    below_premarket_high: Optional[float] = Field(None, description="% below pre-market high")
    above_premarket_low: Optional[float] = Field(None, description="% above pre-market low")
    pos_in_premarket_range: Optional[float] = Field(None, description="Position in pre-market range (0-100%)")
    
    # Multi-TF SMA distances
    dist_sma_5_2m: Optional[float] = Field(None, description="% dist from SMA(5) on 2min TF")
    dist_sma_5_5m: Optional[float] = Field(None, description="% dist from SMA(5) on 5min TF")
    dist_sma_5_15m: Optional[float] = Field(None, description="% dist from SMA(5) on 15min TF")
    dist_sma_5_30m: Optional[float] = Field(None, description="% dist from SMA(5) on 30min TF")
    dist_sma_5_60m: Optional[float] = Field(None, description="% dist from SMA(5) on 60min TF")
    dist_sma_8_2m: Optional[float] = Field(None, description="% dist from SMA(8) on 2min TF")
    dist_sma_8_5m: Optional[float] = Field(None, description="% dist from SMA(8) on 5min TF")
    dist_sma_8_15m: Optional[float] = Field(None, description="% dist from SMA(8) on 15min TF")
    dist_sma_8_30m: Optional[float] = Field(None, description="% dist from SMA(8) on 30min TF")
    dist_sma_8_60m: Optional[float] = Field(None, description="% dist from SMA(8) on 60min TF")
    dist_sma_10_2m: Optional[float] = Field(None, description="% dist from SMA(10) on 2min TF")
    dist_sma_10_5m: Optional[float] = Field(None, description="% dist from SMA(10) on 5min TF")
    dist_sma_10_15m: Optional[float] = Field(None, description="% dist from SMA(10) on 15min TF")
    dist_sma_10_30m: Optional[float] = Field(None, description="% dist from SMA(10) on 30min TF")
    dist_sma_10_60m: Optional[float] = Field(None, description="% dist from SMA(10) on 60min TF")
    dist_sma_20_2m: Optional[float] = Field(None, description="% dist from SMA(20) on 2min TF")
    dist_sma_20_5m: Optional[float] = Field(None, description="% dist from SMA(20) on 5min TF")
    dist_sma_20_15m: Optional[float] = Field(None, description="% dist from SMA(20) on 15min TF")
    dist_sma_20_30m: Optional[float] = Field(None, description="% dist from SMA(20) on 30min TF")
    dist_sma_20_60m: Optional[float] = Field(None, description="% dist from SMA(20) on 60min TF")
    dist_sma_130_2m: Optional[float] = Field(None, description="% dist from SMA(130) on 2min TF")
    dist_sma_130_5m: Optional[float] = Field(None, description="% dist from SMA(130) on 5min TF")
    dist_sma_130_10m: Optional[float] = Field(None, description="% dist from SMA(130) on 10min TF")
    dist_sma_130_15m: Optional[float] = Field(None, description="% dist from SMA(130) on 15min TF")
    dist_sma_130_30m: Optional[float] = Field(None, description="% dist from SMA(130) on 30min TF")
    dist_sma_130_60m: Optional[float] = Field(None, description="% dist from SMA(130) on 60min TF")
    dist_sma_200_2m: Optional[float] = Field(None, description="% dist from SMA(200) on 2min TF")
    dist_sma_200_5m: Optional[float] = Field(None, description="% dist from SMA(200) on 5min TF")
    dist_sma_200_10m: Optional[float] = Field(None, description="% dist from SMA(200) on 10min TF")
    dist_sma_200_15m: Optional[float] = Field(None, description="% dist from SMA(200) on 15min TF")
    dist_sma_200_30m: Optional[float] = Field(None, description="% dist from SMA(200) on 30min TF")
    dist_sma_200_60m: Optional[float] = Field(None, description="% dist from SMA(200) on 60min TF")
    
    # SMA cross metrics
    sma_8_vs_20_2m: Optional[float] = Field(None, description="SMA(8) vs SMA(20) on 2min TF")
    sma_8_vs_20_5m: Optional[float] = Field(None, description="SMA(8) vs SMA(20) on 5min TF")
    sma_8_vs_20_15m: Optional[float] = Field(None, description="SMA(8) vs SMA(20) on 15min TF")
    sma_8_vs_20_60m: Optional[float] = Field(None, description="SMA(8) vs SMA(20) on 60min TF")
    sma_20_vs_200_2m: Optional[float] = Field(None, description="SMA(20) vs SMA(200) on 2min TF")
    sma_20_vs_200_5m: Optional[float] = Field(None, description="SMA(20) vs SMA(200) on 5min TF")
    sma_20_vs_200_15m: Optional[float] = Field(None, description="SMA(20) vs SMA(200) on 15min TF")
    sma_20_vs_200_60m: Optional[float] = Field(None, description="SMA(20) vs SMA(200) on 60min TF")
    
    # Extended daily SMA distances
    dist_daily_sma_5: Optional[float] = Field(None, description="% dist from daily SMA(5)")
    dist_daily_sma_8: Optional[float] = Field(None, description="% dist from daily SMA(8)")
    dist_daily_sma_10: Optional[float] = Field(None, description="% dist from daily SMA(10)")
    dist_daily_sma_200: Optional[float] = Field(None, description="% dist from daily SMA(200)")
    dist_daily_sma_5_dollars: Optional[float] = Field(None, description="$ dist from daily SMA(5)")
    dist_daily_sma_8_dollars: Optional[float] = Field(None, description="$ dist from daily SMA(8)")
    dist_daily_sma_10_dollars: Optional[float] = Field(None, description="$ dist from daily SMA(10)")
    dist_daily_sma_20_dollars: Optional[float] = Field(None, description="$ dist from daily SMA(20)")
    dist_daily_sma_50_dollars: Optional[float] = Field(None, description="$ dist from daily SMA(50)")
    dist_daily_sma_200_dollars: Optional[float] = Field(None, description="$ dist from daily SMA(200)")
    
    # Extended changes and ranges
    change_1y: Optional[float] = Field(None, description="1-year price change %")
    change_1y_dollars: Optional[float] = Field(None, description="1-year price change $")
    change_ytd: Optional[float] = Field(None, description="Year-to-date price change %")
    change_ytd_dollars: Optional[float] = Field(None, description="Year-to-date price change $")
    change_5d_dollars: Optional[float] = Field(None, description="5-day price change $")
    change_10d_dollars: Optional[float] = Field(None, description="10-day price change $")
    change_20d_dollars: Optional[float] = Field(None, description="20-day price change $")
    range_5d_pct: Optional[float] = Field(None, description="5-day range as % of price")
    range_10d_pct: Optional[float] = Field(None, description="10-day range as % of price")
    range_20d_pct: Optional[float] = Field(None, description="20-day range as % of price")
    range_5d: Optional[float] = Field(None, description="5-day range in $")
    range_10d: Optional[float] = Field(None, description="10-day range in $")
    range_20d: Optional[float] = Field(None, description="20-day range in $")
    
    # Misc derived
    yearly_std_dev: Optional[float] = Field(None, description="Yearly standard deviation")
    consecutive_days_up: Optional[float] = Field(None, description="Consecutive days up/down")
    plus_di_minus_di: Optional[float] = Field(None, description="DI+ minus DI- spread")
    gap_dollars: Optional[float] = Field(None, description="Gap in dollars")
    gap_ratio: Optional[float] = Field(None, description="Gap ratio")
    change_from_close: Optional[float] = Field(None, description="% change from close")
    change_from_close_ratio: Optional[float] = Field(None, description="Change from close ratio")
    change_from_open_ratio: Optional[float] = Field(None, description="Change from open ratio")
    change_from_open_weighted: Optional[float] = Field(None, description="Weighted change from open")
    postmarket_change_dollars: Optional[float] = Field(None, description="Post-market change in dollars")
    decimal: Optional[float] = Field(None, description="Decimal part of price")
    bb_std_dev: Optional[float] = Field(None, description="Bollinger Band standard deviation")
    
    # Multi-TF position in range & BB
    pos_in_range_5m: Optional[float] = Field(None, description="Position in 5min range")
    pos_in_range_15m: Optional[float] = Field(None, description="Position in 15min range")
    pos_in_range_30m: Optional[float] = Field(None, description="Position in 30min range")
    pos_in_range_60m: Optional[float] = Field(None, description="Position in 60min range")
    bb_position_5m: Optional[float] = Field(None, description="BB position on 5min TF")
    bb_position_15m: Optional[float] = Field(None, description="BB position on 15min TF")
    bb_position_60m: Optional[float] = Field(None, description="BB position on 60min TF")
    bb_position_1m: Optional[float] = Field(None, description="BB position on 1min TF")
    
    # Multi-TF RSI
    rsi_14_2m: Optional[float] = Field(None, description="RSI(14) on 2min TF")
    rsi_14_5m: Optional[float] = Field(None, description="RSI(14) on 5min TF")
    rsi_14_15m: Optional[float] = Field(None, description="RSI(14) on 15min TF")
    rsi_14_60m: Optional[float] = Field(None, description="RSI(14) on 60min TF")
    
    # Multi-TF consecutive candles
    chg_2min: Optional[float] = Field(None, description="Price change % in last 2 minutes")
    chg_120min: Optional[float] = Field(None, description="Price change % in last 120 minutes")
    consecutive_candles: Optional[int] = Field(None, description="Consecutive candles (1min)")
    consecutive_candles_2m: Optional[int] = Field(None, description="Consecutive candles (2min)")
    consecutive_candles_5m: Optional[int] = Field(None, description="Consecutive candles (5min)")
    consecutive_candles_10m: Optional[int] = Field(None, description="Consecutive candles (10min)")
    consecutive_candles_15m: Optional[int] = Field(None, description="Consecutive candles (15min)")
    consecutive_candles_30m: Optional[int] = Field(None, description="Consecutive candles (30min)")
    consecutive_candles_60m: Optional[int] = Field(None, description="Consecutive candles (60min)")
    
    # Pivot distances
    dist_pivot: Optional[float] = Field(None, description="% dist from pivot point")
    dist_pivot_r1: Optional[float] = Field(None, description="% dist from R1")
    dist_pivot_s1: Optional[float] = Field(None, description="% dist from S1")
    dist_pivot_r2: Optional[float] = Field(None, description="% dist from R2")
    dist_pivot_s2: Optional[float] = Field(None, description="% dist from S2")
    
    # Session context
    session: MarketSession = Field(..., description="Current market session")
    
    # Scoring
    score: float = Field(0.0, description="Composite score")
    rank: Optional[int] = Field(None, description="Rank in results")
    
    # Metadata
    filters_matched: List[str] = Field(default_factory=list, description="Matched filter names")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @validator('change', always=True)
    def calculate_change(cls, v, values):
        """Auto-calculate change if not provided"""
        if v is None and 'price' in values and 'prev_close' in values:
            if values['prev_close']:
                return values['price'] - values['prev_close']
        return v
    
    @validator('change_percent', always=True)
    def calculate_change_percent(cls, v, values):
        """Auto-calculate change percent if not provided"""
        if v is None and 'price' in values and 'prev_close' in values:
            if values['prev_close'] and values['prev_close'] != 0:
                return ((values['price'] - values['prev_close']) / values['prev_close']) * 100
        return v
    
    @validator('spread', always=True)
    def calculate_spread(cls, v, values):
        """
        Auto-calculate spread in CENTS
        displays spread in cents: 50.00 = $0.50
        """
        if v is None and 'bid' in values and 'ask' in values:
            bid = values.get('bid')
            ask = values.get('ask')
            if bid and ask and bid > 0 and ask > 0:
                # Convert to cents: $0.05 spread → 5.00 cents
                return (ask - bid) * 100
        return v
    
    @validator('spread_percent', always=True)
    def calculate_spread_percent(cls, v, values):
        """Auto-calculate spread as percentage of mid price"""
        if v is None and 'bid' in values and 'ask' in values:
            bid = values.get('bid')
            ask = values.get('ask')
            if bid and ask and bid > 0 and ask > 0:
                mid_price = (bid + ask) / 2
                spread = ask - bid
                return (spread / mid_price) * 100
        return v
    
    @validator('rvol', always=True)
    def calculate_rvol(cls, v, values):
        """
        Auto-calculate RVOL simple si no está provisto
        
        NOTA: Este es un cálculo SIMPLIFICADO para screening inicial rápido.
        El cálculo preciso por slots se hace en el Analytics Service.
        
        Pipeline de dos fases:
        1. Scanner usa RVOL simple para reducir 11k → 1000 tickers
        2. Analytics calcula RVOL preciso por slots para los 1000 filtrados
        
        Este enfoque es:
        - ✅ Escalable: No calculamos slots para 11k tickers
        - ✅ Rápido: Screening inicial veloz
        - ✅ Preciso: RVOL detallado donde importa
        """
        if v is None and 'volume_today' in values and 'avg_volume_30d' in values:
            if values['avg_volume_30d'] and values['avg_volume_30d'] > 0:
                # RVOL simple = volumen total hoy / promedio 30 días
                # (se refinará por el Analytics Service usando slots)
                return values['volume_today'] / values['avg_volume_30d']
        return v
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.model_dump()
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================
# SCANNER RESULT (OUTPUT)
# =============================================

class ScannerResult(BaseModel):
    """
    Scanner result set
    Contains filtered tickers and metadata
    """
    timestamp: datetime = Field(default_factory=datetime.now)
    session: MarketSession
    total_universe_size: int = Field(..., description="Total tickers scanned")
    filtered_count: int = Field(..., description="Number of tickers passing filters")
    tickers: List[ScannerTicker] = Field(..., description="Filtered tickers")
    filters_applied: List[str] = Field(..., description="Names of applied filters")
    scan_duration_ms: Optional[float] = Field(None, description="Scan duration in ms")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================
# FILTER CONFIGURATION
# =============================================

class FilterParameters(BaseModel):
    """Base parameters for filters"""
    # RVOL filters
    min_rvol: Optional[float] = Field(None, ge=0, description="Minimum RVOL")
    max_rvol: Optional[float] = Field(None, ge=0, description="Maximum RVOL")
    
    # Price filters
    min_price: Optional[float] = Field(None, ge=0, description="Minimum price")
    max_price: Optional[float] = Field(None, ge=0, description="Maximum price")
    
    # Spread filters (in CENTS, 50.00 = $0.50)
    min_spread: Optional[float] = Field(None, ge=0, description="Minimum spread in cents")
    max_spread: Optional[float] = Field(None, ge=0, description="Maximum spread in cents")
    
    # Bid/Ask size filters (in shares)
    min_bid_size: Optional[int] = Field(None, ge=0, description="Minimum bid size in shares")
    max_bid_size: Optional[int] = Field(None, ge=0, description="Maximum bid size in shares")
    min_ask_size: Optional[int] = Field(None, ge=0, description="Minimum ask size in shares")
    max_ask_size: Optional[int] = Field(None, ge=0, description="Maximum ask size in shares")
    
    # Distance from Inside Market (NBBO)
    min_distance_from_nbbo: Optional[float] = Field(None, ge=0, description="Min distance from NBBO as %")
    max_distance_from_nbbo: Optional[float] = Field(None, ge=0, description="Max distance from NBBO as % (0 = at bid/ask)")
    
    # Volume filters
    min_volume: Optional[int] = Field(None, ge=0, description="Minimum volume")
    min_volume_today: Optional[int] = Field(None, ge=0, description="Minimum volume today")
    min_minute_volume: Optional[int] = Field(None, ge=0, description="Minimum volume in last minute (min.v)")
    
    # Average Daily Volume filters
    min_avg_volume_5d: Optional[int] = Field(None, ge=0, description="Minimum 5-day average volume")
    max_avg_volume_5d: Optional[int] = Field(None, ge=0, description="Maximum 5-day average volume")
    min_avg_volume_10d: Optional[int] = Field(None, ge=0, description="Minimum 10-day average volume")
    max_avg_volume_10d: Optional[int] = Field(None, ge=0, description="Maximum 10-day average volume")
    min_avg_volume_3m: Optional[int] = Field(None, ge=0, description="Minimum 3-month average volume")
    max_avg_volume_3m: Optional[int] = Field(None, ge=0, description="Maximum 3-month average volume")
    
    # Dollar Volume filters (price × avg_volume_10d)
    min_dollar_volume: Optional[float] = Field(None, ge=0, description="Minimum dollar volume ($/day)")
    max_dollar_volume: Optional[float] = Field(None, ge=0, description="Maximum dollar volume ($/day)")
    
    # Volume Today/Yesterday % filters (volume as % of avg_volume_10d)
    min_volume_today_pct: Optional[float] = Field(None, ge=0, description="Min volume today % (e.g. 100 = avg)")
    max_volume_today_pct: Optional[float] = Field(None, ge=0, description="Max volume today %")
    min_volume_yesterday_pct: Optional[float] = Field(None, ge=0, description="Min volume yesterday %")
    max_volume_yesterday_pct: Optional[float] = Field(None, ge=0, description="Max volume yesterday %")
    
    # Volume window filters (volume in last N minutes)
    min_vol_1min: Optional[int] = Field(None, ge=0, description="Min volume in last 1 minute")
    max_vol_1min: Optional[int] = Field(None, ge=0, description="Max volume in last 1 minute")
    min_vol_5min: Optional[int] = Field(None, ge=0, description="Min volume in last 5 minutes")
    max_vol_5min: Optional[int] = Field(None, ge=0, description="Max volume in last 5 minutes")
    min_vol_10min: Optional[int] = Field(None, ge=0, description="Min volume in last 10 minutes")
    max_vol_10min: Optional[int] = Field(None, ge=0, description="Max volume in last 10 minutes")
    min_vol_15min: Optional[int] = Field(None, ge=0, description="Min volume in last 15 minutes")
    max_vol_15min: Optional[int] = Field(None, ge=0, description="Max volume in last 15 minutes")
    min_vol_30min: Optional[int] = Field(None, ge=0, description="Min volume in last 30 minutes")
    max_vol_30min: Optional[int] = Field(None, ge=0, description="Max volume in last 30 minutes")
    
    # Volume window % filters (vs avg_volume_10d, Trade Ideas style)
    min_vol_1min_pct: Optional[float] = Field(None, ge=0, description="Min volume 1min %")
    max_vol_1min_pct: Optional[float] = Field(None, ge=0, description="Max volume 1min %")
    min_vol_5min_pct: Optional[float] = Field(None, ge=0, description="Min volume 5min %")
    max_vol_5min_pct: Optional[float] = Field(None, ge=0, description="Max volume 5min %")
    min_vol_10min_pct: Optional[float] = Field(None, ge=0, description="Min volume 10min %")
    max_vol_10min_pct: Optional[float] = Field(None, ge=0, description="Max volume 10min %")
    min_vol_15min_pct: Optional[float] = Field(None, ge=0, description="Min volume 15min %")
    max_vol_15min_pct: Optional[float] = Field(None, ge=0, description="Max volume 15min %")
    min_vol_30min_pct: Optional[float] = Field(None, ge=0, description="Min volume 30min %")
    max_vol_30min_pct: Optional[float] = Field(None, ge=0, description="Max volume 30min %")
    
    # Price range window filters (Trade Ideas: Range2..Range120)
    min_range_2min: Optional[float] = Field(None, description="Min 2min range ($)")
    max_range_2min: Optional[float] = Field(None, description="Max 2min range ($)")
    min_range_5min: Optional[float] = Field(None, description="Min 5min range ($)")
    max_range_5min: Optional[float] = Field(None, description="Max 5min range ($)")
    min_range_15min: Optional[float] = Field(None, description="Min 15min range ($)")
    max_range_15min: Optional[float] = Field(None, description="Max 15min range ($)")
    min_range_30min: Optional[float] = Field(None, description="Min 30min range ($)")
    max_range_30min: Optional[float] = Field(None, description="Max 30min range ($)")
    min_range_60min: Optional[float] = Field(None, description="Min 60min range ($)")
    max_range_60min: Optional[float] = Field(None, description="Max 60min range ($)")
    min_range_120min: Optional[float] = Field(None, description="Min 120min range ($)")
    max_range_120min: Optional[float] = Field(None, description="Max 120min range ($)")
    min_range_2min_pct: Optional[float] = Field(None, description="Min 2min range % of ATR")
    max_range_2min_pct: Optional[float] = Field(None, description="Max 2min range % of ATR")
    min_range_5min_pct: Optional[float] = Field(None, description="Min 5min range % of ATR")
    max_range_5min_pct: Optional[float] = Field(None, description="Max 5min range % of ATR")
    min_range_15min_pct: Optional[float] = Field(None, description="Min 15min range % of ATR")
    max_range_15min_pct: Optional[float] = Field(None, description="Max 15min range % of ATR")
    min_range_30min_pct: Optional[float] = Field(None, description="Min 30min range % of ATR")
    max_range_30min_pct: Optional[float] = Field(None, description="Max 30min range % of ATR")
    min_range_60min_pct: Optional[float] = Field(None, description="Min 60min range % of ATR")
    max_range_60min_pct: Optional[float] = Field(None, description="Max 60min range % of ATR")
    min_range_120min_pct: Optional[float] = Field(None, description="Min 120min range % of ATR")
    max_range_120min_pct: Optional[float] = Field(None, description="Max 120min range % of ATR")
    
    # Price change window filters (% change in last N minutes)
    min_chg_1min: Optional[float] = Field(None, description="Min % change in last 1 minute")
    max_chg_1min: Optional[float] = Field(None, description="Max % change in last 1 minute")
    min_chg_5min: Optional[float] = Field(None, description="Min % change in last 5 minutes")
    max_chg_5min: Optional[float] = Field(None, description="Max % change in last 5 minutes")
    min_chg_10min: Optional[float] = Field(None, description="Min % change in last 10 minutes")
    max_chg_10min: Optional[float] = Field(None, description="Max % change in last 10 minutes")
    min_chg_15min: Optional[float] = Field(None, description="Min % change in last 15 minutes")
    max_chg_15min: Optional[float] = Field(None, description="Max % change in last 15 minutes")
    min_chg_30min: Optional[float] = Field(None, description="Min % change in last 30 minutes")
    max_chg_30min: Optional[float] = Field(None, description="Max % change in last 30 minutes")
    
    # Data freshness filters
    max_data_age_seconds: Optional[int] = Field(None, ge=0, description="Max age of last trade in seconds")
    
    # Change filters
    min_change_percent: Optional[float] = Field(None, description="Minimum % change")
    max_change_percent: Optional[float] = Field(None, description="Maximum % change")
    
    # Market cap filters
    min_market_cap: Optional[int] = Field(None, ge=0, description="Minimum market cap")
    max_market_cap: Optional[int] = Field(None, ge=0, description="Maximum market cap")
    
    # Float filters (applies to free_float field)
    min_float: Optional[int] = Field(None, ge=0, description="Minimum float shares")
    max_float: Optional[int] = Field(None, ge=0, description="Maximum float shares")
    
    # Sector/Industry filters
    sectors: Optional[List[str]] = Field(None, description="Allowed sectors")
    industries: Optional[List[str]] = Field(None, description="Allowed industries")
    exchanges: Optional[List[str]] = Field(None, description="Allowed exchanges")
    
    # Advanced price distance filters
    min_price_from_high: Optional[float] = Field(None, description="Min % from day high")
    max_price_from_high: Optional[float] = Field(None, description="Max % from day high")
    min_price_from_low: Optional[float] = Field(None, description="Min % from day low")
    max_price_from_low: Optional[float] = Field(None, description="Max % from day low")
    min_price_from_intraday_high: Optional[float] = Field(None, description="Min % from intraday high")
    max_price_from_intraday_high: Optional[float] = Field(None, description="Max % from intraday high")
    min_price_from_intraday_low: Optional[float] = Field(None, description="Min % from intraday low")
    max_price_from_intraday_low: Optional[float] = Field(None, description="Max % from intraday low")

    # Change from open filters
    min_change_from_open: Optional[float] = Field(None, description="Min change from open %")
    max_change_from_open: Optional[float] = Field(None, description="Max change from open %")
    min_change_from_open_dollars: Optional[float] = Field(None, description="Min change from open $")
    max_change_from_open_dollars: Optional[float] = Field(None, description="Max change from open $")

    # Post-Market filters (only active during POST_MARKET session)
    min_postmarket_change_percent: Optional[float] = Field(None, description="Min post-market % change from close")
    max_postmarket_change_percent: Optional[float] = Field(None, description="Max post-market % change from close")
    min_postmarket_volume: Optional[int] = Field(None, ge=0, description="Min post-market volume in shares")
    max_postmarket_volume: Optional[int] = Field(None, ge=0, description="Max post-market volume in shares")
    
    # Position in multi-period ranges
    min_pos_in_5d_range: Optional[float] = Field(None, description="Min position in 5-day range")
    max_pos_in_5d_range: Optional[float] = Field(None, description="Max position in 5-day range")
    min_pos_in_10d_range: Optional[float] = Field(None, description="Min position in 10-day range")
    max_pos_in_10d_range: Optional[float] = Field(None, description="Max position in 10-day range")
    min_pos_in_20d_range: Optional[float] = Field(None, description="Min position in 20-day range")
    max_pos_in_20d_range: Optional[float] = Field(None, description="Max position in 20-day range")
    min_pos_in_3m_range: Optional[float] = Field(None, description="Min position in 3-month range")
    max_pos_in_3m_range: Optional[float] = Field(None, description="Max position in 3-month range")
    min_pos_in_6m_range: Optional[float] = Field(None, description="Min position in 6-month range")
    max_pos_in_6m_range: Optional[float] = Field(None, description="Max position in 6-month range")
    min_pos_in_9m_range: Optional[float] = Field(None, description="Min position in 9-month range")
    max_pos_in_9m_range: Optional[float] = Field(None, description="Max position in 9-month range")
    min_pos_in_52w_range: Optional[float] = Field(None, description="Min position in 52-week range")
    max_pos_in_52w_range: Optional[float] = Field(None, description="Max position in 52-week range")
    min_pos_in_2y_range: Optional[float] = Field(None, description="Min position in 2-year range")
    max_pos_in_2y_range: Optional[float] = Field(None, description="Max position in 2-year range")
    min_pos_in_lifetime_range: Optional[float] = Field(None, description="Min position in lifetime range")
    max_pos_in_lifetime_range: Optional[float] = Field(None, description="Max position in lifetime range")
    min_pos_in_prev_day_range: Optional[float] = Field(None, description="Min position in prev day range")
    max_pos_in_prev_day_range: Optional[float] = Field(None, description="Max position in prev day range")
    min_pos_in_consolidation: Optional[float] = Field(None, description="Min position in consolidation")
    max_pos_in_consolidation: Optional[float] = Field(None, description="Max position in consolidation")
    min_consolidation_days: Optional[float] = Field(None, description="Min consolidation days")
    max_consolidation_days: Optional[float] = Field(None, description="Max consolidation days")
    min_range_contraction: Optional[float] = Field(None, description="Min range contraction")
    max_range_contraction: Optional[float] = Field(None, description="Max range contraction")
    min_lr_divergence_130: Optional[float] = Field(None, description="Min LR divergence 130")
    max_lr_divergence_130: Optional[float] = Field(None, description="Max LR divergence 130")
    min_change_prev_day_pct: Optional[float] = Field(None, description="Min prev day change %")
    max_change_prev_day_pct: Optional[float] = Field(None, description="Max prev day change %")
    
    # Pre-market range
    min_premarket_high: Optional[float] = Field(None, description="Min pre-market high")
    max_premarket_high: Optional[float] = Field(None, description="Max pre-market high")
    min_premarket_low: Optional[float] = Field(None, description="Min pre-market low")
    max_premarket_low: Optional[float] = Field(None, description="Max pre-market low")
    min_below_premarket_high: Optional[float] = Field(None, description="Min % below pre-market high")
    max_below_premarket_high: Optional[float] = Field(None, description="Max % below pre-market high")
    min_above_premarket_low: Optional[float] = Field(None, description="Min % above pre-market low")
    max_above_premarket_low: Optional[float] = Field(None, description="Max % above pre-market low")
    min_pos_in_premarket_range: Optional[float] = Field(None, description="Min position in pre-market range")
    max_pos_in_premarket_range: Optional[float] = Field(None, description="Max position in pre-market range")
    
    # Multi-TF SMA distances
    min_dist_sma_5_2m: Optional[float] = Field(None, description="Min % dist SMA(5) 2min")
    max_dist_sma_5_2m: Optional[float] = Field(None, description="Max % dist SMA(5) 2min")
    min_dist_sma_5_5m: Optional[float] = Field(None, description="Min % dist SMA(5) 5min")
    max_dist_sma_5_5m: Optional[float] = Field(None, description="Max % dist SMA(5) 5min")
    min_dist_sma_5_15m: Optional[float] = Field(None, description="Min % dist SMA(5) 15min")
    max_dist_sma_5_15m: Optional[float] = Field(None, description="Max % dist SMA(5) 15min")
    min_dist_sma_5_30m: Optional[float] = Field(None, description="Min % dist SMA(5) 30min")
    max_dist_sma_5_30m: Optional[float] = Field(None, description="Max % dist SMA(5) 30min")
    min_dist_sma_5_60m: Optional[float] = Field(None, description="Min % dist SMA(5) 60min")
    max_dist_sma_5_60m: Optional[float] = Field(None, description="Max % dist SMA(5) 60min")
    min_dist_sma_8_2m: Optional[float] = Field(None, description="Min % dist SMA(8) 2min")
    max_dist_sma_8_2m: Optional[float] = Field(None, description="Max % dist SMA(8) 2min")
    min_dist_sma_8_5m: Optional[float] = Field(None, description="Min % dist SMA(8) 5min")
    max_dist_sma_8_5m: Optional[float] = Field(None, description="Max % dist SMA(8) 5min")
    min_dist_sma_8_15m: Optional[float] = Field(None, description="Min % dist SMA(8) 15min")
    max_dist_sma_8_15m: Optional[float] = Field(None, description="Max % dist SMA(8) 15min")
    min_dist_sma_8_30m: Optional[float] = Field(None, description="Min % dist SMA(8) 30min")
    max_dist_sma_8_30m: Optional[float] = Field(None, description="Max % dist SMA(8) 30min")
    min_dist_sma_8_60m: Optional[float] = Field(None, description="Min % dist SMA(8) 60min")
    max_dist_sma_8_60m: Optional[float] = Field(None, description="Max % dist SMA(8) 60min")
    min_dist_sma_10_2m: Optional[float] = Field(None, description="Min % dist SMA(10) 2min")
    max_dist_sma_10_2m: Optional[float] = Field(None, description="Max % dist SMA(10) 2min")
    min_dist_sma_10_5m: Optional[float] = Field(None, description="Min % dist SMA(10) 5min")
    max_dist_sma_10_5m: Optional[float] = Field(None, description="Max % dist SMA(10) 5min")
    min_dist_sma_10_15m: Optional[float] = Field(None, description="Min % dist SMA(10) 15min")
    max_dist_sma_10_15m: Optional[float] = Field(None, description="Max % dist SMA(10) 15min")
    min_dist_sma_10_30m: Optional[float] = Field(None, description="Min % dist SMA(10) 30min")
    max_dist_sma_10_30m: Optional[float] = Field(None, description="Max % dist SMA(10) 30min")
    min_dist_sma_10_60m: Optional[float] = Field(None, description="Min % dist SMA(10) 60min")
    max_dist_sma_10_60m: Optional[float] = Field(None, description="Max % dist SMA(10) 60min")
    min_dist_sma_20_2m: Optional[float] = Field(None, description="Min % dist SMA(20) 2min")
    max_dist_sma_20_2m: Optional[float] = Field(None, description="Max % dist SMA(20) 2min")
    min_dist_sma_20_5m: Optional[float] = Field(None, description="Min % dist SMA(20) 5min")
    max_dist_sma_20_5m: Optional[float] = Field(None, description="Max % dist SMA(20) 5min")
    min_dist_sma_20_15m: Optional[float] = Field(None, description="Min % dist SMA(20) 15min")
    max_dist_sma_20_15m: Optional[float] = Field(None, description="Max % dist SMA(20) 15min")
    min_dist_sma_20_30m: Optional[float] = Field(None, description="Min % dist SMA(20) 30min")
    max_dist_sma_20_30m: Optional[float] = Field(None, description="Max % dist SMA(20) 30min")
    min_dist_sma_20_60m: Optional[float] = Field(None, description="Min % dist SMA(20) 60min")
    max_dist_sma_20_60m: Optional[float] = Field(None, description="Max % dist SMA(20) 60min")
    min_dist_sma_130_2m: Optional[float] = Field(None, description="Min % dist SMA(130) 2min")
    max_dist_sma_130_2m: Optional[float] = Field(None, description="Max % dist SMA(130) 2min")
    min_dist_sma_130_5m: Optional[float] = Field(None, description="Min % dist SMA(130) 5min")
    max_dist_sma_130_5m: Optional[float] = Field(None, description="Max % dist SMA(130) 5min")
    min_dist_sma_130_10m: Optional[float] = Field(None, description="Min % dist SMA(130) 10min")
    max_dist_sma_130_10m: Optional[float] = Field(None, description="Max % dist SMA(130) 10min")
    min_dist_sma_130_15m: Optional[float] = Field(None, description="Min % dist SMA(130) 15min")
    max_dist_sma_130_15m: Optional[float] = Field(None, description="Max % dist SMA(130) 15min")
    min_dist_sma_130_30m: Optional[float] = Field(None, description="Min % dist SMA(130) 30min")
    max_dist_sma_130_30m: Optional[float] = Field(None, description="Max % dist SMA(130) 30min")
    min_dist_sma_130_60m: Optional[float] = Field(None, description="Min % dist SMA(130) 60min")
    max_dist_sma_130_60m: Optional[float] = Field(None, description="Max % dist SMA(130) 60min")
    min_dist_sma_200_2m: Optional[float] = Field(None, description="Min % dist SMA(200) 2min")
    max_dist_sma_200_2m: Optional[float] = Field(None, description="Max % dist SMA(200) 2min")
    min_dist_sma_200_5m: Optional[float] = Field(None, description="Min % dist SMA(200) 5min")
    max_dist_sma_200_5m: Optional[float] = Field(None, description="Max % dist SMA(200) 5min")
    min_dist_sma_200_10m: Optional[float] = Field(None, description="Min % dist SMA(200) 10min")
    max_dist_sma_200_10m: Optional[float] = Field(None, description="Max % dist SMA(200) 10min")
    min_dist_sma_200_15m: Optional[float] = Field(None, description="Min % dist SMA(200) 15min")
    max_dist_sma_200_15m: Optional[float] = Field(None, description="Max % dist SMA(200) 15min")
    min_dist_sma_200_30m: Optional[float] = Field(None, description="Min % dist SMA(200) 30min")
    max_dist_sma_200_30m: Optional[float] = Field(None, description="Max % dist SMA(200) 30min")
    min_dist_sma_200_60m: Optional[float] = Field(None, description="Min % dist SMA(200) 60min")
    max_dist_sma_200_60m: Optional[float] = Field(None, description="Max % dist SMA(200) 60min")
    
    # SMA cross
    min_sma_8_vs_20_2m: Optional[float] = Field(None, description="Min SMA(8) vs SMA(20) 2min")
    max_sma_8_vs_20_2m: Optional[float] = Field(None, description="Max SMA(8) vs SMA(20) 2min")
    min_sma_8_vs_20_5m: Optional[float] = Field(None, description="Min SMA(8) vs SMA(20) 5min")
    max_sma_8_vs_20_5m: Optional[float] = Field(None, description="Max SMA(8) vs SMA(20) 5min")
    min_sma_8_vs_20_15m: Optional[float] = Field(None, description="Min SMA(8) vs SMA(20) 15min")
    max_sma_8_vs_20_15m: Optional[float] = Field(None, description="Max SMA(8) vs SMA(20) 15min")
    min_sma_8_vs_20_60m: Optional[float] = Field(None, description="Min SMA(8) vs SMA(20) 60min")
    max_sma_8_vs_20_60m: Optional[float] = Field(None, description="Max SMA(8) vs SMA(20) 60min")
    min_sma_20_vs_200_2m: Optional[float] = Field(None, description="Min SMA(20) vs SMA(200) 2min")
    max_sma_20_vs_200_2m: Optional[float] = Field(None, description="Max SMA(20) vs SMA(200) 2min")
    min_sma_20_vs_200_5m: Optional[float] = Field(None, description="Min SMA(20) vs SMA(200) 5min")
    max_sma_20_vs_200_5m: Optional[float] = Field(None, description="Max SMA(20) vs SMA(200) 5min")
    min_sma_20_vs_200_15m: Optional[float] = Field(None, description="Min SMA(20) vs SMA(200) 15min")
    max_sma_20_vs_200_15m: Optional[float] = Field(None, description="Max SMA(20) vs SMA(200) 15min")
    min_sma_20_vs_200_60m: Optional[float] = Field(None, description="Min SMA(20) vs SMA(200) 60min")
    max_sma_20_vs_200_60m: Optional[float] = Field(None, description="Max SMA(20) vs SMA(200) 60min")
    
    # Extended daily SMA distances
    min_dist_daily_sma_5: Optional[float] = Field(None, description="Min % dist daily SMA(5)")
    max_dist_daily_sma_5: Optional[float] = Field(None, description="Max % dist daily SMA(5)")
    min_dist_daily_sma_8: Optional[float] = Field(None, description="Min % dist daily SMA(8)")
    max_dist_daily_sma_8: Optional[float] = Field(None, description="Max % dist daily SMA(8)")
    min_dist_daily_sma_10: Optional[float] = Field(None, description="Min % dist daily SMA(10)")
    max_dist_daily_sma_10: Optional[float] = Field(None, description="Max % dist daily SMA(10)")
    min_dist_daily_sma_200: Optional[float] = Field(None, description="Min % dist daily SMA(200)")
    max_dist_daily_sma_200: Optional[float] = Field(None, description="Max % dist daily SMA(200)")
    min_dist_daily_sma_5_dollars: Optional[float] = Field(None, description="Min $ dist daily SMA(5)")
    max_dist_daily_sma_5_dollars: Optional[float] = Field(None, description="Max $ dist daily SMA(5)")
    min_dist_daily_sma_8_dollars: Optional[float] = Field(None, description="Min $ dist daily SMA(8)")
    max_dist_daily_sma_8_dollars: Optional[float] = Field(None, description="Max $ dist daily SMA(8)")
    min_dist_daily_sma_10_dollars: Optional[float] = Field(None, description="Min $ dist daily SMA(10)")
    max_dist_daily_sma_10_dollars: Optional[float] = Field(None, description="Max $ dist daily SMA(10)")
    min_dist_daily_sma_20_dollars: Optional[float] = Field(None, description="Min $ dist daily SMA(20)")
    max_dist_daily_sma_20_dollars: Optional[float] = Field(None, description="Max $ dist daily SMA(20)")
    min_dist_daily_sma_50_dollars: Optional[float] = Field(None, description="Min $ dist daily SMA(50)")
    max_dist_daily_sma_50_dollars: Optional[float] = Field(None, description="Max $ dist daily SMA(50)")
    min_dist_daily_sma_200_dollars: Optional[float] = Field(None, description="Min $ dist daily SMA(200)")
    max_dist_daily_sma_200_dollars: Optional[float] = Field(None, description="Max $ dist daily SMA(200)")
    
    # Extended changes
    min_change_1y: Optional[float] = Field(None, description="Min 1-year change %")
    max_change_1y: Optional[float] = Field(None, description="Max 1-year change %")
    min_change_1y_dollars: Optional[float] = Field(None, description="Min 1-year change $")
    max_change_1y_dollars: Optional[float] = Field(None, description="Max 1-year change $")
    min_change_ytd: Optional[float] = Field(None, description="Min YTD change %")
    max_change_ytd: Optional[float] = Field(None, description="Max YTD change %")
    min_change_ytd_dollars: Optional[float] = Field(None, description="Min YTD change $")
    max_change_ytd_dollars: Optional[float] = Field(None, description="Max YTD change $")
    min_change_5d_dollars: Optional[float] = Field(None, description="Min 5-day change $")
    max_change_5d_dollars: Optional[float] = Field(None, description="Max 5-day change $")
    min_change_10d_dollars: Optional[float] = Field(None, description="Min 10-day change $")
    max_change_10d_dollars: Optional[float] = Field(None, description="Max 10-day change $")
    min_change_20d_dollars: Optional[float] = Field(None, description="Min 20-day change $")
    max_change_20d_dollars: Optional[float] = Field(None, description="Max 20-day change $")
    min_range_5d_pct: Optional[float] = Field(None, description="Min 5-day range %")
    max_range_5d_pct: Optional[float] = Field(None, description="Max 5-day range %")
    min_range_10d_pct: Optional[float] = Field(None, description="Min 10-day range %")
    max_range_10d_pct: Optional[float] = Field(None, description="Max 10-day range %")
    min_range_20d_pct: Optional[float] = Field(None, description="Min 20-day range %")
    max_range_20d_pct: Optional[float] = Field(None, description="Max 20-day range %")
    min_range_5d: Optional[float] = Field(None, description="Min 5-day range $")
    max_range_5d: Optional[float] = Field(None, description="Max 5-day range $")
    min_range_10d: Optional[float] = Field(None, description="Min 10-day range $")
    max_range_10d: Optional[float] = Field(None, description="Max 10-day range $")
    min_range_20d: Optional[float] = Field(None, description="Min 20-day range $")
    max_range_20d: Optional[float] = Field(None, description="Max 20-day range $")
    
    # Misc derived
    min_yearly_std_dev: Optional[float] = Field(None, description="Min yearly std dev")
    max_yearly_std_dev: Optional[float] = Field(None, description="Max yearly std dev")
    min_consecutive_days_up: Optional[float] = Field(None, description="Min consecutive days up")
    max_consecutive_days_up: Optional[float] = Field(None, description="Max consecutive days up")
    min_plus_di_minus_di: Optional[float] = Field(None, description="Min DI+ minus DI-")
    max_plus_di_minus_di: Optional[float] = Field(None, description="Max DI+ minus DI-")
    min_gap_dollars: Optional[float] = Field(None, description="Min gap $")
    max_gap_dollars: Optional[float] = Field(None, description="Max gap $")
    min_gap_ratio: Optional[float] = Field(None, description="Min gap ratio")
    max_gap_ratio: Optional[float] = Field(None, description="Max gap ratio")
    min_change_from_close: Optional[float] = Field(None, description="Min change from close %")
    max_change_from_close: Optional[float] = Field(None, description="Max change from close %")
    min_change_from_open_weighted: Optional[float] = Field(None, description="Min weighted change from open")
    max_change_from_open_weighted: Optional[float] = Field(None, description="Max weighted change from open")
    min_bb_std_dev: Optional[float] = Field(None, description="Min BB std dev")
    max_bb_std_dev: Optional[float] = Field(None, description="Max BB std dev")
    
    # Multi-TF position in range & BB
    min_pos_in_range_5m: Optional[float] = Field(None, description="Min position in 5min range")
    max_pos_in_range_5m: Optional[float] = Field(None, description="Max position in 5min range")
    min_pos_in_range_15m: Optional[float] = Field(None, description="Min position in 15min range")
    max_pos_in_range_15m: Optional[float] = Field(None, description="Max position in 15min range")
    min_pos_in_range_30m: Optional[float] = Field(None, description="Min position in 30min range")
    max_pos_in_range_30m: Optional[float] = Field(None, description="Max position in 30min range")
    min_pos_in_range_60m: Optional[float] = Field(None, description="Min position in 60min range")
    max_pos_in_range_60m: Optional[float] = Field(None, description="Max position in 60min range")
    min_bb_position_5m: Optional[float] = Field(None, description="Min BB position 5min")
    max_bb_position_5m: Optional[float] = Field(None, description="Max BB position 5min")
    min_bb_position_15m: Optional[float] = Field(None, description="Min BB position 15min")
    max_bb_position_15m: Optional[float] = Field(None, description="Max BB position 15min")
    min_bb_position_60m: Optional[float] = Field(None, description="Min BB position 60min")
    max_bb_position_60m: Optional[float] = Field(None, description="Max BB position 60min")
    min_bb_position_1m: Optional[float] = Field(None, description="Min BB position 1min")
    max_bb_position_1m: Optional[float] = Field(None, description="Max BB position 1min")
    
    # Multi-TF RSI
    min_rsi_14_2m: Optional[float] = Field(None, description="Min RSI(14) 2min")
    max_rsi_14_2m: Optional[float] = Field(None, description="Max RSI(14) 2min")
    min_rsi_14_5m: Optional[float] = Field(None, description="Min RSI(14) 5min")
    max_rsi_14_5m: Optional[float] = Field(None, description="Max RSI(14) 5min")
    min_rsi_14_15m: Optional[float] = Field(None, description="Min RSI(14) 15min")
    max_rsi_14_15m: Optional[float] = Field(None, description="Max RSI(14) 15min")
    min_rsi_14_60m: Optional[float] = Field(None, description="Min RSI(14) 60min")
    max_rsi_14_60m: Optional[float] = Field(None, description="Max RSI(14) 60min")
    
    # Time window changes (extended)
    min_chg_2min: Optional[float] = Field(None, description="Min % change 2min")
    max_chg_2min: Optional[float] = Field(None, description="Max % change 2min")
    min_chg_120min: Optional[float] = Field(None, description="Min % change 120min")
    max_chg_120min: Optional[float] = Field(None, description="Max % change 120min")
    
    # Consecutive candles
    min_consecutive_candles: Optional[int] = Field(None, description="Min consecutive candles (1min)")
    max_consecutive_candles: Optional[int] = Field(None, description="Max consecutive candles (1min)")
    min_consecutive_candles_2m: Optional[int] = Field(None, description="Min consecutive candles 2min")
    max_consecutive_candles_2m: Optional[int] = Field(None, description="Max consecutive candles 2min")
    min_consecutive_candles_5m: Optional[int] = Field(None, description="Min consecutive candles 5min")
    max_consecutive_candles_5m: Optional[int] = Field(None, description="Max consecutive candles 5min")
    min_consecutive_candles_10m: Optional[int] = Field(None, description="Min consecutive candles 10min")
    max_consecutive_candles_10m: Optional[int] = Field(None, description="Max consecutive candles 10min")
    min_consecutive_candles_15m: Optional[int] = Field(None, description="Min consecutive candles 15min")
    max_consecutive_candles_15m: Optional[int] = Field(None, description="Max consecutive candles 15min")
    min_consecutive_candles_30m: Optional[int] = Field(None, description="Min consecutive candles 30min")
    max_consecutive_candles_30m: Optional[int] = Field(None, description="Max consecutive candles 30min")
    min_consecutive_candles_60m: Optional[int] = Field(None, description="Min consecutive candles 60min")
    max_consecutive_candles_60m: Optional[int] = Field(None, description="Max consecutive candles 60min")
    
    # Pivot distances
    min_dist_pivot: Optional[float] = Field(None, description="Min % dist from pivot")
    max_dist_pivot: Optional[float] = Field(None, description="Max % dist from pivot")
    min_dist_pivot_r1: Optional[float] = Field(None, description="Min % dist from R1")
    max_dist_pivot_r1: Optional[float] = Field(None, description="Max % dist from R1")
    min_dist_pivot_s1: Optional[float] = Field(None, description="Min % dist from S1")
    max_dist_pivot_s1: Optional[float] = Field(None, description="Max % dist from S1")
    min_dist_pivot_r2: Optional[float] = Field(None, description="Min % dist from R2")
    max_dist_pivot_r2: Optional[float] = Field(None, description="Max % dist from R2")
    min_dist_pivot_s2: Optional[float] = Field(None, description="Min % dist from S2")
    max_dist_pivot_s2: Optional[float] = Field(None, description="Max % dist from S2")
    
    # Daily SMA absolute values
    min_daily_sma_5: Optional[float] = Field(None, description="Min daily SMA(5)")
    max_daily_sma_5: Optional[float] = Field(None, description="Max daily SMA(5)")
    min_daily_sma_8: Optional[float] = Field(None, description="Min daily SMA(8)")
    max_daily_sma_8: Optional[float] = Field(None, description="Max daily SMA(8)")
    min_daily_sma_10: Optional[float] = Field(None, description="Min daily SMA(10)")
    max_daily_sma_10: Optional[float] = Field(None, description="Max daily SMA(10)")
    min_daily_sma_20: Optional[float] = Field(None, description="Min daily SMA(20)")
    max_daily_sma_20: Optional[float] = Field(None, description="Max daily SMA(20)")
    min_daily_sma_50: Optional[float] = Field(None, description="Min daily SMA(50)")
    max_daily_sma_50: Optional[float] = Field(None, description="Max daily SMA(50)")
    min_daily_sma_200: Optional[float] = Field(None, description="Min daily SMA(200)")
    max_daily_sma_200: Optional[float] = Field(None, description="Max daily SMA(200)")
    min_daily_rsi: Optional[float] = Field(None, description="Min daily RSI(14)")
    max_daily_rsi: Optional[float] = Field(None, description="Max daily RSI(14)")
    min_daily_adx_14: Optional[float] = Field(None, description="Min daily ADX(14)")
    max_daily_adx_14: Optional[float] = Field(None, description="Max daily ADX(14)")
    min_daily_atr_percent: Optional[float] = Field(None, description="Min daily ATR %")
    max_daily_atr_percent: Optional[float] = Field(None, description="Max daily ATR %")
    min_daily_bb_position: Optional[float] = Field(None, description="Min daily BB position")
    max_daily_bb_position: Optional[float] = Field(None, description="Max daily BB position")
    min_high_52w: Optional[float] = Field(None, description="Min 52w high")
    max_high_52w: Optional[float] = Field(None, description="Max 52w high")
    min_low_52w: Optional[float] = Field(None, description="Min 52w low")
    max_low_52w: Optional[float] = Field(None, description="Max 52w low")
    min_from_52w_high: Optional[float] = Field(None, description="Min pct from 52w high")
    max_from_52w_high: Optional[float] = Field(None, description="Max pct from 52w high")
    min_from_52w_low: Optional[float] = Field(None, description="Min pct from 52w low")
    max_from_52w_low: Optional[float] = Field(None, description="Max pct from 52w low")
    min_decimal: Optional[float] = Field(None, description="Min decimal places")
    max_decimal: Optional[float] = Field(None, description="Max decimal places")
    min_change_from_close_dollars: Optional[float] = Field(None, description="Min change from close dollars")
    max_change_from_close_dollars: Optional[float] = Field(None, description="Max change from close dollars")
    min_change_from_close_ratio: Optional[float] = Field(None, description="Min change from close ratio")
    max_change_from_close_ratio: Optional[float] = Field(None, description="Max change from close ratio")
    min_change_from_open_ratio: Optional[float] = Field(None, description="Min change from open ratio")
    max_change_from_open_ratio: Optional[float] = Field(None, description="Max change from open ratio")
    min_postmarket_change_dollars: Optional[float] = Field(None, description="Min postmarket change dollars")
    max_postmarket_change_dollars: Optional[float] = Field(None, description="Max postmarket change dollars")
    min_rsi_2m: Optional[float] = Field(None, description="Min RSI 2min alias")
    max_rsi_2m: Optional[float] = Field(None, description="Max RSI 2min alias")
    min_rsi_5m: Optional[float] = Field(None, description="Min RSI 5min alias")
    max_rsi_5m: Optional[float] = Field(None, description="Max RSI 5min alias")
    min_rsi_15m: Optional[float] = Field(None, description="Min RSI 15min alias")
    max_rsi_15m: Optional[float] = Field(None, description="Max RSI 15min alias")
    min_rsi_60m: Optional[float] = Field(None, description="Min RSI 60min alias")
    max_rsi_60m: Optional[float] = Field(None, description="Max RSI 60min alias")
    
    # Original core filters (explicit declarations for validation)
    min_above_low: Optional[float] = Field(None, description="Min above low")
    max_above_low: Optional[float] = Field(None, description="Max above low")
    min_adx_14: Optional[float] = Field(None, description="Min ADX 14")
    max_adx_14: Optional[float] = Field(None, description="Max ADX 14")
    min_atr: Optional[float] = Field(None, description="Min ATR")
    max_atr: Optional[float] = Field(None, description="Max ATR")
    min_atr_percent: Optional[float] = Field(None, description="Min ATR percent")
    max_atr_percent: Optional[float] = Field(None, description="Max ATR percent")
    min_avg_volume_20d: Optional[int] = Field(None, ge=0, description="Min 20-day avg volume")
    max_avg_volume_20d: Optional[int] = Field(None, ge=0, description="Max 20-day avg volume")
    min_bb_lower: Optional[float] = Field(None, description="Min BB lower")
    max_bb_lower: Optional[float] = Field(None, description="Max BB lower")
    min_bb_upper: Optional[float] = Field(None, description="Min BB upper")
    max_bb_upper: Optional[float] = Field(None, description="Max BB upper")
    min_below_high: Optional[float] = Field(None, description="Min below high")
    max_below_high: Optional[float] = Field(None, description="Max below high")
    min_bid_ask_ratio: Optional[float] = Field(None, description="Min bid/ask ratio")
    max_bid_ask_ratio: Optional[float] = Field(None, description="Max bid/ask ratio")
    min_change_1d: Optional[float] = Field(None, description="Min 1-day change pct")
    max_change_1d: Optional[float] = Field(None, description="Max 1-day change pct")
    min_change_3d: Optional[float] = Field(None, description="Min 3-day change pct")
    max_change_3d: Optional[float] = Field(None, description="Max 3-day change pct")
    min_change_5d: Optional[float] = Field(None, description="Min 5-day change pct")
    max_change_5d: Optional[float] = Field(None, description="Max 5-day change pct")
    min_change_10d: Optional[float] = Field(None, description="Min 10-day change pct")
    max_change_10d: Optional[float] = Field(None, description="Max 10-day change pct")
    min_change_20d: Optional[float] = Field(None, description="Min 20-day change pct")
    max_change_20d: Optional[float] = Field(None, description="Max 20-day change pct")
    min_chg_60min: Optional[float] = Field(None, description="Min 60min change pct")
    max_chg_60min: Optional[float] = Field(None, description="Max 60min change pct")
    min_dist_daily_sma_20: Optional[float] = Field(None, description="Min dist daily SMA 20 pct")
    max_dist_daily_sma_20: Optional[float] = Field(None, description="Max dist daily SMA 20 pct")
    min_dist_daily_sma_50: Optional[float] = Field(None, description="Min dist daily SMA 50 pct")
    max_dist_daily_sma_50: Optional[float] = Field(None, description="Max dist daily SMA 50 pct")
    min_dist_from_vwap: Optional[float] = Field(None, description="Min dist from VWAP pct")
    max_dist_from_vwap: Optional[float] = Field(None, description="Max dist from VWAP pct")
    min_dist_sma_5: Optional[float] = Field(None, description="Min dist SMA 5 pct")
    max_dist_sma_5: Optional[float] = Field(None, description="Max dist SMA 5 pct")
    min_dist_sma_8: Optional[float] = Field(None, description="Min dist SMA 8 pct")
    max_dist_sma_8: Optional[float] = Field(None, description="Max dist SMA 8 pct")
    min_dist_sma_20: Optional[float] = Field(None, description="Min dist SMA 20 pct")
    max_dist_sma_20: Optional[float] = Field(None, description="Max dist SMA 20 pct")
    min_dist_sma_50: Optional[float] = Field(None, description="Min dist SMA 50 pct")
    max_dist_sma_50: Optional[float] = Field(None, description="Max dist SMA 50 pct")
    min_dist_sma_200: Optional[float] = Field(None, description="Min dist SMA 200 pct")
    max_dist_sma_200: Optional[float] = Field(None, description="Max dist SMA 200 pct")
    min_ema_20: Optional[float] = Field(None, description="Min EMA 20")
    max_ema_20: Optional[float] = Field(None, description="Max EMA 20")
    min_ema_50: Optional[float] = Field(None, description="Min EMA 50")
    max_ema_50: Optional[float] = Field(None, description="Max EMA 50")
    min_float_shares: Optional[int] = Field(None, ge=0, description="Min float shares")
    max_float_shares: Optional[int] = Field(None, ge=0, description="Max float shares")
    min_float_turnover: Optional[float] = Field(None, description="Min float turnover")
    max_float_turnover: Optional[float] = Field(None, description="Max float turnover")
    min_gap_percent: Optional[float] = Field(None, description="Min gap pct")
    max_gap_percent: Optional[float] = Field(None, description="Max gap pct")
    min_macd_line: Optional[float] = Field(None, description="Min MACD line")
    max_macd_line: Optional[float] = Field(None, description="Max MACD line")
    min_macd_hist: Optional[float] = Field(None, description="Min MACD histogram")
    max_macd_hist: Optional[float] = Field(None, description="Max MACD histogram")
    max_minute_volume: Optional[int] = Field(None, ge=0, description="Max minute volume")
    min_pos_in_range: Optional[float] = Field(None, description="Min pos in range")
    max_pos_in_range: Optional[float] = Field(None, description="Max pos in range")
    min_pos_of_open: Optional[float] = Field(None, description="Min pos of open")
    max_pos_of_open: Optional[float] = Field(None, description="Max pos of open")
    min_premarket_change_percent: Optional[float] = Field(None, description="Min premarket change pct")
    max_premarket_change_percent: Optional[float] = Field(None, description="Max premarket change pct")
    min_prev_day_volume: Optional[int] = Field(None, ge=0, description="Min prev day volume")
    max_prev_day_volume: Optional[int] = Field(None, ge=0, description="Max prev day volume")
    min_rsi: Optional[float] = Field(None, description="Min RSI")
    max_rsi: Optional[float] = Field(None, description="Max RSI")
    min_shares_outstanding: Optional[int] = Field(None, ge=0, description="Min shares outstanding")
    max_shares_outstanding: Optional[int] = Field(None, ge=0, description="Max shares outstanding")
    min_sma_5: Optional[float] = Field(None, description="Min SMA 5")
    max_sma_5: Optional[float] = Field(None, description="Max SMA 5")
    min_sma_8: Optional[float] = Field(None, description="Min SMA 8")
    max_sma_8: Optional[float] = Field(None, description="Max SMA 8")
    min_sma_20: Optional[float] = Field(None, description="Min SMA 20")
    max_sma_20: Optional[float] = Field(None, description="Max SMA 20")
    min_sma_50: Optional[float] = Field(None, description="Min SMA 50")
    max_sma_50: Optional[float] = Field(None, description="Max SMA 50")
    min_sma_200: Optional[float] = Field(None, description="Min SMA 200")
    max_sma_200: Optional[float] = Field(None, description="Max SMA 200")
    min_stoch_k: Optional[float] = Field(None, description="Min Stochastic K")
    max_stoch_k: Optional[float] = Field(None, description="Max Stochastic K")
    min_stoch_d: Optional[float] = Field(None, description="Min Stochastic D")
    max_stoch_d: Optional[float] = Field(None, description="Max Stochastic D")
    min_todays_range: Optional[float] = Field(None, description="Min todays range")
    max_todays_range: Optional[float] = Field(None, description="Max todays range")
    min_todays_range_pct: Optional[float] = Field(None, description="Min todays range pct")
    max_todays_range_pct: Optional[float] = Field(None, description="Max todays range pct")
    min_trades_today: Optional[int] = Field(None, ge=0, description="Min trades today")
    max_trades_today: Optional[int] = Field(None, ge=0, description="Max trades today")
    min_trades_z_score: Optional[float] = Field(None, description="Min trades z-score")
    max_trades_z_score: Optional[float] = Field(None, description="Max trades z-score")
    max_volume: Optional[int] = Field(None, ge=0, description="Max volume")
    min_vwap: Optional[float] = Field(None, description="Min VWAP")
    max_vwap: Optional[float] = Field(None, description="Max VWAP")
    min_postmarket_volume: Optional[int] = Field(None, ge=0, description="Min postmarket volume")
    
    # Custom expression (for advanced users)
    custom_expression: Optional[str] = Field(None, description="Python expression for custom filter")
    
    class Config:
        extra = "allow"


class FilterConfig(BaseModel):
    """
    Configuration for a scanner filter
    Stored in database and configurable via admin panel
    """
    id: Optional[int] = Field(None, description="Database ID")
    name: str = Field(..., description="Filter name", max_length=100)
    description: Optional[str] = Field(None, description="Filter description")
    enabled: bool = Field(True, description="Is filter enabled")
    filter_type: str = Field(..., description="Filter type (rvol, price, volume, custom)")
    parameters: FilterParameters = Field(..., description="Filter parameters")
    priority: int = Field(0, description="Filter priority (higher = applied first)")
    
    # Sessions where filter applies
    apply_to_sessions: Optional[List[MarketSession]] = Field(
        None, 
        description="Sessions where filter applies (None = all sessions)"
    )
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def applies_to_session(self, session: MarketSession) -> bool:
        """Check if filter applies to given session"""
        if self.apply_to_sessions is None:
            return True
        return session in self.apply_to_sessions
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


# =============================================
# RVOL SLOT DATA
# =============================================

class RVOLSlotData(BaseModel):
    """
    RVOL data for a specific time slot
    Used for more accurate RVOL calculations
    """
    symbol: str
    date: str  # YYYY-MM-DD
    slot_number: int = Field(..., ge=0, le=77, description="Slot number (0-77 for 5-min slots)")
    slot_time: str  # HH:MM format
    volume_accumulated: int = Field(..., description="Volume accumulated up to this slot")
    trades_count: Optional[int] = Field(None, description="Number of trades")
    avg_price: Optional[float] = Field(None, description="Average price in slot")
    
    @validator('slot_number')
    def validate_slot(cls, v):
        """Validate slot number (78 slots of 5 min = 390 minutes)"""
        if not 0 <= v <= 77:
            raise ValueError("Slot number must be between 0 and 77")
        return v


# =============================================
# TICKER METADATA
# =============================================

class TickerMetadata(BaseModel):
    """
    Reference metadata for a ticker
    Cached in Redis with TTL
    Expandido con campos completos de Polygon API
    """
    # Identificación básica
    symbol: str
    company_name: Optional[str] = None
    
    # Clasificación
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    
    # Capitalización y shares
    market_cap: Optional[int] = None
    free_float: Optional[int] = None
    free_float_percent: Optional[float] = None
    shares_outstanding: Optional[int] = None
    
    # Métricas de volumen y precio
    avg_volume_30d: Optional[int] = None
    avg_volume_10d: Optional[int] = None
    avg_volume_5d: Optional[int] = None
    avg_volume_3m: Optional[int] = None
    avg_price_30d: Optional[float] = None
    beta: Optional[float] = None
    
    # Información de la compañía
    description: Optional[str] = None
    homepage_url: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[Dict[str, str]] = None  # {address1, city, state, postal_code}
    total_employees: Optional[int] = None
    list_date: Optional[str] = None  # Fecha de IPO (YYYY-MM-DD)
    
    # Branding
    logo_url: Optional[str] = None
    icon_url: Optional[str] = None
    
    # Identificadores
    cik: Optional[str] = None  # SEC Central Index Key
    composite_figi: Optional[str] = None  # OpenFIGI identifier
    share_class_figi: Optional[str] = None  # Share Class FIGI
    ticker_root: Optional[str] = None  # Raíz del ticker
    ticker_suffix: Optional[str] = None  # Sufijo del ticker
    
    # Detalles del activo
    type: Optional[str] = None  # CS, ETF, ADRC, etc
    currency_name: Optional[str] = None
    locale: Optional[str] = None  # us, global
    market: Optional[str] = None  # stocks, crypto, fx, otc, indices
    round_lot: Optional[int] = None
    delisted_utc: Optional[str] = None  # Fecha de delisting (NULL si activo)
    
    # Estados
    is_etf: bool = False
    is_actively_trading: bool = True
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @validator('market_cap', 'free_float', 'shares_outstanding', 'avg_volume_30d', 'avg_volume_10d', 'avg_volume_5d', 'avg_volume_3m', 'total_employees', 'round_lot', pre=True)
    def convert_to_int(cls, v):
        """Convert float to int for numeric fields"""
        if v is not None and isinstance(v, float):
            return int(v)
        return v
    
    @validator('address', pre=True)
    def convert_address(cls, v):
        """Convert JSON string to dict for address field"""
        if v is None:
            return None
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v
    
    @validator('list_date', pre=True)
    def convert_list_date(cls, v):
        """Convert date object to string"""
        if v is None:
            return None
        if hasattr(v, 'isoformat'):  # datetime.date or datetime.datetime
            return v.isoformat()
        return str(v)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

