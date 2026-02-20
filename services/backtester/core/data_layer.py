"""
DuckDB-Based Data Layer for Polygon FLATS.

Provides zero-copy reads from compressed CSV flat files directly into
DuckDB analytical queries. All split adjustment is handled transparently.

Data sources:
  • day_aggs:    /data/polygon/day_aggs/{date}.csv.gz     (~5 MB/day)
  • minute_aggs: /data/polygon/minute_aggs/{date}.csv.gz  (~300 MB/day)
"""
from __future__ import annotations

import glob
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import structlog

from .split_adjuster import SplitAdjuster

logger = structlog.get_logger(__name__)


def _date_range_files(base_dir: Path, start: date, end: date) -> list[str]:
    """Return sorted list of CSV.gz files within the date range."""
    files = []
    current = start
    while current <= end:
        fname = current.strftime("%Y-%m-%d") + ".csv.gz"
        path = base_dir / fname
        if path.exists():
            files.append(str(path))
        current += timedelta(days=1)
    return files


class DataLayer:
    """
    High-performance data access layer backed by DuckDB.

    Reads Polygon FLATS CSV.gz files directly (no ETL needed) and
    applies split adjustment via the SplitAdjuster.
    """

    def __init__(
        self,
        polygon_data_dir: Path,
        split_adjuster: SplitAdjuster | None = None,
        day_aggs_subdir: str = "day_aggs",
        minute_aggs_subdir: str = "minute_aggs",
    ):
        self._data_dir = Path(polygon_data_dir)
        self._day_dir = self._data_dir / day_aggs_subdir
        self._minute_dir = self._data_dir / minute_aggs_subdir
        self._adjuster = split_adjuster
        self._con = duckdb.connect(":memory:")
        self._configure_duckdb()

    def _configure_duckdb(self) -> None:
        self._con.execute("SET threads = 4")
        self._con.execute("SET memory_limit = '2GB'")

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        return self._con

    def close(self) -> None:
        self._con.close()

    # ── Day Bars ─────────────────────────────────────────────────────────

    def load_day_bars(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Load daily OHLCV bars from FLATS day_aggs.

        Returns DataFrame with columns:
            ticker, date, open, high, low, close, volume, vwap, transactions
        """
        files = _date_range_files(self._day_dir, start, end)
        if not files:
            logger.warning("no_day_agg_files", start=str(start), end=str(end))
            return pd.DataFrame(columns=[
                "ticker", "date", "open", "high", "low", "close",
                "volume", "vwap", "transactions",
            ])

        file_list = ", ".join(f"'{f}'" for f in files)
        ticker_filter = ""
        if tickers:
            escaped = ", ".join(f"'{t}'" for t in tickers)
            ticker_filter = f"WHERE ticker IN ({escaped})"

        query = f"""
            SELECT
                ticker,
                CAST(
                    make_timestamp(CAST(timestamp / 1000000000 AS BIGINT))
                    AS DATE
                ) AS date,
                open,
                high,
                low,
                close,
                CAST(volume AS BIGINT) AS volume,
                vwap,
                CAST(transactions AS INTEGER) AS transactions
            FROM read_csv_auto(
                [{file_list}],
                header=true,
                columns={{
                    'ticker': 'VARCHAR',
                    'open': 'DOUBLE',
                    'high': 'DOUBLE',
                    'low': 'DOUBLE',
                    'close': 'DOUBLE',
                    'volume': 'DOUBLE',
                    'vwap': 'DOUBLE',
                    'timestamp': 'BIGINT',
                    'transactions': 'DOUBLE'
                }}
            )
            {ticker_filter}
            ORDER BY ticker, date
        """
        df = self._con.execute(query).fetchdf()
        logger.info(
            "day_bars_loaded",
            files=len(files),
            rows=len(df),
            tickers=df["ticker"].nunique() if len(df) else 0,
        )
        return df

    # ── Minute Bars ──────────────────────────────────────────────────────

    def load_minute_bars(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Load minute-level OHLCV bars from FLATS minute_aggs.

        Returns DataFrame with columns:
            ticker, timestamp, open, high, low, close, volume, vwap, transactions
        """
        files = _date_range_files(self._minute_dir, start, end)
        if not files:
            return pd.DataFrame(columns=[
                "ticker", "timestamp", "open", "high", "low", "close",
                "volume", "vwap", "transactions",
            ])

        file_list = ", ".join(f"'{f}'" for f in files)
        ticker_filter = ""
        if tickers:
            escaped = ", ".join(f"'{t}'" for t in tickers)
            ticker_filter = f"WHERE ticker IN ({escaped})"

        query = f"""
            SELECT
                ticker,
                make_timestamp(CAST(window_start / 1000000000 AS BIGINT)) AS timestamp,
                open, high, low, close,
                CAST(volume AS BIGINT) AS volume,
                vwap,
                CAST(transactions AS INTEGER) AS transactions
            FROM read_csv_auto(
                [{file_list}],
                header=true,
                columns={{
                    'ticker': 'VARCHAR',
                    'open': 'DOUBLE',
                    'high': 'DOUBLE',
                    'low': 'DOUBLE',
                    'close': 'DOUBLE',
                    'volume': 'DOUBLE',
                    'vwap': 'DOUBLE',
                    'window_start': 'BIGINT',
                    'transactions': 'DOUBLE'
                }}
            )
            {ticker_filter}
            ORDER BY ticker, timestamp
        """
        df = self._con.execute(query).fetchdf()
        logger.info("minute_bars_loaded", files=len(files), rows=len(df))
        return df

    # ── Split-Adjusted Loading ───────────────────────────────────────────

    async def load_day_bars_adjusted(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """Load daily bars with split adjustment applied."""
        df = self.load_day_bars(start, end, tickers)
        if self._adjuster and not df.empty:
            df = await self._adjuster.adjust(df, date_col="date")
        return df

    async def load_minute_bars_adjusted(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """Load minute bars with split adjustment applied."""
        df = self.load_minute_bars(start, end, tickers)
        if self._adjuster and not df.empty:
            df = await self._adjuster.adjust(df, date_col="timestamp")
        return df

    # ── Universe Filtering via DuckDB SQL ────────────────────────────────

    def filter_universe_sql(
        self,
        bars_df: pd.DataFrame,
        where_clause: str,
    ) -> list[str]:
        """
        Filter tickers using a SQL WHERE clause against aggregated stats.

        Example: "avg_volume > 500000 AND avg_close BETWEEN 1 AND 50"
        """
        self._con.register("_bars", bars_df)
        query = f"""
            SELECT ticker
            FROM (
                SELECT
                    ticker,
                    AVG(close) AS avg_close,
                    AVG(volume) AS avg_volume,
                    MAX(close) AS max_close,
                    MIN(close) AS min_close,
                    COUNT(*) AS bar_count
                FROM _bars
                GROUP BY ticker
            )
            WHERE {where_clause}
        """
        result = self._con.execute(query).fetchdf()
        self._con.unregister("_bars")
        return result["ticker"].tolist()

    # ── Technical Indicators via DuckDB Window Functions ──────────────────

    def add_indicators_sql(self, bars_df: pd.DataFrame) -> pd.DataFrame:
        """
        Add common technical indicators using DuckDB window functions.
        Vectorized, no Python loops.
        """
        self._con.register("_bars", bars_df)
        result = self._con.execute("""
            SELECT
                *,
                -- Previous close for gap calculation
                LAG(close) OVER w AS prev_close,
                -- Simple Moving Averages
                AVG(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma_20,
                AVG(close) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma_50,
                -- Volume moving average
                AVG(volume) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg_volume_20d,
                -- ATR (simplified: using True Range approximation)
                AVG(high - low) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS atr_14,
                -- Rolling high/low
                MAX(high) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
                MIN(low) OVER (PARTITION BY ticker ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
                -- Bar index within ticker (for RSI calculation helper)
                ROW_NUMBER() OVER w AS bar_idx
            FROM _bars
            WINDOW w AS (PARTITION BY ticker ORDER BY date)
            ORDER BY ticker, date
        """).fetchdf()

        # Derived indicators computed on the enriched DataFrame
        result["gap_pct"] = np.where(
            result["prev_close"] > 0,
            (result["open"] - result["prev_close"]) / result["prev_close"] * 100,
            0.0,
        )
        result["rvol"] = np.where(
            result["avg_volume_20d"] > 0,
            result["volume"] / result["avg_volume_20d"],
            0.0,
        )
        result["range_pct"] = np.where(
            result["low"] > 0,
            (result["high"] - result["low"]) / result["low"] * 100,
            0.0,
        )

        # RSI-14 via vectorized pandas (Wilder's method)
        result = self._compute_rsi(result, period=14)

        self._con.unregister("_bars")
        return result

    @staticmethod
    def _compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Compute RSI per ticker using Wilder's smoothing."""
        rsi_vals = []
        for _, group in df.groupby("ticker"):
            delta = group["close"].diff()
            gain = delta.clip(lower=0)
            loss = (-delta).clip(lower=0)
            avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - (100 / (1 + rs))
            rsi_vals.append(rsi)

        df["rsi_14"] = pd.concat(rsi_vals).reindex(df.index)
        return df
