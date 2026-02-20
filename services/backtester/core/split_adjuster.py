"""
Split Adjustment Engine for Polygon FLATS data.

FLATS files are NOT split-adjusted. This module fetches historical split
data from Polygon REST API and computes cumulative adjustment factors so
that all OHLCV data can be compared on the same basis.

Algorithm:
  1.  Fetch all splits for a ticker (or bulk for all tickers).
  2.  Sort splits by execution_date ASC.
  3.  Walk BACKWARDS from the most recent split, accumulating the product
      of (split_from / split_to) — the *price* factor.
  4.  Store (ticker, effective_before_date, cumulative_price_factor).
  5.  When loading bars, any bar with date < effective_before_date gets
      its prices multiplied and volume divided by the factor.
  6.  DuckDB ASOF JOIN handles the lookup efficiently.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import httpx
import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)

_POLYGON_SPLITS_URL = "https://api.polygon.io/v3/reference/splits"


async def fetch_splits_from_polygon(
    api_key: str,
    ticker: str | None = None,
    *,
    limit: int = 1000,
    execution_date_gte: str | None = None,
    execution_date_lte: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch split events from Polygon REST API with pagination."""
    all_results: list[dict] = []
    params: dict[str, Any] = {
        "limit": limit,
        "order": "asc",
        "sort": "execution_date",
        "apiKey": api_key,
    }
    if ticker:
        params["ticker"] = ticker
    if execution_date_gte:
        params["execution_date.gte"] = execution_date_gte
    if execution_date_lte:
        params["execution_date.lte"] = execution_date_lte

    async with httpx.AsyncClient(timeout=30.0) as client:
        url: str | None = _POLYGON_SPLITS_URL
        while url:
            resp = await client.get(url, params=params if url == _POLYGON_SPLITS_URL else {"apiKey": api_key})
            resp.raise_for_status()
            data = resp.json()
            all_results.extend(data.get("results", []))
            url = data.get("next_url")
            params = {}  # next_url already has params

    logger.info(
        "polygon_splits_fetched",
        ticker=ticker,
        count=len(all_results),
    )
    return all_results


def parse_splits(raw_splits: list[dict]) -> pd.DataFrame:
    """Parse Polygon split records into a clean DataFrame."""
    if not raw_splits:
        return pd.DataFrame(columns=["ticker", "execution_date", "split_from", "split_to"])

    records = []
    for s in raw_splits:
        try:
            records.append({
                "ticker": s["ticker"],
                "execution_date": pd.Timestamp(s["execution_date"]).date(),
                "split_from": float(s["split_from"]),
                "split_to": float(s["split_to"]),
            })
        except (KeyError, ValueError, TypeError):
            continue

    df = pd.DataFrame(records)
    # Remove no-op splits (1:1)
    df = df[df["split_from"] != df["split_to"]].copy()
    df = df.sort_values(["ticker", "execution_date"]).reset_index(drop=True)
    return df


def compute_adjustment_factors(splits_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute cumulative price adjustment factors per (ticker, split_date).

    For each split, the cumulative factor represents the multiplier that
    all prices BEFORE that split date need to be multiplied by.

    The factor is accumulated from the most recent split backward:
      factor_n   = split_from_n / split_to_n
      factor_n-1 = factor_n * (split_from_{n-1} / split_to_{n-1})
      ...

    Returns DataFrame with columns:
      ticker, effective_before_date, price_factor, volume_factor
    """
    if splits_df.empty:
        return pd.DataFrame(
            columns=["ticker", "effective_before_date", "price_factor", "volume_factor"]
        )

    results = []
    for ticker, group in splits_df.groupby("ticker"):
        rows = group.sort_values("execution_date", ascending=False)

        cumulative_price_factor = 1.0
        entries = []
        for _, row in rows.iterrows():
            pf = row["split_from"] / row["split_to"]
            cumulative_price_factor *= pf
            entries.append({
                "ticker": ticker,
                "effective_before_date": row["execution_date"],
                "price_factor": cumulative_price_factor,
                "volume_factor": 1.0 / cumulative_price_factor,
            })

        results.extend(entries)

    df = pd.DataFrame(results)
    df = df.sort_values(["ticker", "effective_before_date"]).reset_index(drop=True)
    return df


def adjust_bars_with_factors(
    bars_df: pd.DataFrame,
    factors_df: pd.DataFrame,
    date_col: str = "date",
) -> pd.DataFrame:
    """
    Apply split adjustment factors to OHLCV bars using a vectorized merge.

    For each bar, finds the adjustment factor for the EARLIEST split that
    happened AFTER the bar date for that ticker, which gives the correct
    cumulative factor.

    Args:
        bars_df:    Must have columns: ticker, {date_col}, open, high, low, close, volume
        factors_df: Output of compute_adjustment_factors()
        date_col:   Name of the date column in bars_df

    Returns:
        Copy of bars_df with adjusted OHLCV + vwap columns.
    """
    if factors_df.empty or bars_df.empty:
        return bars_df.copy()

    bars = bars_df.copy()
    bars["_date"] = pd.to_datetime(bars[date_col]).dt.date

    factors = factors_df.copy()
    factors["effective_before_date"] = pd.to_datetime(factors["effective_before_date"]).dt.date

    # For each bar, find the factor for the LATEST split date that is
    # STILL AFTER the bar date.  We do this with a sorted merge.
    # DuckDB ASOF JOIN approach: register both as tables and run SQL.
    con = duckdb.connect(":memory:")
    con.register("bars_raw", bars)
    con.register("adj_factors", factors)

    adjusted = con.execute("""
        WITH bar_factors AS (
            SELECT
                b.*,
                a.price_factor,
                a.volume_factor
            FROM bars_raw b
            ASOF LEFT JOIN adj_factors a
                ON b.ticker = a.ticker
                AND b._date < a.effective_before_date
        )
        SELECT
            ticker,
            {date_col},
            open  * COALESCE(price_factor, 1.0)  AS open,
            high  * COALESCE(price_factor, 1.0)  AS high,
            low   * COALESCE(price_factor, 1.0)  AS low,
            close * COALESCE(price_factor, 1.0)  AS close,
            CAST(volume * COALESCE(volume_factor, 1.0) AS BIGINT) AS volume,
            CASE WHEN vwap IS NOT NULL
                 THEN vwap * COALESCE(price_factor, 1.0)
                 ELSE NULL
            END AS vwap,
            transactions
        FROM bar_factors
        ORDER BY ticker, {date_col}
    """.format(date_col=date_col)).fetchdf()

    con.close()
    return adjusted


class SplitAdjuster:
    """
    High-level interface: fetches splits, caches them, and adjusts data.
    """

    def __init__(
        self,
        polygon_api_key: str,
        cache_dir: Path | None = None,
        cache_ttl_hours: int = 24,
    ):
        self._api_key = polygon_api_key
        self._cache_dir = cache_dir
        self._cache_ttl = timedelta(hours=cache_ttl_hours)
        self._factors_df: pd.DataFrame | None = None

        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self) -> Path | None:
        return self._cache_dir / "splits.parquet" if self._cache_dir else None

    def _cache_is_fresh(self) -> bool:
        path = self._cache_path()
        if not path or not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return (datetime.now() - mtime) < self._cache_ttl

    async def load_factors(self, tickers: list[str] | None = None) -> pd.DataFrame:
        """Load or fetch adjustment factors. Caches as parquet."""
        if self._factors_df is not None:
            if tickers:
                return self._factors_df[self._factors_df["ticker"].isin(tickers)]
            return self._factors_df

        # Try cache
        if self._cache_is_fresh():
            logger.info("splits_cache_hit", path=str(self._cache_path()))
            self._factors_df = pd.read_parquet(self._cache_path())
            if tickers:
                return self._factors_df[self._factors_df["ticker"].isin(tickers)]
            return self._factors_df

        # Fetch from Polygon
        raw = await fetch_splits_from_polygon(self._api_key)
        splits_df = parse_splits(raw)
        self._factors_df = compute_adjustment_factors(splits_df)

        # Save cache
        if self._cache_path():
            self._factors_df.to_parquet(self._cache_path(), index=False)
            logger.info("splits_cache_saved", records=len(self._factors_df))

        if tickers:
            return self._factors_df[self._factors_df["ticker"].isin(tickers)]
        return self._factors_df

    async def adjust(
        self,
        bars_df: pd.DataFrame,
        date_col: str = "date",
    ) -> pd.DataFrame:
        """Adjust a bars DataFrame using cached factors."""
        tickers = bars_df["ticker"].unique().tolist()
        factors = await self.load_factors(tickers)
        return adjust_bars_with_factors(bars_df, factors, date_col=date_col)
