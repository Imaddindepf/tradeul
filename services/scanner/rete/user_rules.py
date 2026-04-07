"""
User Rules Converter
Convierte filtros de usuario (de BD) a ScanRule para RETE
"""

from typing import List, Dict, Any, Optional

from .models import Condition, Operator, ScanRule, RuleOwnerType


# Mapeo de campos min/max a condiciones
FILTER_FIELD_MAPPING = [
    # (min_param, max_param, ticker_field)
    #
    # === Price & Spread ===
    ("min_price", "max_price", "price"),
    ("min_vwap", "max_vwap", "vwap"),
    ("min_spread", "max_spread", "spread"),
    ("min_bid_size", "max_bid_size", "bid_size"),
    ("min_ask_size", "max_ask_size", "ask_size"),
    ("min_distance_from_nbbo", "max_distance_from_nbbo", "distance_from_nbbo"),
    #
    # === Change % ===
    ("min_change_percent", "max_change_percent", "change_percent"),
    ("min_change_from_open", "max_change_from_open", "change_from_open"),
    ("min_change_from_open_dollars", "max_change_from_open_dollars", "change_from_open_dollars"),
    ("min_gap_percent", "max_gap_percent", "gap_percent"),
    ("min_premarket_change_percent", "max_premarket_change_percent", "premarket_change_percent"),
    ("min_postmarket_change_percent", "max_postmarket_change_percent", "postmarket_change_percent"),
    ("min_price_from_high", "max_price_from_high", "price_from_high"),
    ("min_price_from_low", "max_price_from_low", "price_from_low"),
    ("min_price_from_intraday_high", "max_price_from_intraday_high", "price_from_intraday_high"),
    ("min_price_from_intraday_low", "max_price_from_intraday_low", "price_from_intraday_low"),
    #
    # === Volume ===
    ("min_rvol", "max_rvol", "rvol"),
    ("min_volume", "max_volume", "volume_today"),
    ("min_volume_today", None, "volume_today"),
    ("min_minute_volume", "max_minute_volume", "minute_volume"),
    ("min_volume_today_pct", "max_volume_today_pct", "volume_today_pct"),
    ("min_volume_yesterday_pct", "max_volume_yesterday_pct", "volume_yesterday_pct"),
    #
    # === Volume Windows ===
    ("min_vol_1min", "max_vol_1min", "vol_1min"),
    ("min_vol_5min", "max_vol_5min", "vol_5min"),
    ("min_vol_10min", "max_vol_10min", "vol_10min"),
    ("min_vol_15min", "max_vol_15min", "vol_15min"),
    ("min_vol_30min", "max_vol_30min", "vol_30min"),
    #
    # === Volume Window % (Trade Ideas style) ===
    ("min_vol_1min_pct", "max_vol_1min_pct", "vol_1min_pct"),
    ("min_vol_5min_pct", "max_vol_5min_pct", "vol_5min_pct"),
    ("min_vol_10min_pct", "max_vol_10min_pct", "vol_10min_pct"),
    ("min_vol_15min_pct", "max_vol_15min_pct", "vol_15min_pct"),
    ("min_vol_30min_pct", "max_vol_30min_pct", "vol_30min_pct"),
    #
    # === Price Range Windows ===
    ("min_range_2min", "max_range_2min", "range_2min"),
    ("min_range_5min", "max_range_5min", "range_5min"),
    ("min_range_15min", "max_range_15min", "range_15min"),
    ("min_range_30min", "max_range_30min", "range_30min"),
    ("min_range_60min", "max_range_60min", "range_60min"),
    ("min_range_120min", "max_range_120min", "range_120min"),
    ("min_range_2min_pct", "max_range_2min_pct", "range_2min_pct"),
    ("min_range_5min_pct", "max_range_5min_pct", "range_5min_pct"),
    ("min_range_15min_pct", "max_range_15min_pct", "range_15min_pct"),
    ("min_range_30min_pct", "max_range_30min_pct", "range_30min_pct"),
    ("min_range_60min_pct", "max_range_60min_pct", "range_60min_pct"),
    ("min_range_120min_pct", "max_range_120min_pct", "range_120min_pct"),
    #
    # === Time Window Changes ===
    ("min_chg_1min", "max_chg_1min", "chg_1min"),
    ("min_chg_1min_dollars", "max_chg_1min_dollars", "chg_1min_dollars"),
    ("min_chg_5min", "max_chg_5min", "chg_5min"),
    ("min_chg_5min_dollars", "max_chg_5min_dollars", "chg_5min_dollars"),
    ("min_chg_10min", "max_chg_10min", "chg_10min"),
    ("min_chg_10min_dollars", "max_chg_10min_dollars", "chg_10min_dollars"),
    ("min_chg_15min", "max_chg_15min", "chg_15min"),
    ("min_chg_15min_dollars", "max_chg_15min_dollars", "chg_15min_dollars"),
    ("min_chg_30min", "max_chg_30min", "chg_30min"),
    ("min_chg_30min_dollars", "max_chg_30min_dollars", "chg_30min_dollars"),
    ("min_chg_60min", "max_chg_60min", "chg_60min"),
    ("min_chg_60min_dollars", "max_chg_60min_dollars", "chg_60min_dollars"),
    #
    # === Quote ===
    ("min_bid", "max_bid", "bid"),
    ("min_ask", "max_ask", "ask"),
    ("min_bid_ask_ratio", "max_bid_ask_ratio", "bid_ask_ratio"),
    #
    # === Technical (Intraday) ===
    ("min_atr", "max_atr", "atr"),
    ("min_atr_percent", "max_atr_percent", "atr_percent"),
    ("min_rsi", "max_rsi", "rsi_14"),
    ("min_ema_20", "max_ema_20", "ema_20"),
    ("min_ema_50", "max_ema_50", "ema_50"),
    ("min_price_vs_vwap", "max_price_vs_vwap", "price_vs_vwap"),
    # Intraday SMA (actual SMA from BarEngine, not EMA)
    ("min_sma_5", "max_sma_5", "sma_5"),
    ("min_sma_8", "max_sma_8", "sma_8"),
    ("min_sma_20", "max_sma_20", "sma_20"),
    ("min_sma_50", "max_sma_50", "sma_50"),
    ("min_sma_200", "max_sma_200", "sma_200"),
    # MACD / Stochastic / Bollinger
    ("min_macd_line", "max_macd_line", "macd_line"),
    ("min_macd_hist", "max_macd_hist", "macd_hist"),
    ("min_stoch_k", "max_stoch_k", "stoch_k"),
    ("min_stoch_d", "max_stoch_d", "stoch_d"),
    ("min_adx_14", "max_adx_14", "adx_14"),
    ("min_bb_upper", "max_bb_upper", "bb_upper"),
    ("min_bb_lower", "max_bb_lower", "bb_lower"),
    #
    # === Daily Indicators ===
    ("min_daily_sma_20", "max_daily_sma_20", "daily_sma_20"),
    ("min_daily_sma_50", "max_daily_sma_50", "daily_sma_50"),
    ("min_daily_sma_200", "max_daily_sma_200", "daily_sma_200"),
    ("min_daily_rsi", "max_daily_rsi", "daily_rsi"),
    ("min_daily_adx_14", "max_daily_adx_14", "daily_adx_14"),
    ("min_daily_atr_percent", "max_daily_atr_percent", "daily_atr_percent"),
    ("min_daily_bb_position", "max_daily_bb_position", "daily_bb_position"),
    #
    # === 52-Week ===
    ("min_high_52w", "max_high_52w", "high_52w"),
    ("min_low_52w", "max_low_52w", "low_52w"),
    ("min_from_52w_high", "max_from_52w_high", "from_52w_high"),
    ("min_from_52w_low", "max_from_52w_low", "from_52w_low"),
    #
    # === Derived / Computed ===
    ("min_dollar_volume", "max_dollar_volume", "dollar_volume"),
    ("min_todays_range", "max_todays_range", "todays_range"),
    ("min_todays_range_pct", "max_todays_range_pct", "todays_range_pct"),
    ("min_float_turnover", "max_float_turnover", "float_turnover"),
    ("min_dist_from_vwap", "max_dist_from_vwap", "dist_from_vwap"),
    ("min_dist_sma_5", "max_dist_sma_5", "dist_sma_5"),
    ("min_dist_sma_8", "max_dist_sma_8", "dist_sma_8"),
    ("min_dist_sma_20", "max_dist_sma_20", "dist_sma_20"),
    ("min_dist_sma_50", "max_dist_sma_50", "dist_sma_50"),
    ("min_dist_sma_200", "max_dist_sma_200", "dist_sma_200"),
    ("min_dist_daily_sma_20", "max_dist_daily_sma_20", "dist_daily_sma_20"),
    ("min_dist_daily_sma_50", "max_dist_daily_sma_50", "dist_daily_sma_50"),
    ("min_pos_in_range", "max_pos_in_range", "pos_in_range"),
    ("min_below_high", "max_below_high", "below_high"),
    ("min_above_low", "max_above_low", "above_low"),
    ("min_pos_of_open", "max_pos_of_open", "pos_of_open"),
    ("min_prev_day_volume", "max_prev_day_volume", "prev_day_volume"),
    #
    # === Multi-Day Changes ===
    ("min_change_1d", "max_change_1d", "change_1d"),
    ("min_change_3d", "max_change_3d", "change_3d"),
    ("min_change_5d", "max_change_5d", "change_5d"),
    ("min_change_10d", "max_change_10d", "change_10d"),
    ("min_change_20d", "max_change_20d", "change_20d"),
    #
    # === Average Volumes ===
    ("min_avg_volume_5d", "max_avg_volume_5d", "avg_volume_5d"),
    ("min_avg_volume_10d", "max_avg_volume_10d", "avg_volume_10d"),
    ("min_avg_volume_20d", "max_avg_volume_20d", "avg_volume_20d"),
    ("min_avg_volume_3m", "max_avg_volume_3m", "avg_volume_3m"),
    #
    # === Trades ===
    ("min_trades_today", "max_trades_today", "trades_today"),
    ("min_trades_z_score", "max_trades_z_score", "trades_z_score"),
    #
    # === Fundamentals ===
    ("min_market_cap", "max_market_cap", "market_cap"),
    ("min_float", "max_float", "free_float"),
    ("min_float_shares", "max_float_shares", "free_float"),
    ("min_shares_outstanding", "max_shares_outstanding", "shares_outstanding"),
    #
    # === Position in Multi-Period Ranges ===
    ("min_pos_in_5d_range", "max_pos_in_5d_range", "pos_in_5d_range"),
    ("min_pos_in_10d_range", "max_pos_in_10d_range", "pos_in_10d_range"),
    ("min_pos_in_20d_range", "max_pos_in_20d_range", "pos_in_20d_range"),
    ("min_pos_in_3m_range", "max_pos_in_3m_range", "pos_in_3m_range"),
    ("min_pos_in_6m_range", "max_pos_in_6m_range", "pos_in_6m_range"),
    ("min_pos_in_9m_range", "max_pos_in_9m_range", "pos_in_9m_range"),
    ("min_pos_in_52w_range", "max_pos_in_52w_range", "pos_in_52w_range"),
    ("min_pos_in_2y_range", "max_pos_in_2y_range", "pos_in_2y_range"),
    ("min_pos_in_lifetime_range", "max_pos_in_lifetime_range", "pos_in_lifetime_range"),
    ("min_pos_in_prev_day_range", "max_pos_in_prev_day_range", "pos_in_prev_day_range"),
    ("min_pos_in_consolidation", "max_pos_in_consolidation", "pos_in_consolidation"),
    ("min_consolidation_days", "max_consolidation_days", "consolidation_days"),
    ("min_range_contraction", "max_range_contraction", "range_contraction"),
    ("min_lr_divergence_130", "max_lr_divergence_130", "lr_divergence_130"),
    ("min_change_prev_day_pct", "max_change_prev_day_pct", "change_prev_day_pct"),
    #
    # === Pre-Market Range ===
    ("min_premarket_high", "max_premarket_high", "premarket_high"),
    ("min_premarket_low", "max_premarket_low", "premarket_low"),
    ("min_below_premarket_high", "max_below_premarket_high", "below_premarket_high"),
    ("min_above_premarket_low", "max_above_premarket_low", "above_premarket_low"),
    ("min_pos_in_premarket_range", "max_pos_in_premarket_range", "pos_in_premarket_range"),
    #
    # === Multi-TF SMA Distances ===
    ("min_dist_sma_5_2m", "max_dist_sma_5_2m", "dist_sma_5_2m"),
    ("min_dist_sma_5_5m", "max_dist_sma_5_5m", "dist_sma_5_5m"),
    ("min_dist_sma_5_15m", "max_dist_sma_5_15m", "dist_sma_5_15m"),
    ("min_dist_sma_5_30m", "max_dist_sma_5_30m", "dist_sma_5_30m"),
    ("min_dist_sma_5_60m", "max_dist_sma_5_60m", "dist_sma_5_60m"),
    ("min_dist_sma_8_2m", "max_dist_sma_8_2m", "dist_sma_8_2m"),
    ("min_dist_sma_8_5m", "max_dist_sma_8_5m", "dist_sma_8_5m"),
    ("min_dist_sma_8_15m", "max_dist_sma_8_15m", "dist_sma_8_15m"),
    ("min_dist_sma_8_30m", "max_dist_sma_8_30m", "dist_sma_8_30m"),
    ("min_dist_sma_8_60m", "max_dist_sma_8_60m", "dist_sma_8_60m"),
    ("min_dist_sma_10_2m", "max_dist_sma_10_2m", "dist_sma_10_2m"),
    ("min_dist_sma_10_5m", "max_dist_sma_10_5m", "dist_sma_10_5m"),
    ("min_dist_sma_10_15m", "max_dist_sma_10_15m", "dist_sma_10_15m"),
    ("min_dist_sma_10_30m", "max_dist_sma_10_30m", "dist_sma_10_30m"),
    ("min_dist_sma_10_60m", "max_dist_sma_10_60m", "dist_sma_10_60m"),
    ("min_dist_sma_20_2m", "max_dist_sma_20_2m", "dist_sma_20_2m"),
    ("min_dist_sma_20_5m", "max_dist_sma_20_5m", "dist_sma_20_5m"),
    ("min_dist_sma_20_15m", "max_dist_sma_20_15m", "dist_sma_20_15m"),
    ("min_dist_sma_20_30m", "max_dist_sma_20_30m", "dist_sma_20_30m"),
    ("min_dist_sma_20_60m", "max_dist_sma_20_60m", "dist_sma_20_60m"),
    ("min_dist_sma_130_2m", "max_dist_sma_130_2m", "dist_sma_130_2m"),
    ("min_dist_sma_130_5m", "max_dist_sma_130_5m", "dist_sma_130_5m"),
    ("min_dist_sma_130_10m", "max_dist_sma_130_10m", "dist_sma_130_10m"),
    ("min_dist_sma_130_15m", "max_dist_sma_130_15m", "dist_sma_130_15m"),
    ("min_dist_sma_130_30m", "max_dist_sma_130_30m", "dist_sma_130_30m"),
    ("min_dist_sma_130_60m", "max_dist_sma_130_60m", "dist_sma_130_60m"),
    ("min_dist_sma_200_2m", "max_dist_sma_200_2m", "dist_sma_200_2m"),
    ("min_dist_sma_200_5m", "max_dist_sma_200_5m", "dist_sma_200_5m"),
    ("min_dist_sma_200_10m", "max_dist_sma_200_10m", "dist_sma_200_10m"),
    ("min_dist_sma_200_15m", "max_dist_sma_200_15m", "dist_sma_200_15m"),
    ("min_dist_sma_200_30m", "max_dist_sma_200_30m", "dist_sma_200_30m"),
    ("min_dist_sma_200_60m", "max_dist_sma_200_60m", "dist_sma_200_60m"),
    #
    # === SMA Cross ===
    ("min_sma_8_vs_20_2m", "max_sma_8_vs_20_2m", "sma_8_vs_20_2m"),
    ("min_sma_8_vs_20_5m", "max_sma_8_vs_20_5m", "sma_8_vs_20_5m"),
    ("min_sma_8_vs_20_15m", "max_sma_8_vs_20_15m", "sma_8_vs_20_15m"),
    ("min_sma_8_vs_20_60m", "max_sma_8_vs_20_60m", "sma_8_vs_20_60m"),
    ("min_sma_20_vs_200_2m", "max_sma_20_vs_200_2m", "sma_20_vs_200_2m"),
    ("min_sma_20_vs_200_5m", "max_sma_20_vs_200_5m", "sma_20_vs_200_5m"),
    ("min_sma_20_vs_200_15m", "max_sma_20_vs_200_15m", "sma_20_vs_200_15m"),
    ("min_sma_20_vs_200_60m", "max_sma_20_vs_200_60m", "sma_20_vs_200_60m"),
    #
    # === Extended Daily SMA Distances ===
    ("min_dist_daily_sma_5", "max_dist_daily_sma_5", "dist_daily_sma_5"),
    ("min_dist_daily_sma_8", "max_dist_daily_sma_8", "dist_daily_sma_8"),
    ("min_dist_daily_sma_10", "max_dist_daily_sma_10", "dist_daily_sma_10"),
    ("min_dist_daily_sma_200", "max_dist_daily_sma_200", "dist_daily_sma_200"),
    ("min_dist_daily_sma_5_dollars", "max_dist_daily_sma_5_dollars", "dist_daily_sma_5_dollars"),
    ("min_dist_daily_sma_8_dollars", "max_dist_daily_sma_8_dollars", "dist_daily_sma_8_dollars"),
    ("min_dist_daily_sma_10_dollars", "max_dist_daily_sma_10_dollars", "dist_daily_sma_10_dollars"),
    ("min_dist_daily_sma_20_dollars", "max_dist_daily_sma_20_dollars", "dist_daily_sma_20_dollars"),
    ("min_dist_daily_sma_50_dollars", "max_dist_daily_sma_50_dollars", "dist_daily_sma_50_dollars"),
    ("min_dist_daily_sma_200_dollars", "max_dist_daily_sma_200_dollars", "dist_daily_sma_200_dollars"),
    #
    # === Extended Changes & Ranges ===
    ("min_change_1y", "max_change_1y", "change_1y"),
    ("min_change_1y_dollars", "max_change_1y_dollars", "change_1y_dollars"),
    ("min_change_ytd", "max_change_ytd", "change_ytd"),
    ("min_change_ytd_dollars", "max_change_ytd_dollars", "change_ytd_dollars"),
    ("min_change_5d_dollars", "max_change_5d_dollars", "change_5d_dollars"),
    ("min_change_10d_dollars", "max_change_10d_dollars", "change_10d_dollars"),
    ("min_change_20d_dollars", "max_change_20d_dollars", "change_20d_dollars"),
    ("min_range_5d_pct", "max_range_5d_pct", "range_5d_pct"),
    ("min_range_10d_pct", "max_range_10d_pct", "range_10d_pct"),
    ("min_range_20d_pct", "max_range_20d_pct", "range_20d_pct"),
    #
    # === Misc Derived ===
    ("min_yearly_std_dev", "max_yearly_std_dev", "yearly_std_dev"),
    ("min_consecutive_days_up", "max_consecutive_days_up", "consecutive_days_up"),
    ("min_plus_di_minus_di", "max_plus_di_minus_di", "plus_di_minus_di"),
    ("min_gap_dollars", "max_gap_dollars", "gap_dollars"),
    ("min_gap_ratio", "max_gap_ratio", "gap_ratio"),
    ("min_change_from_close", "max_change_from_close", "change_from_close"),
    ("min_change_from_open_weighted", "max_change_from_open_weighted", "change_from_open_weighted"),
    ("min_bb_std_dev", "max_bb_std_dev", "bb_std_dev"),
    #
    # === Multi-TF Position in Range & BB ===
    ("min_pos_in_range_5m", "max_pos_in_range_5m", "pos_in_range_5m"),
    ("min_pos_in_range_15m", "max_pos_in_range_15m", "pos_in_range_15m"),
    ("min_pos_in_range_30m", "max_pos_in_range_30m", "pos_in_range_30m"),
    ("min_pos_in_range_60m", "max_pos_in_range_60m", "pos_in_range_60m"),
    ("min_bb_position_5m", "max_bb_position_5m", "bb_position_5m"),
    ("min_bb_position_15m", "max_bb_position_15m", "bb_position_15m"),
    ("min_bb_position_60m", "max_bb_position_60m", "bb_position_60m"),
    #
    # === Multi-TF RSI ===
    ("min_rsi_14_2m", "max_rsi_14_2m", "rsi_14_2m"),
    ("min_rsi_14_5m", "max_rsi_14_5m", "rsi_14_5m"),
    ("min_rsi_14_15m", "max_rsi_14_15m", "rsi_14_15m"),
    ("min_rsi_14_60m", "max_rsi_14_60m", "rsi_14_60m"),
    #
    # === Extended Time Window Changes ===
    ("min_chg_2min", "max_chg_2min", "chg_2min"),
    ("min_chg_120min", "max_chg_120min", "chg_120min"),
    ("min_chg_2min_dollars", "max_chg_2min_dollars", "chg_2min_dollars"),
    ("min_chg_120min_dollars", "max_chg_120min_dollars", "chg_120min_dollars"),
    #
    # === Consecutive Candles ===
    ("min_consecutive_candles", "max_consecutive_candles", "consecutive_candles"),
    ("min_consecutive_candles_2m", "max_consecutive_candles_2m", "consecutive_candles_2m"),
    ("min_consecutive_candles_5m", "max_consecutive_candles_5m", "consecutive_candles_5m"),
    ("min_consecutive_candles_10m", "max_consecutive_candles_10m", "consecutive_candles_10m"),
    ("min_consecutive_candles_15m", "max_consecutive_candles_15m", "consecutive_candles_15m"),
    ("min_consecutive_candles_30m", "max_consecutive_candles_30m", "consecutive_candles_30m"),
    ("min_consecutive_candles_60m", "max_consecutive_candles_60m", "consecutive_candles_60m"),
    #
    # === Additional Derived (frontend parity) ===
    ("min_decimal", "max_decimal", "decimal"),
    ("min_change_from_close_dollars", "max_change_from_close_dollars", "change_from_close"),
    ("min_change_from_close_ratio", "max_change_from_close_ratio", "change_from_close_ratio"),
    ("min_change_from_open_ratio", "max_change_from_open_ratio", "change_from_open_ratio"),
    ("min_postmarket_change_dollars", "max_postmarket_change_dollars", "postmarket_change_dollars"),
    ("min_postmarket_volume", "max_postmarket_volume", "postmarket_volume"),
    ("min_bb_position_1m", "max_bb_position_1m", "bb_position_1m"),
    # Daily SMA values (absolute, not distance)
    ("min_daily_sma_5", "max_daily_sma_5", "daily_sma_5"),
    ("min_daily_sma_8", "max_daily_sma_8", "daily_sma_8"),
    ("min_daily_sma_10", "max_daily_sma_10", "daily_sma_10"),
    # Multi-day range $ (absolute)
    ("min_range_5d", "max_range_5d", "range_5d"),
    ("min_range_10d", "max_range_10d", "range_10d"),
    ("min_range_20d", "max_range_20d", "range_20d"),
    # RSI multi-TF (frontend sends min_rsi_2m, alias to rsi_14_2m)
    ("min_rsi_2m", "max_rsi_2m", "rsi_14_2m"),
    ("min_rsi_5m", "max_rsi_5m", "rsi_14_5m"),
    ("min_rsi_15m", "max_rsi_15m", "rsi_14_15m"),
    ("min_rsi_60m", "max_rsi_60m", "rsi_14_60m"),
    #
    # === Pivot Distances ===
    ("min_dist_pivot", "max_dist_pivot", "dist_pivot"),
    ("min_dist_pivot_r1", "max_dist_pivot_r1", "dist_pivot_r1"),
    ("min_dist_pivot_s1", "max_dist_pivot_s1", "dist_pivot_s1"),
    ("min_dist_pivot_r2", "max_dist_pivot_r2", "dist_pivot_r2"),
    ("min_dist_pivot_s2", "max_dist_pivot_s2", "dist_pivot_s2"),
    #
    # === Dilution Risk (1=Low, 2=Medium, 3=High; null → excluded) ===
    ("min_dilution_overall_risk_score",    "max_dilution_overall_risk_score",    "dilution_overall_risk_score"),
    ("min_dilution_offering_ability_score","max_dilution_offering_ability_score","dilution_offering_ability_score"),
    ("min_dilution_overhead_supply_score", "max_dilution_overhead_supply_score", "dilution_overhead_supply_score"),
    ("min_dilution_historical_score",      "max_dilution_historical_score",      "dilution_historical_score"),
    ("min_dilution_cash_need_score",       "max_dilution_cash_need_score",       "dilution_cash_need_score"),
]


def filter_params_to_conditions(params: Dict[str, Any]) -> List[Condition]:
    """
    Convierte FilterParameters (dict) a lista de Condition.
    """
    conditions = []
    
    for min_param, max_param, field in FILTER_FIELD_MAPPING:
        min_val = params.get(min_param)
        max_val = params.get(max_param) if max_param else None
        
        if min_val is not None and max_val is not None:
            op = Operator.OUTSIDE if min_val > max_val else Operator.BETWEEN
            conditions.append(Condition(
                field=field,
                operator=op,
                value=[min_val, max_val],
            ))
        elif min_val is not None:
            conditions.append(Condition(
                field=field,
                operator=Operator.GTE,
                value=min_val
            ))
        elif max_val is not None:
            conditions.append(Condition(
                field=field,
                operator=Operator.LTE,
                value=max_val
            ))
    
    # Filtros de lista
    security_type = params.get("security_type")
    if security_type and isinstance(security_type, str) and security_type.strip():
        conditions.append(Condition(
            field="security_type",
            operator=Operator.EQ,
            value=security_type.strip()
        ))
    
    sectors = params.get("sectors")
    if sectors and isinstance(sectors, list):
        conditions.append(Condition(
            field="sector",
            operator=Operator.IN,
            value=sectors
        ))
    
    industries = params.get("industries")
    if industries and isinstance(industries, list):
        conditions.append(Condition(
            field="industry",
            operator=Operator.IN,
            value=industries
        ))
    
    exchanges = params.get("exchanges")
    if exchanges and isinstance(exchanges, list):
        conditions.append(Condition(
            field="exchange",
            operator=Operator.IN,
            value=exchanges
        ))
    
    return conditions


def user_filter_to_scan_rule(
    filter_data: Dict[str, Any],
    user_id: str
) -> Optional[ScanRule]:
    """
    Convierte un registro de user_scanner_filters a ScanRule.
    
    Args:
        filter_data: Dict con campos de la tabla user_scanner_filters
        user_id: ID del usuario propietario
        
    Returns:
        ScanRule o None si no hay condiciones
    """
    filter_id = filter_data.get("id")
    name = filter_data.get("name", f"Scan {filter_id}")
    enabled = filter_data.get("enabled", True)
    priority = filter_data.get("priority", 0)
    params = filter_data.get("parameters", {})
    
    # Si params es string (JSON), parsearlo
    if isinstance(params, str):
        import json
        params = json.loads(params)
    
    conditions = filter_params_to_conditions(params)
    
    if not conditions:
        return None
    
    return ScanRule(
        id=f"user:{user_id}:scan:{filter_id}",
        owner_type=RuleOwnerType.USER,
        owner_id=user_id,
        name=name,
        conditions=conditions,
        enabled=enabled,
        priority=priority,
        sort_field="change_percent",
        sort_descending=True,
    )


def convert_user_filters(
    filters: List[Dict[str, Any]],
    user_id: str
) -> List[ScanRule]:
    """
    Convierte lista de filtros de usuario a ScanRule.
    """
    rules = []
    for filter_data in filters:
        rule = user_filter_to_scan_rule(filter_data, user_id)
        if rule:
            rules.append(rule)
    return rules
