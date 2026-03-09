"""
Filter Evaluator — applies TradeUL filter parameters to backtest DataFrames.

Supports the same ~148 filter parameters used by ConfigWindow / EventFilters,
evaluated per-bar against the indicator-enriched DataFrame.

Two modes:
  1. Universe pre-filter: filter tickers before simulation (aggregate stats)
  2. Per-bar filter: apply as additional entry conditions (per-bar evaluation)

Usage:
    # Pre-filter universe
    valid_tickers = evaluate_universe_filters(df, filters)
    
    # Per-bar mask
    mask = evaluate_bar_filters(df, filters)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


# ── Min/Max filter pairs mapped to DataFrame columns ────────────────────────

_DIRECT_FILTERS: list[tuple[str, str, str]] = [
    # (filter_key_prefix, df_column, description)
    ("price", "close", "Price"),
    ("rvol", "rvol", "Relative Volume"),
    ("volume", "volume", "Volume"),
    ("gap_percent", "gap_pct", "Gap %"),
    ("change_percent", "change_pct", "Change %"),
    ("change_from_open", "change_from_open", "Change from Open"),
    ("atr_percent", "atr_pct", "ATR %"),
    ("rsi", "rsi_14", "RSI"),
    ("vwap", "vwap", "VWAP"),
    ("sma_5", "sma_5", "SMA 5"),
    ("sma_8", "sma_8", "SMA 8"),
    ("sma_20", "sma_20", "SMA 20"),
    ("sma_50", "sma_50", "SMA 50"),
    ("sma_200", "sma_200", "SMA 200"),
    ("ema_20", "ema_20", "EMA 20"),
    ("ema_50", "ema_50", "EMA 50"),
    ("macd_line", "macd_line", "MACD Line"),
    ("macd_hist", "macd_hist", "MACD Histogram"),
    ("stoch_k", "stoch_k", "Stochastic %K"),
    ("stoch_d", "stoch_d", "Stochastic %D"),
    ("adx_14", "adx_14", "ADX"),
    ("bb_upper", "bb_upper", "BB Upper"),
    ("bb_lower", "bb_lower", "BB Lower"),
    ("dollar_volume", "dollar_volume", "Dollar Volume"),
    ("range_pct", "range_pct", "Range %"),
    ("dist_from_vwap", "dist_from_vwap", "Distance from VWAP"),
    ("pos_in_range", "pos_in_range", "Position in Range"),
    ("below_high", "below_high", "Below High"),
    ("above_low", "above_low", "Above Low"),
    ("avg_volume_5d", "avg_volume_5d", "Avg Volume 5D"),
    ("avg_volume_10d", "avg_volume_10d", "Avg Volume 10D"),
    ("avg_volume_20d", "avg_volume_20d", "Avg Volume 20D"),
    ("high_52w", "high_52w", "52W High"),
    ("low_52w", "low_52w", "52W Low"),
]


def _apply_min_max(
    mask: pd.Series,
    df: pd.DataFrame,
    filters: dict,
    filter_key: str,
    col_name: str,
) -> pd.Series:
    """Apply min/max filter pair to mask. Skips if column missing or filter not set."""
    if col_name not in df.columns:
        return mask

    min_key = f"min_{filter_key}"
    max_key = f"max_{filter_key}"
    min_val = filters.get(min_key)
    max_val = filters.get(max_key)

    if min_val is not None:
        try:
            mask = mask & (df[col_name] >= float(min_val))
        except (ValueError, TypeError):
            pass

    if max_val is not None:
        try:
            mask = mask & (df[col_name] <= float(max_val))
        except (ValueError, TypeError):
            pass

    return mask


def evaluate_bar_filters(
    df: pd.DataFrame,
    filters: dict,
) -> pd.Series:
    """
    Evaluate filter parameters per-bar, returning a boolean mask.
    Only rows where ALL active filters pass will be True.
    """
    if not filters:
        return pd.Series(True, index=df.index)

    mask = pd.Series(True, index=df.index)

    for filter_key, col_name, _ in _DIRECT_FILTERS:
        mask = _apply_min_max(mask, df, filters, filter_key, col_name)

    # Distance from SMA filters (computed as percentage)
    for sma_period in [5, 8, 20, 50, 200]:
        sma_col = f"sma_{sma_period}"
        dist_key = f"dist_sma_{sma_period}"
        if sma_col in df.columns:
            dist = np.where(
                df[sma_col] > 0,
                (df["close"] - df[sma_col]) / df[sma_col] * 100,
                0.0,
            )
            dist_series = pd.Series(dist, index=df.index)
            min_val = filters.get(f"min_{dist_key}")
            max_val = filters.get(f"max_{dist_key}")
            if min_val is not None:
                mask = mask & (dist_series >= float(min_val))
            if max_val is not None:
                mask = mask & (dist_series <= float(max_val))

    # From 52W high/low (percentage)
    if "high_52w" in df.columns:
        from_52h = np.where(
            df["high_52w"] > 0,
            (df["high_52w"] - df["close"]) / df["high_52w"] * 100,
            0.0,
        )
        from_52h_s = pd.Series(from_52h, index=df.index)
        min_val = filters.get("min_from_52w_high")
        max_val = filters.get("max_from_52w_high")
        if min_val is not None:
            mask = mask & (from_52h_s >= float(min_val))
        if max_val is not None:
            mask = mask & (from_52h_s <= float(max_val))

    if "low_52w" in df.columns:
        from_52l = np.where(
            df["low_52w"] > 0,
            (df["close"] - df["low_52w"]) / df["low_52w"] * 100,
            0.0,
        )
        from_52l_s = pd.Series(from_52l, index=df.index)
        min_val = filters.get("min_from_52w_low")
        max_val = filters.get("max_from_52w_low")
        if min_val is not None:
            mask = mask & (from_52l_s >= float(min_val))
        if max_val is not None:
            mask = mask & (from_52l_s <= float(max_val))

    return mask.fillna(False)


def evaluate_universe_filters(
    df: pd.DataFrame,
    filters: dict,
) -> list[str]:
    """
    Evaluate filters at the aggregate (per-ticker) level to pre-filter
    the universe before simulation. Returns list of valid tickers.

    Uses median/mean of per-bar values to determine if a ticker passes.
    """
    if not filters:
        return df["ticker"].unique().tolist()

    agg_filters = {}
    for filter_key, col_name, _ in _DIRECT_FILTERS:
        min_val = filters.get(f"min_{filter_key}")
        max_val = filters.get(f"max_{filter_key}")
        if min_val is not None or max_val is not None:
            if col_name in df.columns:
                agg_filters[col_name] = (min_val, max_val)

    if not agg_filters:
        return df["ticker"].unique().tolist()

    grouped = df.groupby("ticker")
    valid_tickers = []

    for ticker, group in grouped:
        passes = True
        for col, (min_val, max_val) in agg_filters.items():
            if col in ("volume", "dollar_volume", "avg_volume_5d",
                        "avg_volume_10d", "avg_volume_20d"):
                val = group[col].mean()
            elif col in ("close", "vwap"):
                val = group[col].median()
            elif col in ("rvol",):
                val = group[col].mean()
            else:
                val = group[col].median()

            if min_val is not None and val < float(min_val):
                passes = False
                break
            if max_val is not None and val > float(max_val):
                passes = False
                break

        if passes:
            valid_tickers.append(ticker)

    logger.info(
        "universe_filtered",
        total=df["ticker"].nunique(),
        passed=len(valid_tickers),
        filters_applied=len(agg_filters),
    )
    return valid_tickers


def get_supported_filters() -> list[dict]:
    """Return metadata about all supported filter parameters."""
    result = []
    for filter_key, col_name, description in _DIRECT_FILTERS:
        result.append({
            "min_key": f"min_{filter_key}",
            "max_key": f"max_{filter_key}",
            "column": col_name,
            "description": description,
        })
    return result
