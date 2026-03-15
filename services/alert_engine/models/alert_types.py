"""
Alert Types — Complete enum of all detectable alert types.

Each alert type maps 1:1 to a Trade Ideas alert code.
Organized by implementation tier:
  Tier 1: Implementable now (data available in enriched snapshot + daily OHLC)
  Tier 2: Requires multi-timeframe bar data (BarEngine already computes)
  Tier 3: Requires pattern engine or external data (future)

Quality semantics vary by alert group — see CustomSettingType.
"""

from enum import Enum
from typing import Dict


class CustomSettingType(str, Enum):
    """Defines what the quality/custom-setting number means for each alert group."""
    LOOKBACK_DAYS = "lookback_days"
    QUALITY_RATIO = "quality_ratio"
    VOLUME_RATIO = "volume_ratio"
    MIN_SHARES = "min_shares"
    MIN_DOLLARS = "min_dollars"
    MIN_PERCENT = "min_percent"
    MIN_SIGMA = "min_sigma"
    MIN_SECONDS = "min_seconds"
    MIN_CENTS = "min_cents"
    MIN_TIMES = "min_times"
    MIN_HOURS = "min_hours"
    NONE = "none"


class AlertType(str, Enum):
    """
    All alert types the engine can detect.

    Value = event_type string sent downstream (must match frontend expectations).
    Comment = [CODE] TI code | Tier | CustomSettingType
    """

    # ─── TIER 1: HIGHS & LOWS (lookback_days) ───────────────────────
    NEW_HIGH = "new_high"                                    # [NHP]  T1 lookback_days
    NEW_LOW = "new_low"                                      # [NLP]  T1 lookback_days
    NEW_HIGH_ASK = "new_high_ask"                            # [NHA]  T1 lookback_days
    NEW_LOW_BID = "new_low_bid"                              # [NLB]  T1 lookback_days
    NEW_HIGH_FILTERED = "new_high_filtered"                  # [NHPF] T1 lookback_days
    NEW_LOW_FILTERED = "new_low_filtered"                    # [NLPF] T1 lookback_days
    NEW_HIGH_ASK_FILTERED = "new_high_ask_filtered"          # [NHAF] T1 lookback_days
    NEW_LOW_BID_FILTERED = "new_low_bid_filtered"            # [NLBF] T1 lookback_days
    NEW_HIGH_BID = "new_high_bid"                              # [NHB]  T1 min_shares
    NEW_LOW_ASK = "new_low_ask"                                # [NLA]  T1 min_shares
    NEW_HIGH_BID_FILTERED = "new_high_bid_filtered"            # [NHBF] T1 min_shares
    NEW_LOW_ASK_FILTERED = "new_low_ask_filtered"              # [NLAF] T1 min_shares
    PRE_MARKET_HIGH = "pre_market_high"                      # [HPRE] T1 lookback_days
    PRE_MARKET_LOW = "pre_market_low"                        # [LPRE] T1 lookback_days
    POST_MARKET_HIGH = "post_market_high"                    # [HPOST] T1 lookback_days
    POST_MARKET_LOW = "post_market_low"                      # [LPOST] T1 lookback_days
    CROSSED_DAILY_HIGH_RESISTANCE = "crossed_daily_high_resistance"  # [CDHR] T1 lookback_days
    CROSSED_DAILY_LOW_SUPPORT = "crossed_daily_low_support"          # [CDLS] T1 lookback_days

    # ─── TIER 1: PULLBACKS — Auto variants (anchor = max(open, prev_close)) ──
    PULLBACK_75_FROM_LOW = "pullback_75_from_low"                # [PFL75]  T1 min_percent
    PULLBACK_25_FROM_LOW = "pullback_25_from_low"                # [PFL25]  T1 min_percent
    PULLBACK_75_FROM_HIGH = "pullback_75_from_high"              # [PFH75]  T1 min_percent
    PULLBACK_25_FROM_HIGH = "pullback_25_from_high"              # [PFH25]  T1 min_percent
    # ─── TIER 1: PULLBACKS — Close variants (anchor = prev close) ─────
    PULLBACK_75_FROM_LOW_CLOSE = "pullback_75_from_low_close"    # [PFL75C] T1 min_percent
    PULLBACK_25_FROM_LOW_CLOSE = "pullback_25_from_low_close"    # [PFL25C] T1 min_percent
    PULLBACK_75_FROM_HIGH_CLOSE = "pullback_75_from_high_close"  # [PFH75C] T1 min_percent
    PULLBACK_25_FROM_HIGH_CLOSE = "pullback_25_from_high_close"  # [PFH25C] T1 min_percent
    # ─── TIER 1: PULLBACKS — Open variants (anchor = today's open) ────
    PULLBACK_75_FROM_LOW_OPEN = "pullback_75_from_low_open"      # [PFL75O] T1 min_percent
    PULLBACK_25_FROM_LOW_OPEN = "pullback_25_from_low_open"      # [PFL25O] T1 min_percent
    PULLBACK_75_FROM_HIGH_OPEN = "pullback_75_from_high_open"    # [PFH75O] T1 min_percent
    PULLBACK_25_FROM_HIGH_OPEN = "pullback_25_from_high_open"    # [PFH25O] T1 min_percent

    # ─── TIER 1: CHECK MARK (continuation pattern) ────────────────────
    CHECK_MARK_UP = "check_mark_up"                          # [CMU]  T1 none
    CHECK_MARK_DOWN = "check_mark_down"                      # [CMD]  T1 none

    # ─── TIER 1: % CHANGE (min_percent) ──────────────────────────────
    PERCENT_UP_DAY = "percent_up_day"                        # [PUD]  T1 min_percent
    PERCENT_DOWN_DAY = "percent_down_day"                    # [PDD]  T1 min_percent

    # ─── TIER 1: STD DEVIATION (min_sigma) ───────────────────────────
    STD_DEV_BREAKOUT = "std_dev_breakout"                    # [BBU]  T1 min_sigma
    STD_DEV_BREAKDOWN = "std_dev_breakdown"                  # [BBD]  T1 min_sigma

    # ─── TIER 1: CROSSES — OPEN/CLOSE (min_seconds) ─────────────────
    CROSSED_ABOVE_OPEN = "crossed_above_open"                # [CAO]  T1 min_seconds
    CROSSED_BELOW_OPEN = "crossed_below_open"                # [CBO]  T1 min_seconds
    CROSSED_ABOVE_CLOSE = "crossed_above_prev_close"         # [CAC]  T1 min_seconds
    CROSSED_BELOW_CLOSE = "crossed_below_prev_close"         # [CBC]  T1 min_seconds
    CROSSED_ABOVE_OPEN_CONFIRMED = "crossed_above_open_confirmed"    # [CAOC] T1 none
    CROSSED_BELOW_OPEN_CONFIRMED = "crossed_below_open_confirmed"    # [CBOC] T1 none
    CROSSED_ABOVE_CLOSE_CONFIRMED = "crossed_above_close_confirmed"  # [CACC] T1 none
    CROSSED_BELOW_CLOSE_CONFIRMED = "crossed_below_close_confirmed"  # [CBCC] T1 none

    # ─── TIER 1: CROSSES — VWAP (none) ──────────────────────────────
    CROSSED_ABOVE_VWAP = "vwap_cross_up"                     # [CAVC] T1 none
    CROSSED_BELOW_VWAP = "vwap_cross_down"                   # [CBVC] T1 none

    # ─── TIER 1: CROSSES — DAILY MA (none) ──────────────────────────
    CROSSED_ABOVE_SMA20_DAILY = "crossed_above_sma20_daily"  # [CA20] T1 none
    CROSSED_BELOW_SMA20_DAILY = "crossed_below_sma20_daily"  # [CB20] T1 none
    CROSSED_ABOVE_SMA50_DAILY = "crossed_above_sma50_daily"  # [CA50] T1 none
    CROSSED_BELOW_SMA50_DAILY = "crossed_below_sma50_daily"  # [CB50] T1 none
    CROSSED_ABOVE_SMA200 = "crossed_above_sma200"            # [CA200] T1 none
    CROSSED_BELOW_SMA200 = "crossed_below_sma200"            # [CB200] T1 none

    # ─── TIER 1: VOLUME (volume_ratio) ──────────────────────────────
    HIGH_RELATIVE_VOLUME = "rvol_spike"                      # [HRV]  T1 volume_ratio
    STRONG_VOLUME = "volume_surge"                           # [SV]   T1 volume_ratio
    VOLUME_SPIKE_1MIN = "volume_spike_1min"                  # [VS1]  T1 volume_ratio
    UNUSUAL_PRINTS = "unusual_prints"                        # [UNOP] T1 volume_ratio
    BLOCK_TRADE = "block_trade"                              # [BP]   T1 min_shares

    # ─── TIER 1: RUNNING / MOMENTUM (quality_ratio or min_dollars) ──
    RUNNING_UP_NOW = "running_up"                            # [RUN]  T1 min_dollars
    RUNNING_DOWN_NOW = "running_down"                        # [RDN]  T1 min_dollars
    RUNNING_UP = "running_up_sustained"                      # [RU]   T1 quality_ratio
    RUNNING_DOWN = "running_down_sustained"                  # [RD]   T1 quality_ratio
    RUNNING_UP_INTERMEDIATE = "running_up_intermediate"      # [RUI]  T1 quality_ratio
    RUNNING_DOWN_INTERMEDIATE = "running_down_intermediate"  # [RDI]  T1 quality_ratio
    RUNNING_UP_CONFIRMED = "running_up_confirmed"            # [RUC]  T1 quality_ratio
    RUNNING_DOWN_CONFIRMED = "running_down_confirmed"        # [RDC]  T1 quality_ratio

    # ─── TIER 1: GAPS (min_dollars = total retracement) ─────────────
    GAP_UP_REVERSAL = "gap_up_reversal"                      # [GUR]  T1 min_dollars
    GAP_DOWN_REVERSAL = "gap_down_reversal"                  # [GDR]  T1 min_dollars
    FALSE_GAP_UP_RETRACEMENT = "false_gap_up_retracement"    # [FGUR] T1 min_dollars
    FALSE_GAP_DOWN_RETRACEMENT = "false_gap_down_retracement"  # [FGDR] T1 min_dollars

    # ─── TIER 1: BID/ASK MICROSTRUCTURE ─────────────────────────────
    LARGE_BID_SIZE = "large_bid_size"                        # [LBS]  T1 min_shares
    LARGE_ASK_SIZE = "large_ask_size"                        # [LAS]  T1 min_shares
    MARKET_CROSSED = "market_crossed"                        # [MC]   T1 min_cents
    MARKET_CROSSED_UP = "market_crossed_up"                  # [MCU]  T1 min_cents
    MARKET_CROSSED_DOWN = "market_crossed_down"              # [MCD]  T1 min_cents
    MARKET_LOCKED = "market_locked"                          # [ML]   T1 none
    LARGE_SPREAD = "large_spread"                            # [LSP]  T1 none
    TRADING_ABOVE = "trading_above"                          # [TRA]  T1 min_times
    TRADING_BELOW = "trading_below"                          # [TRB]  T1 min_times
    TRADING_ABOVE_SPECIALIST = "trading_above_specialist"    # [TRAS] T1 min_times
    TRADING_BELOW_SPECIALIST = "trading_below_specialist"    # [TRBS] T1 min_times

    # ─── TIER 1: HALTS ──────────────────────────────────────────────
    HALT = "halt"                                            # [HALT]   T1 none
    RESUME = "resume"                                        # [RESUME] T1 none

    # ─── TIER 1: VWAP DIVERGENCE ────────────────────────────────────
    VWAP_DIVERGENCE_UP = "vwap_divergence_up"                # [VDU]  T1 none
    VWAP_DIVERGENCE_DOWN = "vwap_divergence_down"            # [VDD]  T1 none

    # ─── TIER 1: SMA CROSS — 5/8 (7 timeframes) ───────────────────────
    SMA5_ABOVE_SMA8_1M = "sma5_above_sma8_1m"               # [X5A8_1]
    SMA5_BELOW_SMA8_1M = "sma5_below_sma8_1m"               # [X5B8_1]
    SMA5_ABOVE_SMA8_2M = "sma5_above_sma8_2m"               # [X5A8_2]
    SMA5_BELOW_SMA8_2M = "sma5_below_sma8_2m"               # [X5B8_2]
    SMA5_ABOVE_SMA8_4M = "sma5_above_sma8_4m"               # [X5A8_4]
    SMA5_BELOW_SMA8_4M = "sma5_below_sma8_4m"               # [X5B8_4]
    SMA5_ABOVE_SMA8_5M = "sma5_above_sma8_5m"               # [X5A8_5]
    SMA5_BELOW_SMA8_5M = "sma5_below_sma8_5m"               # [X5B8_5]
    SMA5_ABOVE_SMA8_10M = "sma5_above_sma8_10m"             # [X5A8_10]
    SMA5_BELOW_SMA8_10M = "sma5_below_sma8_10m"             # [X5B8_10]
    SMA5_ABOVE_SMA8_20M = "sma5_above_sma8_20m"             # [X5A8_20]
    SMA5_BELOW_SMA8_20M = "sma5_below_sma8_20m"             # [X5B8_20]
    SMA5_ABOVE_SMA8_30M = "sma5_above_sma8_30m"             # [X5A8_30]
    SMA5_BELOW_SMA8_30M = "sma5_below_sma8_30m"             # [X5B8_30]

    # ─── TIER 1: SMA CROSS — 8/20 (3 timeframes) ───────────────────────
    SMA8_ABOVE_SMA20_2M = "sma8_above_sma20_2m"             # [ECAY2]
    SMA8_BELOW_SMA20_2M = "sma8_below_sma20_2m"             # [ECBY2]
    SMA8_ABOVE_SMA20_5M = "sma8_above_sma20_5min"           # [ECAY5]  (legacy name kept)
    SMA8_BELOW_SMA20_5M = "sma8_below_sma20_5min"           # [ECBY5]  (legacy name kept)
    SMA8_ABOVE_SMA20_15M = "sma8_above_sma20_15m"           # [ECAY15]
    SMA8_BELOW_SMA20_15M = "sma8_below_sma20_15m"           # [ECBY15]

    # ─── TIER 1: SMA CROSS — 20/200 (3 timeframes) ─────────────────────
    SMA20_ABOVE_SMA200_2M = "sma20_above_sma200_2m"         # [YCAD2]
    SMA20_BELOW_SMA200_2M = "sma20_below_sma200_2m"         # [YCBD2]
    SMA20_ABOVE_SMA200_5M = "sma20_above_sma200_5m"         # [YCAD5]
    SMA20_BELOW_SMA200_5M = "sma20_below_sma200_5m"         # [YCBD5]
    SMA20_ABOVE_SMA200_15M = "sma20_above_sma200_15m"       # [YCAD15]
    SMA20_BELOW_SMA200_15M = "sma20_below_sma200_15m"       # [YCBD15]

    # ─── TIER 1: MACD CROSSES — 5 timeframes (5,10,15,30,60 min) ──────
    MACD_ABOVE_SIGNAL_5M = "macd_above_signal_5min"          # [MDAS5]  (legacy)
    MACD_BELOW_SIGNAL_5M = "macd_below_signal_5min"          # [MDBS5]  (legacy)
    MACD_ABOVE_ZERO_5M = "macd_above_zero_5min"              # [MDAZ5]  (legacy)
    MACD_BELOW_ZERO_5M = "macd_below_zero_5min"              # [MDBZ5]  (legacy)
    MACD_ABOVE_SIGNAL_10M = "macd_above_signal_10m"          # [MDAS10]
    MACD_BELOW_SIGNAL_10M = "macd_below_signal_10m"          # [MDBS10]
    MACD_ABOVE_ZERO_10M = "macd_above_zero_10m"              # [MDAZ10]
    MACD_BELOW_ZERO_10M = "macd_below_zero_10m"              # [MDBZ10]
    MACD_ABOVE_SIGNAL_15M = "macd_above_signal_15m"          # [MDAS15]
    MACD_BELOW_SIGNAL_15M = "macd_below_signal_15m"          # [MDBS15]
    MACD_ABOVE_ZERO_15M = "macd_above_zero_15m"              # [MDAZ15]
    MACD_BELOW_ZERO_15M = "macd_below_zero_15m"              # [MDBZ15]
    MACD_ABOVE_SIGNAL_30M = "macd_above_signal_30m"          # [MDAS30]
    MACD_BELOW_SIGNAL_30M = "macd_below_signal_30m"          # [MDBS30]
    MACD_ABOVE_ZERO_30M = "macd_above_zero_30m"              # [MDAZ30]
    MACD_BELOW_ZERO_30M = "macd_below_zero_30m"              # [MDBZ30]
    MACD_ABOVE_SIGNAL_60M = "macd_above_signal_60m"          # [MDAS60]
    MACD_BELOW_SIGNAL_60M = "macd_below_signal_60m"          # [MDBS60]
    MACD_ABOVE_ZERO_60M = "macd_above_zero_60m"              # [MDAZ60]
    MACD_BELOW_ZERO_60M = "macd_below_zero_60m"              # [MDBZ60]

    # ─── STOCHASTIC CROSSES — 3 timeframes (5,15,60 min) ───────────────
    STOCH_CROSS_BULLISH_5M = "stoch_cross_bullish_5min"      # [SC20_5]  (legacy)
    STOCH_CROSS_BEARISH_5M = "stoch_cross_bearish_5min"      # [SC80_5]  (legacy)
    STOCH_CROSS_BULLISH_15M = "stoch_cross_bullish_15m"      # [SC20_15]
    STOCH_CROSS_BEARISH_15M = "stoch_cross_bearish_15m"      # [SC80_15]
    STOCH_CROSS_BULLISH_60M = "stoch_cross_bullish_60m"      # [SC20_60]
    STOCH_CROSS_BEARISH_60M = "stoch_cross_bearish_60m"      # [SC80_60]

    # ─── CANDLE PATTERN ALERTS ─────────────────────────────────────────
    # Doji — 5 timeframes (5,10,15,30,60 min), neutral, no custom setting
    DOJI_5M = "doji_5m"                                      # [DOJ5]
    DOJI_10M = "doji_10m"                                    # [DOJ10]
    DOJI_15M = "doji_15m"                                    # [DOJ15]
    DOJI_30M = "doji_30m"                                    # [DOJ30]
    DOJI_60M = "doji_60m"                                    # [DOJ60]
    # Hammer — 6 timeframes (2,5,10,15,30,60 min), bullish
    HAMMER_2M = "hammer_2m"                                  # [HMR2]
    HAMMER_5M = "hammer_5m"                                  # [HMR5]
    HAMMER_10M = "hammer_10m"                                # [HMR10]
    HAMMER_15M = "hammer_15m"                                # [HMR15]
    HAMMER_30M = "hammer_30m"                                # [HMR30]
    HAMMER_60M = "hammer_60m"                                # [HMR60]
    # Hanging Man — 6 timeframes (2,5,10,15,30,60 min), bearish
    HANGING_MAN_2M = "hanging_man_2m"                        # [HGM2]
    HANGING_MAN_5M = "hanging_man_5m"                        # [HGM5]
    HANGING_MAN_10M = "hanging_man_10m"                      # [HGM10]
    HANGING_MAN_15M = "hanging_man_15m"                      # [HGM15]
    HANGING_MAN_30M = "hanging_man_30m"                      # [HGM30]
    HANGING_MAN_60M = "hanging_man_60m"                      # [HGM60]
    # Bullish Engulfing — 4 timeframes (5,10,15,30 min)
    ENGULF_BULL_5M = "engulf_bull_5m"                        # [NGU5]
    ENGULF_BULL_10M = "engulf_bull_10m"                      # [NGU10]
    ENGULF_BULL_15M = "engulf_bull_15m"                      # [NGU15]
    ENGULF_BULL_30M = "engulf_bull_30m"                      # [NGU30]
    # Bearish Engulfing — 4 timeframes (5,10,15,30 min)
    ENGULF_BEAR_5M = "engulf_bear_5m"                        # [NGD5]
    ENGULF_BEAR_10M = "engulf_bear_10m"                      # [NGD10]
    ENGULF_BEAR_15M = "engulf_bear_15m"                      # [NGD15]
    ENGULF_BEAR_30M = "engulf_bear_30m"                      # [NGD30]
    # Piercing Pattern — 4 timeframes (5,10,15,30 min), bullish
    PIERCING_5M = "piercing_5m"                              # [PP5]
    PIERCING_10M = "piercing_10m"                            # [PP10]
    PIERCING_15M = "piercing_15m"                            # [PP15]
    PIERCING_30M = "piercing_30m"                            # [PP30]
    # Dark Cloud Cover — 4 timeframes (5,10,15,30 min), bearish
    DARK_CLOUD_5M = "dark_cloud_5m"                          # [DCC5]
    DARK_CLOUD_10M = "dark_cloud_10m"                        # [DCC10]
    DARK_CLOUD_15M = "dark_cloud_15m"                        # [DCC15]
    DARK_CLOUD_30M = "dark_cloud_30m"                        # [DCC30]
    # Bottoming Tail — 6 timeframes (2,5,10,15,30,60 min), bullish
    BOTTOMING_TAIL_2M = "bottoming_tail_2m"                  # [BT2]
    BOTTOMING_TAIL_5M = "bottoming_tail_5m"                  # [BT5]
    BOTTOMING_TAIL_10M = "bottoming_tail_10m"                # [BT10]
    BOTTOMING_TAIL_15M = "bottoming_tail_15m"                # [BT15]
    BOTTOMING_TAIL_30M = "bottoming_tail_30m"                # [BT30]
    BOTTOMING_TAIL_60M = "bottoming_tail_60m"                # [BT60]
    # Topping Tail — 6 timeframes (2,5,10,15,30,60 min), bearish
    TOPPING_TAIL_2M = "topping_tail_2m"                      # [TT2]
    TOPPING_TAIL_5M = "topping_tail_5m"                      # [TT5]
    TOPPING_TAIL_10M = "topping_tail_10m"                    # [TT10]
    TOPPING_TAIL_15M = "topping_tail_15m"                    # [TT15]
    TOPPING_TAIL_30M = "topping_tail_30m"                    # [TT30]
    TOPPING_TAIL_60M = "topping_tail_60m"                    # [TT60]
    # Narrow Range Buy Bar — 4 timeframes (5,10,15,30 min), bullish
    NARROW_RANGE_BUY_5M = "narrow_range_buy_5m"              # [NRBB5]
    NARROW_RANGE_BUY_10M = "narrow_range_buy_10m"            # [NRBB10]
    NARROW_RANGE_BUY_15M = "narrow_range_buy_15m"            # [NRBB15]
    NARROW_RANGE_BUY_30M = "narrow_range_buy_30m"            # [NRBB30]
    # Narrow Range Sell Bar — 4 timeframes (5,10,15,30 min), bearish
    NARROW_RANGE_SELL_5M = "narrow_range_sell_5m"            # [NRSB5]
    NARROW_RANGE_SELL_10M = "narrow_range_sell_10m"          # [NRSB10]
    NARROW_RANGE_SELL_15M = "narrow_range_sell_15m"          # [NRSB15]
    NARROW_RANGE_SELL_30M = "narrow_range_sell_30m"          # [NRSB30]
    # Red Bar Reversal — 4 timeframes (2,5,15,60 min), bearish
    RED_BAR_REV_2M = "red_bar_rev_2m"                        # [RBR2]
    RED_BAR_REV_5M = "red_bar_rev_5m"                        # [RBR5]
    RED_BAR_REV_15M = "red_bar_rev_15m"                      # [RBR15]
    RED_BAR_REV_60M = "red_bar_rev_60m"                      # [RBR60]
    # Green Bar Reversal — 4 timeframes (2,5,15,60 min), bullish
    GREEN_BAR_REV_2M = "green_bar_rev_2m"                    # [GBR2]
    GREEN_BAR_REV_5M = "green_bar_rev_5m"                    # [GBR5]
    GREEN_BAR_REV_15M = "green_bar_rev_15m"                  # [GBR15]
    GREEN_BAR_REV_60M = "green_bar_rev_60m"                  # [GBR60]
    # 1-2-3 Continuation Buy — 4 timeframes (2,5,15,60 min), bullish
    CONT_123_BUY_2M = "cont_123_buy_2m"                     # [C1U_2]
    CONT_123_BUY_5M = "cont_123_buy_5m"                     # [C1U_5]
    CONT_123_BUY_15M = "cont_123_buy_15m"                   # [C1U_15]
    CONT_123_BUY_60M = "cont_123_buy_60m"                   # [C1U_60]
    # 1-2-3 Continuation Sell — 4 timeframes (2,5,15,60 min), bearish
    CONT_123_SELL_2M = "cont_123_sell_2m"                    # [C1D_2]
    CONT_123_SELL_5M = "cont_123_sell_5m"                    # [C1D_5]
    CONT_123_SELL_15M = "cont_123_sell_15m"                  # [C1D_15]
    CONT_123_SELL_60M = "cont_123_sell_60m"                  # [C1D_60]

    # ─── TIER 1: ORB — Multi-timeframe (1m, 2m, 5m, 10m, 15m, 30m, 60m) ──
    ORB_UP_1M = "orb_up_1min"                                # [ORU1]   T1
    ORB_DOWN_1M = "orb_down_1min"                            # [ORD1]   T1
    ORB_UP_2M = "orb_up_2min"                                # [ORU2]   T1
    ORB_DOWN_2M = "orb_down_2min"                            # [ORD2]   T1
    ORB_UP_5M = "orb_up_5min"                                # [ORU5]   T1
    ORB_DOWN_5M = "orb_down_5min"                            # [ORD5]   T1
    ORB_UP_10M = "orb_up_10min"                              # [ORU10]  T1
    ORB_DOWN_10M = "orb_down_10min"                          # [ORD10]  T1
    ORB_UP_15M = "orb_up_15min"                              # [ORU15]  T1
    ORB_DOWN_15M = "orb_down_15min"                          # [ORD15]  T1
    ORB_UP_30M = "orb_up_30min"                              # [ORU30]  T1
    ORB_DOWN_30M = "orb_down_30min"                          # [ORD30]  T1
    ORB_UP_60M = "orb_up_60min"                              # [ORU60]  T1
    ORB_DOWN_60M = "orb_down_60min"                          # [ORD60]  T1

    # ─── TIER 1: CONSOLIDATION / CHANNEL ──────────────────────────────
    CONSOLIDATION = "consolidation"                              # [C]    T1 quality_ratio
    CHANNEL_BREAKOUT = "channel_breakout"                        # [CHBO] T1
    CHANNEL_BREAKDOWN = "channel_breakdown"                      # [CHBD] T1
    CHANNEL_BREAKOUT_CONFIRMED = "channel_breakout_confirmed"    # [CHBOC] T1 quality_ratio
    CHANNEL_BREAKDOWN_CONFIRMED = "channel_breakdown_confirmed"  # [CHBDC] T1 quality_ratio

    # ─── TIER 1: FIXED-TIMEFRAME CONSOLIDATION BREAKOUT ────────────
    CONSOL_BREAKOUT_5M = "consol_breakout_5m"                    # [CBO5]  T1 min_cents
    CONSOL_BREAKDOWN_5M = "consol_breakdown_5m"                  # [CBD5]  T1 min_cents
    CONSOL_BREAKOUT_10M = "consol_breakout_10m"                  # [CBO10] T1 min_cents
    CONSOL_BREAKDOWN_10M = "consol_breakdown_10m"                # [CBD10] T1 min_cents
    CONSOL_BREAKOUT_15M = "consol_breakout_15m"                  # [CBO15] T1 min_cents
    CONSOL_BREAKDOWN_15M = "consol_breakdown_15m"                # [CBD15] T1 min_cents
    CONSOL_BREAKOUT_30M = "consol_breakout_30m"                  # [CBO30] T1 min_cents
    CONSOL_BREAKDOWN_30M = "consol_breakdown_30m"                # [CBD30] T1 min_cents

    # ─── TIER 1: GEOMETRIC PATTERNS ───────────────────────────────
    BROADENING_BOTTOM = "broadening_bottom"                      # [GBBOT] T1 min_hours
    BROADENING_TOP = "broadening_top"                            # [GBTOP] T1 min_hours
    TRIANGLE_BOTTOM = "triangle_bottom"                          # [GTBOT] T1 min_hours
    TRIANGLE_TOP = "triangle_top"                                # [GTTOP] T1 min_hours
    RECTANGLE_BOTTOM = "rectangle_bottom"                        # [GRBOT] T1 min_hours
    RECTANGLE_TOP = "rectangle_top"                              # [GRTOP] T1 min_hours
    DOUBLE_BOTTOM = "double_bottom"                              # [GDBOT] T1 min_hours
    DOUBLE_TOP = "double_top"                                    # [GDTOP] T1 min_hours
    HEAD_AND_SHOULDERS_INV = "head_and_shoulders_inv"            # [GHASI] T1 min_hours
    HEAD_AND_SHOULDERS = "head_and_shoulders"                    # [GHAS]  T1 min_hours

    # ─── TIER 1: FIBONACCI RETRACEMENTS ────────────────────────────────
    FIB_BUY_38 = "fib_buy_38"                                  # [FU38]  T1 min_hours
    FIB_SELL_38 = "fib_sell_38"                                # [FD38]  T1 min_hours
    FIB_BUY_50 = "fib_buy_50"                                  # [FU50]  T1 min_hours
    FIB_SELL_50 = "fib_sell_50"                                # [FD50]  T1 min_hours
    FIB_BUY_62 = "fib_buy_62"                                  # [FU62]  T1 min_hours
    FIB_SELL_62 = "fib_sell_62"                                # [FD62]  T1 min_hours
    FIB_BUY_79 = "fib_buy_79"                                  # [FU79]  T1 min_hours
    FIB_SELL_79 = "fib_sell_79"                                # [FD79]  T1 min_hours

    # ─── TIER 1: TRAILING STOPS ──────────────────────────────────────
    TRAILING_STOP_PCT_UP = "trailing_stop_pct_up"                # [TSPU]  T1 min_percent
    TRAILING_STOP_PCT_DOWN = "trailing_stop_pct_down"            # [TSPD]  T1 min_percent
    TRAILING_STOP_VOL_UP = "trailing_stop_vol_up"                # [TSSU]  T1 volume_ratio
    TRAILING_STOP_VOL_DOWN = "trailing_stop_vol_down"            # [TSSD]  T1 volume_ratio

    # ─── TIER 1: LINEAR REGRESSION TRENDS ────────────────────────────
    LINREG_UP_5M = "linreg_up_5m"                              # [PEU5]  T1 min_dollars
    LINREG_DOWN_5M = "linreg_down_5m"                          # [PED5]  T1 min_dollars
    LINREG_UP_15M = "linreg_up_15m"                            # [PEU15] T1 min_dollars
    LINREG_DOWN_15M = "linreg_down_15m"                        # [PED15] T1 min_dollars
    LINREG_UP_30M = "linreg_up_30m"                            # [PEU30] T1 min_dollars
    LINREG_DOWN_30M = "linreg_down_30m"                        # [PED30] T1 min_dollars
    LINREG_UP_90M = "linreg_up_90m"                            # [PEU90] T1 min_dollars
    LINREG_DOWN_90M = "linreg_down_90m"                        # [PED90] T1 min_dollars

    # ─── TIER 1: SMA THRUST (upward/downward) ──────────────────────────
    SMA_THRUST_UP_2M = "sma_thrust_up_2m"                      # [SMAU2]  T1 min_suddenness
    SMA_THRUST_DOWN_2M = "sma_thrust_down_2m"                  # [SMAD2]  T1 min_suddenness
    SMA_THRUST_UP_5M = "sma_thrust_up_5m"                      # [SMAU5]  T1 min_suddenness
    SMA_THRUST_DOWN_5M = "sma_thrust_down_5m"                  # [SMAD5]  T1 min_suddenness
    SMA_THRUST_UP_15M = "sma_thrust_up_15m"                    # [SMAU15] T1 min_suddenness
    SMA_THRUST_DOWN_15M = "sma_thrust_down_15m"                # [SMAD15] T1 min_suddenness

    # ─── TIER 2: N-MINUTE HIGH/LOW (candlestick, no custom setting) ──
    INTRADAY_HIGH_5M = "intraday_high_5m"                        # [IDH5]  T2 none
    INTRADAY_LOW_5M = "intraday_low_5m"                          # [IDL5]  T2 none
    INTRADAY_HIGH_10M = "intraday_high_10m"                      # [IDH10] T2 none
    INTRADAY_LOW_10M = "intraday_low_10m"                        # [IDL10] T2 none
    INTRADAY_HIGH_15M = "intraday_high_15m"                      # [IDH15] T2 none
    INTRADAY_LOW_15M = "intraday_low_15m"                        # [IDL15] T2 none
    INTRADAY_HIGH_30M = "intraday_high_30m"                      # [IDH30] T2 none
    INTRADAY_LOW_30M = "intraday_low_30m"                        # [IDL30] T2 none
    INTRADAY_HIGH_60M = "intraday_high_60m"                      # [IDH60] T2 none
    INTRADAY_LOW_60M = "intraday_low_60m"                        # [IDL60] T2 none


ALERT_TYPE_MAP: Dict[str, AlertType] = {a.value: a for a in AlertType}
