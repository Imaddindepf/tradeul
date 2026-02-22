"""
Hybrid Data Layer: Polygon FLATS + REST API.

Two data sources, transparently unified:
  1. FLATS (on-disk parquet/csv.gz) — fast, bulk, recent data (~14 months)
  2. Polygon REST API — any historical period, split-adjusted, on-demand

The layer automatically detects FLATS coverage and fills gaps from REST.
REST results are cached locally as parquet for subsequent requests.

FLATS schema (8 columns):
    ticker, volume, open, close, high, low, window_start, transactions
    • window_start: nanoseconds since Unix epoch
    • No vwap column — FLATS data requires SplitAdjuster

REST schema (Polygon v2/aggs):
    v, vw, o, c, h, l, t, n
    • t: milliseconds since epoch
    • Already split-adjusted when adjusted=true
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pandas as pd
import structlog

from .split_adjuster import SplitAdjuster

logger = structlog.get_logger(__name__)

_POLYGON_AGGS_URL = "https://api.polygon.io/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"

_FLATS_CSV_COLUMNS = {
    "ticker": "VARCHAR",
    "volume": "DOUBLE",
    "open": "DOUBLE",
    "close": "DOUBLE",
    "high": "DOUBLE",
    "low": "DOUBLE",
    "window_start": "BIGINT",
    "transactions": "DOUBLE",
}

_OUTPUT_DAY_COLS = [
    "ticker", "date", "open", "high", "low", "close", "volume", "transactions",
]

_OUTPUT_MINUTE_COLS = [
    "ticker", "timestamp", "open", "high", "low", "close", "volume", "transactions",
]


@dataclass
class _DateSources:
    """Grouped file paths by format for a date range."""
    parquet: list[str] = field(default_factory=list)
    csv_gz: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.parquet and not self.csv_gz


def _collect_sources(base_dir: Path, start: date, end: date) -> _DateSources:
    """Collect available files preferring parquet over csv.gz per date."""
    sources = _DateSources()
    current = start
    while current <= end:
        stem = current.strftime("%Y-%m-%d")
        pq = base_dir / f"{stem}.parquet"
        csv = base_dir / f"{stem}.csv.gz"
        if pq.exists():
            sources.parquet.append(str(pq))
        elif csv.exists():
            sources.csv_gz.append(str(csv))
        current += timedelta(days=1)
    return sources


async def _fetch_polygon_rest_daily(
    api_key: str,
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Fetch daily bars from Polygon REST API (split-adjusted)."""
    url = _POLYGON_AGGS_URL.format(
        ticker=ticker, multiplier=1, timespan="day",
        from_date=start.isoformat(), to_date=end.isoformat(),
    )
    all_bars: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        all_bars.extend(data.get("results", []))

    if not all_bars:
        return pd.DataFrame(columns=_OUTPUT_DAY_COLS)

    rows = []
    for b in all_bars:
        rows.append({
            "ticker": ticker,
            "date": pd.Timestamp.fromtimestamp(b["t"] / 1000).normalize(),
            "open": b["o"],
            "high": b["h"],
            "low": b["l"],
            "close": b["c"],
            "volume": int(b["v"]),
            "transactions": int(b.get("n", 0)),
        })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    logger.info("rest_daily_fetched", ticker=ticker, bars=len(df),
                start=str(start), end=str(end))
    return df


async def _fetch_polygon_rest_minute(
    api_key: str,
    ticker: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    """Fetch minute bars from Polygon REST API (split-adjusted, paginated)."""
    all_bars: list[dict] = []
    chunk_start = start
    async with httpx.AsyncClient(timeout=30.0) as client:
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=5), end)
            url = _POLYGON_AGGS_URL.format(
                ticker=ticker, multiplier=1, timespan="minute",
                from_date=chunk_start.isoformat(), to_date=chunk_end.isoformat(),
            )
            params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            all_bars.extend(data.get("results", []))
            chunk_start = chunk_end + timedelta(days=1)

    if not all_bars:
        return pd.DataFrame(columns=_OUTPUT_MINUTE_COLS)

    rows = []
    for b in all_bars:
        rows.append({
            "ticker": ticker,
            "timestamp": pd.Timestamp.fromtimestamp(b["t"] / 1000),
            "open": b["o"],
            "high": b["h"],
            "low": b["l"],
            "close": b["c"],
            "volume": int(b["v"]),
            "transactions": int(b.get("n", 0)),
        })
    df = pd.DataFrame(rows)
    logger.info("rest_minute_fetched", ticker=ticker, bars=len(df))
    return df


class _RESTCache:
    """Simple parquet-backed cache for Polygon REST results."""

    def __init__(self, cache_dir: Path):
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, ticker: str, timespan: str) -> Path:
        return self._dir / f"{ticker}_{timespan}.parquet"

    def get(self, ticker: str, timespan: str, start: date, end: date) -> pd.DataFrame | None:
        p = self._path(ticker, timespan)
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        date_col = "date" if timespan == "day" else "timestamp"
        if date_col not in df.columns:
            return None
        df[date_col] = pd.to_datetime(df[date_col])
        d_col = df[date_col].dt.date if timespan == "day" else df[date_col].dt.date
        mask = (d_col >= start) & (d_col <= end)
        subset = df[mask]
        if subset.empty:
            return None
        if d_col[mask].min() <= start and d_col[mask].max() >= end:
            return subset
        return None

    def put(self, ticker: str, timespan: str, df: pd.DataFrame) -> None:
        p = self._path(ticker, timespan)
        if p.exists():
            existing = pd.read_parquet(p)
            combined = pd.concat([existing, df], ignore_index=True)
            date_col = "date" if timespan == "day" else "timestamp"
            combined = combined.drop_duplicates(
                subset=["ticker", date_col], keep="last"
            ).sort_values(["ticker", date_col])
            combined.to_parquet(p, index=False)
        else:
            df.to_parquet(p, index=False)


class DataLayer:
    """
    High-performance data access layer backed by DuckDB.

    Reads Polygon FLATS files (parquet preferred, csv.gz fallback) directly
    and applies split adjustment via the SplitAdjuster.
    """

    def __init__(
        self,
        polygon_data_dir: Path,
        split_adjuster: SplitAdjuster | None = None,
        polygon_api_key: str = "",
        rest_cache_dir: Path | None = None,
        day_aggs_subdir: str = "day_aggs",
        minute_aggs_subdir: str = "minute_aggs",
    ):
        self._data_dir = Path(polygon_data_dir)
        self._day_dir = self._data_dir / day_aggs_subdir
        self._minute_dir = self._data_dir / minute_aggs_subdir
        self._adjuster = split_adjuster
        self._api_key = polygon_api_key
        self._rest_cache = _RESTCache(rest_cache_dir) if rest_cache_dir else None
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

    # ── Internal: build a SELECT fragment from mixed sources ──────────

    def _build_source_cte(
        self,
        sources: _DateSources,
        ticker_filter: str,
    ) -> str:
        """
        Build a DuckDB query that UNIONs parquet and csv.gz sources,
        normalising column names to: ticker, open, high, low, close,
        volume, window_start, transactions.
        """
        parts: list[str] = []

        select_cols = """
                ticker,
                open,
                high,
                low,
                close,
                CAST(volume AS BIGINT) AS volume,
                window_start,
                CAST(transactions AS INTEGER) AS transactions"""

        if sources.parquet:
            pq_list = ", ".join(f"'{f}'" for f in sources.parquet)
            parts.append(
                f"SELECT {select_cols} FROM read_parquet([{pq_list}])"
            )

        if sources.csv_gz:
            csv_list = ", ".join(f"'{f}'" for f in sources.csv_gz)
            col_spec = ", ".join(
                f"'{k}': '{v}'" for k, v in _FLATS_CSV_COLUMNS.items()
            )
            parts.append(
                f"SELECT {select_cols} FROM read_csv("
                f"[{csv_list}], header=true, delim=',', "
                f"columns={{{col_spec}}})"
            )

        union = " UNION ALL ".join(parts)
        return f"SELECT * FROM ({union}) AS _raw {ticker_filter}"

    @staticmethod
    def _ticker_where(tickers: list[str] | None) -> str:
        if not tickers:
            return ""
        escaped = ", ".join(f"'{t}'" for t in tickers)
        return f"WHERE ticker IN ({escaped})"

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
            ticker, date, open, high, low, close, volume, transactions
        """
        sources = _collect_sources(self._day_dir, start, end)
        if sources.empty:
            logger.warning("no_day_agg_files", start=str(start), end=str(end))
            return pd.DataFrame(columns=_OUTPUT_DAY_COLS)

        ticker_where = self._ticker_where(tickers)
        inner = self._build_source_cte(sources, ticker_where)

        query = f"""
            SELECT
                ticker,
                CAST(
                    make_timestamp(
                        CAST(window_start / 1000 AS BIGINT)
                    ) AS DATE
                ) AS date,
                open,
                high,
                low,
                close,
                volume,
                transactions
            FROM ({inner}) AS _src
            ORDER BY ticker, date
        """
        df = self._con.execute(query).fetchdf()
        n_files = len(sources.parquet) + len(sources.csv_gz)
        logger.info(
            "day_bars_loaded",
            files=n_files,
            rows=len(df),
            tickers=df["ticker"].nunique() if len(df) else 0,
            parquet=len(sources.parquet),
            csv_gz=len(sources.csv_gz),
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
            ticker, timestamp, open, high, low, close, volume, transactions
        """
        sources = _collect_sources(self._minute_dir, start, end)
        if sources.empty:
            return pd.DataFrame(columns=_OUTPUT_MINUTE_COLS)

        ticker_where = self._ticker_where(tickers)
        inner = self._build_source_cte(sources, ticker_where)

        query = f"""
            SELECT
                ticker,
                make_timestamp(
                    CAST(window_start / 1000 AS BIGINT)
                ) AS timestamp,
                open,
                high,
                low,
                close,
                volume,
                transactions
            FROM ({inner}) AS _src
            ORDER BY ticker, timestamp
        """
        df = self._con.execute(query).fetchdf()
        n_files = len(sources.parquet) + len(sources.csv_gz)
        logger.info("minute_bars_loaded", files=n_files, rows=len(df))
        return df

    # ── FLATS coverage detection ────────────────────────────────────────

    def _flats_date_range(self, base_dir: Path) -> tuple[date | None, date | None]:
        """Detect the earliest and latest date available in FLATS."""
        dates: list[date] = []
        if not base_dir.exists():
            return None, None
        for f in base_dir.iterdir():
            stem = f.stem.replace(".csv", "")
            try:
                dates.append(date.fromisoformat(stem))
            except ValueError:
                continue
        if not dates:
            return None, None
        return min(dates), max(dates)

    # ── Hybrid Loading (FLATS + REST) ─────────────────────────────────

    async def load_day_bars_adjusted(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """
        Load daily bars with split adjustment, using both data sources:
        - FLATS (on-disk) for dates with local files, then SplitAdjuster
        - Polygon REST API for dates outside FLATS, already adjusted
        """
        flats_min, flats_max = self._flats_date_range(self._day_dir)
        parts: list[pd.DataFrame] = []

        # Determine which ranges need REST vs FLATS
        rest_ranges: list[tuple[date, date]] = []
        flats_start, flats_end = start, end

        if flats_min is None:
            rest_ranges.append((start, end))
            flats_start = flats_end = None
        else:
            if start < flats_min:
                rest_ranges.append((start, min(end, flats_min - timedelta(days=1))))
                flats_start = flats_min
            if end > flats_max:
                rest_ranges.append((max(start, flats_max + timedelta(days=1)), end))
                flats_end = flats_max
            if flats_start and flats_end and flats_start <= flats_end:
                flats_df = self.load_day_bars(flats_start, flats_end, tickers)
                if self._adjuster and not flats_df.empty:
                    flats_df = await self._adjuster.adjust(flats_df, date_col="date")
                if not flats_df.empty:
                    parts.append(flats_df)

        # Fetch REST data for uncovered ranges
        if rest_ranges and self._api_key and tickers:
            for r_start, r_end in rest_ranges:
                rest_dfs = await self._fetch_rest_daily_multi(tickers, r_start, r_end)
                if not rest_dfs.empty:
                    parts.append(rest_dfs)

        if not parts:
            logger.warning("no_data_available", start=str(start), end=str(end),
                           flats_range=f"{flats_min}-{flats_max}" if flats_min else "none")
            return pd.DataFrame(columns=_OUTPUT_DAY_COLS)

        combined = pd.concat(parts, ignore_index=True)
        combined["date"] = pd.to_datetime(combined["date"])
        combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
        combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
        logger.info("day_bars_adjusted_loaded", rows=len(combined),
                     tickers=combined["ticker"].nunique(),
                     flats_range=f"{flats_min}-{flats_max}" if flats_min else "none",
                     rest_ranges=str(rest_ranges) if rest_ranges else "none")
        return combined

    async def load_minute_bars_adjusted(
        self,
        start: date,
        end: date,
        tickers: list[str] | None = None,
    ) -> pd.DataFrame:
        """Load minute bars — hybrid FLATS + REST."""
        flats_min, flats_max = self._flats_date_range(self._minute_dir)
        parts: list[pd.DataFrame] = []

        rest_ranges: list[tuple[date, date]] = []
        flats_start, flats_end = start, end

        if flats_min is None:
            rest_ranges.append((start, end))
            flats_start = flats_end = None
        else:
            if start < flats_min:
                rest_ranges.append((start, min(end, flats_min - timedelta(days=1))))
                flats_start = flats_min
            if end > flats_max:
                rest_ranges.append((max(start, flats_max + timedelta(days=1)), end))
                flats_end = flats_max
            if flats_start and flats_end and flats_start <= flats_end:
                flats_df = self.load_minute_bars(flats_start, flats_end, tickers)
                if self._adjuster and not flats_df.empty:
                    flats_df = await self._adjuster.adjust(flats_df, date_col="timestamp")
                if not flats_df.empty:
                    parts.append(flats_df)

        if rest_ranges and self._api_key and tickers:
            for r_start, r_end in rest_ranges:
                rest_dfs = await self._fetch_rest_minute_multi(tickers, r_start, r_end)
                if not rest_dfs.empty:
                    parts.append(rest_dfs)

        if not parts:
            return pd.DataFrame(columns=_OUTPUT_MINUTE_COLS)

        combined = pd.concat(parts, ignore_index=True)
        combined = combined.sort_values(["ticker", "timestamp"]).reset_index(drop=True)
        return combined

    # ── REST fetchers with cache and parallelism ─────────────────────

    async def _fetch_rest_daily_multi(
        self, tickers: list[str], start: date, end: date,
    ) -> pd.DataFrame:
        """Fetch daily bars from REST for multiple tickers in parallel."""
        async def _get_one(ticker: str) -> pd.DataFrame:
            if self._rest_cache:
                try:
                    cached = self._rest_cache.get(ticker, "day", start, end)
                    if cached is not None:
                        logger.info("rest_cache_hit", ticker=ticker, timespan="day")
                        return cached
                except Exception:
                    pass
            df = await _fetch_polygon_rest_daily(self._api_key, ticker, start, end)
            if self._rest_cache and not df.empty:
                try:
                    self._rest_cache.put(ticker, "day", df)
                except Exception as exc:
                    logger.warning("rest_cache_write_failed", ticker=ticker, error=str(exc))
            return df

        results = await asyncio.gather(
            *[_get_one(t) for t in tickers], return_exceptions=True)
        frames = []
        for t, res in zip(tickers, results):
            if isinstance(res, Exception):
                logger.warning("rest_fetch_failed", ticker=t, error=str(res))
            elif not res.empty:
                frames.append(res)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_OUTPUT_DAY_COLS)

    async def _fetch_rest_minute_multi(
        self, tickers: list[str], start: date, end: date,
    ) -> pd.DataFrame:
        """Fetch minute bars from REST for multiple tickers in parallel."""
        async def _get_one(ticker: str) -> pd.DataFrame:
            if self._rest_cache:
                try:
                    cached = self._rest_cache.get(ticker, "minute", start, end)
                    if cached is not None:
                        return cached
                except Exception:
                    pass
            df = await _fetch_polygon_rest_minute(self._api_key, ticker, start, end)
            if self._rest_cache and not df.empty:
                try:
                    self._rest_cache.put(ticker, "minute", df)
                except Exception as exc:
                    logger.warning("rest_cache_write_failed", ticker=ticker, error=str(exc))
            return df

        results = await asyncio.gather(
            *[_get_one(t) for t in tickers], return_exceptions=True)
        frames = []
        for t, res in zip(tickers, results):
            if isinstance(res, Exception):
                logger.warning("rest_fetch_failed", ticker=t, error=str(res))
            elif not res.empty:
                frames.append(res)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=_OUTPUT_MINUTE_COLS)

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
        Vectorized, no Python loops. Works for both daily (date col) and
        intraday (timestamp col) data.
        """
        time_col = "timestamp" if "timestamp" in bars_df.columns else "date"

        self._con.register("_bars", bars_df)
        result = self._con.execute(f"""
            SELECT
                *,
                LAG(close) OVER w AS prev_close,
                AVG(close) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS sma_20,
                AVG(close) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS sma_50,
                AVG(close) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS sma_200,
                AVG(volume) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg_volume_20d,
                AVG(high - low) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS atr_14,
                MAX(high) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS high_20d,
                MIN(low) OVER (PARTITION BY ticker ORDER BY {time_col} ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS low_20d,
                ROW_NUMBER() OVER w AS bar_idx
            FROM _bars
            WINDOW w AS (PARTITION BY ticker ORDER BY {time_col})
            ORDER BY ticker, {time_col}
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

        result = self._compute_ema_indicators(result)
        result = self._compute_rsi(result, period=14)
        result = self._compute_vwap_proxy(result)

        self._con.unregister("_bars")
        return result

    @staticmethod
    def _compute_ema_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """Compute EMA indicators per ticker using pandas ewm."""
        ema_configs = [(9, "ema_9"), (21, "ema_21")]
        for span, col_name in ema_configs:
            vals = []
            for _, group in df.groupby("ticker"):
                ema = group["close"].ewm(span=span, adjust=False).mean()
                vals.append(ema)
            df[col_name] = pd.concat(vals).reindex(df.index)
        return df

    @staticmethod
    def _compute_vwap_proxy(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute VWAP or proxy per ticker.
        If 'vwap' column exists (from REST data), keep it.
        Otherwise compute cumulative VWAP from OHLCV.
        """
        if "vwap" in df.columns:
            return df
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        date_col = "date" if "date" in df.columns else "timestamp"
        vals = []
        for _, group in df.groupby("ticker"):
            tp = typical_price.loc[group.index]
            vol = df["volume"].loc[group.index]
            cum_tp_vol = (tp * vol).cumsum()
            cum_vol = vol.cumsum()
            vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
            vals.append(vwap)
        df["vwap"] = pd.concat(vals).reindex(df.index)
        return df

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
