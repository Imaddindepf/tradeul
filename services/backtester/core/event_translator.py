"""
Event Translator — converts TradeUL event types into vectorized boolean masks.

Each event from alert-catalog.ts is translated into a pandas boolean Series
that can be used as entry/exit signals by the backtesting engine.

The translator operates on a DataFrame that already has all indicators
computed by DataLayer.add_indicators_sql().

Usage:
    mask = translate_event(df, "vwap_cross_up")
    combined = translate_events(df, ["vwap_cross_up", "rvol_spike"])  # OR
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _crosses_above(lhs: pd.Series, rhs) -> pd.Series:
    rhs_s = rhs if isinstance(rhs, pd.Series) else pd.Series(rhs, index=lhs.index)
    return (lhs > rhs_s) & (lhs.shift(1) <= rhs_s.shift(1))


def _crosses_below(lhs: pd.Series, rhs) -> pd.Series:
    rhs_s = rhs if isinstance(rhs, pd.Series) else pd.Series(rhs, index=lhs.index)
    return (lhs < rhs_s) & (lhs.shift(1) >= rhs_s.shift(1))


def _pct_change_n(series: pd.Series, n: int) -> pd.Series:
    prev = series.shift(n)
    return np.where(prev > 0, (series - prev) / prev * 100, 0.0)


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series(0.0, index=df.index)


def _false_series(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


# ── Event translation registry ──────────────────────────────────────────────

_TRANSLATORS: dict[str, callable] = {}


def _register(event_id: str):
    def decorator(fn):
        _TRANSLATORS[event_id] = fn
        return fn
    return decorator


# ── Price events ─────────────────────────────────────────────────────────────

@_register("new_high")
def _(df):
    return df["high"] >= _safe_col(df, "intraday_high")

@_register("new_low")
def _(df):
    return df["low"] <= _safe_col(df, "intraday_low")

@_register("pre_market_high")
def _(df):
    return _false_series(df)

@_register("pre_market_low")
def _(df):
    return _false_series(df)

@_register("post_market_high")
def _(df):
    return _false_series(df)

@_register("post_market_low")
def _(df):
    return _false_series(df)


# ── Open/Close crosses ──────────────────────────────────────────────────────

@_register("crossed_above_open")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "day_open"))

@_register("crossed_below_open")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "day_open"))

@_register("crossed_above_prev_close")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "prev_close"))

@_register("crossed_below_prev_close")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "prev_close"))


# ── VWAP events ──────────────────────────────────────────────────────────────

@_register("vwap_cross_up")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "vwap"))

@_register("vwap_cross_down")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "vwap"))


# ── Volume events ────────────────────────────────────────────────────────────

@_register("rvol_spike")
def _(df):
    return _safe_col(df, "rvol") >= 3.0

@_register("volume_surge")
def _(df):
    return _safe_col(df, "rvol") >= 5.0

@_register("volume_spike_1min")
def _(df):
    return _safe_col(df, "rvol") >= 3.0

@_register("unusual_prints")
def _(df):
    return _safe_col(df, "rvol") >= 4.0

@_register("block_trade")
def _(df):
    return _safe_col(df, "dollar_volume") >= 1_000_000


# ── Momentum events ─────────────────────────────────────────────────────────

@_register("running_up")
def _(df):
    return pd.Series(_pct_change_n(df["close"], 5), index=df.index) >= 2.0

@_register("running_down")
def _(df):
    return pd.Series(_pct_change_n(df["close"], 5), index=df.index) <= -2.0

@_register("percent_up_5")
def _(df):
    return _safe_col(df, "change_pct") >= 5.0

@_register("percent_down_5")
def _(df):
    return _safe_col(df, "change_pct") <= -5.0

@_register("percent_up_10")
def _(df):
    return _safe_col(df, "change_pct") >= 10.0

@_register("percent_down_10")
def _(df):
    return _safe_col(df, "change_pct") <= -10.0


# ── Pullback events ──────────────────────────────────────────────────────────

@_register("pullback_75_from_high")
def _(df):
    rng = _safe_col(df, "intraday_high") - _safe_col(df, "intraday_low")
    retracement = _safe_col(df, "intraday_high") - df["close"]
    return np.where(rng > 0, retracement / rng >= 0.75, False)

@_register("pullback_25_from_high")
def _(df):
    rng = _safe_col(df, "intraday_high") - _safe_col(df, "intraday_low")
    retracement = _safe_col(df, "intraday_high") - df["close"]
    return np.where(rng > 0, retracement / rng >= 0.25, False)

@_register("pullback_75_from_low")
def _(df):
    rng = _safe_col(df, "intraday_high") - _safe_col(df, "intraday_low")
    bounce = df["close"] - _safe_col(df, "intraday_low")
    return np.where(rng > 0, bounce / rng >= 0.75, False)

@_register("pullback_25_from_low")
def _(df):
    rng = _safe_col(df, "intraday_high") - _safe_col(df, "intraday_low")
    bounce = df["close"] - _safe_col(df, "intraday_low")
    return np.where(rng > 0, bounce / rng >= 0.25, False)


# ── Gap events ───────────────────────────────────────────────────────────────

@_register("gap_up_reversal")
def _(df):
    gapped_up = _safe_col(df, "gap_pct") > 0
    below_open = df["close"] < _safe_col(df, "day_open")
    return gapped_up & below_open

@_register("gap_down_reversal")
def _(df):
    gapped_down = _safe_col(df, "gap_pct") < 0
    above_open = df["close"] > _safe_col(df, "day_open")
    return gapped_down & above_open


# ── Halt events (not backtestable with OHLCV) ───────────────────────────────

@_register("halt")
def _(df):
    return _false_series(df)

@_register("resume")
def _(df):
    return _false_series(df)


# ── MA Cross events ─────────────────────────────────────────────────────────

@_register("crossed_above_ema20")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "ema_20"))

@_register("crossed_below_ema20")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "ema_20"))

@_register("crossed_above_ema50")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "ema_50"))

@_register("crossed_below_ema50")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "ema_50"))

@_register("crossed_above_sma8")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "sma_8"))

@_register("crossed_below_sma8")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "sma_8"))

@_register("crossed_above_sma20")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "sma_20"))

@_register("crossed_below_sma20")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "sma_20"))

@_register("crossed_above_sma50")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "sma_50"))

@_register("crossed_below_sma50")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "sma_50"))

@_register("crossed_above_sma200")
def _(df):
    return _crosses_above(df["close"], _safe_col(df, "sma_200"))

@_register("crossed_below_sma200")
def _(df):
    return _crosses_below(df["close"], _safe_col(df, "sma_200"))

@_register("sma_8_cross_above_20")
def _(df):
    return _crosses_above(_safe_col(df, "sma_8"), _safe_col(df, "sma_20"))

@_register("sma_8_cross_below_20")
def _(df):
    return _crosses_below(_safe_col(df, "sma_8"), _safe_col(df, "sma_20"))


# ── MACD events ──────────────────────────────────────────────────────────────

@_register("macd_cross_bullish")
def _(df):
    return _crosses_above(_safe_col(df, "macd_line"), _safe_col(df, "macd_signal"))

@_register("macd_cross_bearish")
def _(df):
    return _crosses_below(_safe_col(df, "macd_line"), _safe_col(df, "macd_signal"))

@_register("macd_zero_cross_up")
def _(df):
    return _crosses_above(_safe_col(df, "macd_line"), 0)

@_register("macd_zero_cross_down")
def _(df):
    return _crosses_below(_safe_col(df, "macd_line"), 0)


# ── Stochastic events ───────────────────────────────────────────────────────

@_register("stoch_cross_bullish")
def _(df):
    k, d = _safe_col(df, "stoch_k"), _safe_col(df, "stoch_d")
    cross = _crosses_above(k, d)
    oversold = k.shift(1) < 30
    return cross & oversold

@_register("stoch_cross_bearish")
def _(df):
    k, d = _safe_col(df, "stoch_k"), _safe_col(df, "stoch_d")
    cross = _crosses_below(k, d)
    overbought = k.shift(1) > 70
    return cross & overbought

@_register("stoch_oversold")
def _(df):
    return _safe_col(df, "stoch_k") < 20

@_register("stoch_overbought")
def _(df):
    return _safe_col(df, "stoch_k") > 80


# ── ORB events ───────────────────────────────────────────────────────────────

@_register("orb_breakout_up")
def _(df):
    return df["high"] > _safe_col(df, "high_20d").shift(1)

@_register("orb_breakout_down")
def _(df):
    return df["low"] < _safe_col(df, "low_20d").shift(1)


# ── Consolidation events ────────────────────────────────────────────────────

@_register("consolidation_breakout_up")
def _(df):
    tight_range = _safe_col(df, "bb_width") < _safe_col(df, "bb_width").rolling(20, min_periods=1).mean() * 0.5
    breakout = df["close"] > _safe_col(df, "bb_upper")
    vol_confirm = _safe_col(df, "rvol") >= 1.5
    return tight_range.shift(1).fillna(False) & breakout & vol_confirm

@_register("consolidation_breakout_down")
def _(df):
    tight_range = _safe_col(df, "bb_width") < _safe_col(df, "bb_width").rolling(20, min_periods=1).mean() * 0.5
    breakdown = df["close"] < _safe_col(df, "bb_lower")
    vol_confirm = _safe_col(df, "rvol") >= 1.5
    return tight_range.shift(1).fillna(False) & breakdown & vol_confirm


# ── Bollinger Band events ───────────────────────────────────────────────────

@_register("bb_upper_breakout")
def _(df):
    return df["close"] > _safe_col(df, "bb_upper")

@_register("bb_lower_breakdown")
def _(df):
    return df["close"] < _safe_col(df, "bb_lower")


# ── Daily level events ──────────────────────────────────────────────────────

@_register("crossed_daily_high_resistance")
def _(df):
    return _crosses_above(df["high"], _safe_col(df, "prev_high"))

@_register("crossed_daily_low_support")
def _(df):
    return _crosses_below(df["low"], _safe_col(df, "prev_low"))

@_register("false_gap_up_retracement")
def _(df):
    gapped_up = _safe_col(df, "gap_pct") > 1.0
    retraced = df["low"] <= _safe_col(df, "prev_close")
    return gapped_up & retraced

@_register("false_gap_down_retracement")
def _(df):
    gapped_down = _safe_col(df, "gap_pct") < -1.0
    recovered = df["high"] >= _safe_col(df, "prev_close")
    return gapped_down & recovered


# ── Confirmed / Sustained events ────────────────────────────────────────────

@_register("running_up_sustained")
def _(df):
    return pd.Series(_pct_change_n(df["close"], 10), index=df.index) >= 3.0

@_register("running_down_sustained")
def _(df):
    return pd.Series(_pct_change_n(df["close"], 10), index=df.index) <= -3.0

@_register("running_up_confirmed")
def _(df):
    chg5 = pd.Series(_pct_change_n(df["close"], 5), index=df.index) >= 2.0
    chg15 = pd.Series(_pct_change_n(df["close"], 15), index=df.index) >= 4.0
    return chg5 & chg15

@_register("running_down_confirmed")
def _(df):
    chg5 = pd.Series(_pct_change_n(df["close"], 5), index=df.index) <= -2.0
    chg15 = pd.Series(_pct_change_n(df["close"], 15), index=df.index) <= -4.0
    return chg5 & chg15

@_register("vwap_divergence_up")
def _(df):
    price_new_low = df["low"] <= df["low"].shift(1)
    vwap = _safe_col(df, "vwap")
    vwap_not_low = vwap > vwap.shift(1)
    return price_new_low & vwap_not_low

@_register("vwap_divergence_down")
def _(df):
    price_new_high = df["high"] >= df["high"].shift(1)
    vwap = _safe_col(df, "vwap")
    vwap_not_high = vwap < vwap.shift(1)
    return price_new_high & vwap_not_high

@_register("crossed_above_open_confirmed")
def _(df):
    above = df["close"] > _safe_col(df, "day_open")
    prev_above = df["close"].shift(1) > _safe_col(df, "day_open").shift(1)
    return above & prev_above

@_register("crossed_below_open_confirmed")
def _(df):
    below = df["close"] < _safe_col(df, "day_open")
    prev_below = df["close"].shift(1) < _safe_col(df, "day_open").shift(1)
    return below & prev_below

@_register("crossed_above_close_confirmed")
def _(df):
    above = df["close"] > _safe_col(df, "prev_close")
    prev_above = df["close"].shift(1) > _safe_col(df, "prev_close").shift(1)
    return above & prev_above

@_register("crossed_below_close_confirmed")
def _(df):
    below = df["close"] < _safe_col(df, "prev_close")
    prev_below = df["close"].shift(1) < _safe_col(df, "prev_close").shift(1)
    return below & prev_below


# ── Public API ───────────────────────────────────────────────────────────────

def get_supported_events() -> list[str]:
    """Return list of all event IDs that can be translated."""
    return sorted(_TRANSLATORS.keys())


def is_event_supported(event_id: str) -> bool:
    return event_id in _TRANSLATORS


def translate_event(df: pd.DataFrame, event_id: str) -> pd.Series:
    """
    Translate a single event into a boolean mask over the DataFrame.
    Returns False for all rows if the event is not supported.
    """
    fn = _TRANSLATORS.get(event_id)
    if fn is None:
        return pd.Series(False, index=df.index)
    result = fn(df)
    if isinstance(result, np.ndarray):
        result = pd.Series(result, index=df.index)
    return result.fillna(False).astype(bool)


def translate_events(
    df: pd.DataFrame,
    event_ids: list[str],
    combine: str = "or",
) -> pd.Series:
    """
    Translate multiple events and combine them.

    combine="or"  → any event triggers (entry: choose one of these events)
    combine="and" → all events must fire simultaneously
    """
    if not event_ids:
        return pd.Series(False, index=df.index)

    masks = [translate_event(df, eid) for eid in event_ids]

    if combine == "and":
        result = masks[0]
        for m in masks[1:]:
            result = result & m
        return result
    else:
        result = masks[0]
        for m in masks[1:]:
            result = result | m
        return result
