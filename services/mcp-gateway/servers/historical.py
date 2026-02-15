"""
MCP Server: Historical Data
Access to 1760+ days of OHLCV data via DuckDB on Parquet flat files.
Both day-level and minute-level granularity.
"""
from fastmcp import FastMCP
from config import config
from typing import Optional
import duckdb
import os
from datetime import datetime, timedelta

mcp = FastMCP(
    "TradeUL Historical Data",
    instructions="Historical market data service with 1760+ trading days of OHLCV data. "
    "Minute-level and day-level granularity. Powered by DuckDB on Parquet flat files. "
    "Use for backtesting, pattern analysis, and historical comparisons.",
)


def _get_duckdb():
    """Create a fresh DuckDB connection (thread-safe)."""
    conn = duckdb.connect(":memory:")
    conn.execute("SET threads=2")
    conn.execute("SET memory_limit='1GB'")
    return conn


def _find_file(base_path: str, date_str: str) -> Optional[str]:
    """Find data file for a date, preferring Parquet over CSV.gz."""
    parquet = os.path.join(base_path, f"{date_str}.parquet")
    if os.path.exists(parquet):
        return parquet
    csvgz = os.path.join(base_path, f"{date_str}.csv.gz")
    if os.path.exists(csvgz):
        return csvgz
    return None


@mcp.tool()
async def get_day_bars(
    date: str = "today",
    symbols: Optional[list[str]] = None,
    limit: int = 100,
    sort_by: str = "volume",
    sort_order: str = "desc",
) -> dict:
    """Get daily OHLCV bars for a specific date.

    Args:
        date: 'today', 'yesterday', or 'YYYY-MM-DD'
        symbols: Optional list of specific tickers
        limit: Max results (default 100)
        sort_by: Column to sort by (volume, close, change_pct)
        sort_order: 'asc' or 'desc'

    Returns: ticker, open, high, low, close, volume, vwap, transactions
    """
    if date == "today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    elif date == "yesterday":
        dt = datetime.now() - timedelta(days=1)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = date

    filepath = _find_file(config.day_aggs_path, date_str)
    if not filepath:
        return {"error": f"No data found for {date_str}", "date": date_str}

    conn = _get_duckdb()
    try:
        where_clause = ""
        if symbols:
            symbols_str = ", ".join(f"'{s.upper()}'" for s in symbols)
            where_clause = f"WHERE ticker IN ({symbols_str})"

        sql = f"""
        SELECT ticker, open, high, low, close, volume, vwap, transactions,
               ROUND((close - open) / NULLIF(open, 0) * 100, 2) as change_pct
        FROM read_parquet('{filepath}')
        {where_clause}
        ORDER BY {sort_by} {sort_order}
        LIMIT {limit}
        """
        result = conn.execute(sql).fetchdf()
        records = result.to_dict(orient="records")
        return {"date": date_str, "bars": records, "count": len(records)}
    finally:
        conn.close()


@mcp.tool()
async def get_minute_bars(
    date: str,
    symbol: str,
    start_hour: int = 4,
    end_hour: int = 20,
) -> dict:
    """Get minute-level OHLCV bars for a specific ticker and date.

    Args:
        date: 'today', 'yesterday', or 'YYYY-MM-DD'
        symbol: Ticker symbol
        start_hour: Start hour in ET (4=pre-market, 9=market open)
        end_hour: End hour in ET (16=market close, 20=post-market)

    Returns: timestamp, open, high, low, close, volume for each minute.
    """
    if date == "today":
        date_str = datetime.now().strftime("%Y-%m-%d")
        filepath = os.path.join(config.minute_aggs_path, "today.parquet")
        if not os.path.exists(filepath):
            filepath = _find_file(config.minute_aggs_path, date_str)
    elif date == "yesterday":
        dt = datetime.now() - timedelta(days=1)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        date_str = dt.strftime("%Y-%m-%d")
        filepath = _find_file(config.minute_aggs_path, date_str)
    else:
        date_str = date
        filepath = _find_file(config.minute_aggs_path, date_str)

    if not filepath:
        return {"error": f"No minute data found for {date_str}"}

    conn = _get_duckdb()
    try:
        sql = f"""
        SELECT *,
               EXTRACT(HOUR FROM window_start AT TIME ZONE 'America/New_York') as hour_et
        FROM read_parquet('{filepath}')
        WHERE ticker = '{symbol.upper()}'
          AND EXTRACT(HOUR FROM window_start AT TIME ZONE 'America/New_York') >= {start_hour}
          AND EXTRACT(HOUR FROM window_start AT TIME ZONE 'America/New_York') < {end_hour}
        ORDER BY window_start
        """
        result = conn.execute(sql).fetchdf()
        # Convert timestamps to strings for serialization
        for col in result.select_dtypes(include=["datetime64"]).columns:
            result[col] = result[col].astype(str)
        records = result.to_dict(orient="records")
        return {"date": date_str, "symbol": symbol, "bars": records, "count": len(records)}
    finally:
        conn.close()


@mcp.tool()
async def get_top_movers(
    date: str,
    direction: str = "up",
    start_hour: int = 9,
    end_hour: int = 16,
    limit: int = 20,
    min_volume: int = 100000,
) -> dict:
    """Get top gaining or losing stocks for a specific date and time range.

    Args:
        date: 'today', 'yesterday', or 'YYYY-MM-DD'
        direction: 'up' (gainers) or 'down' (losers)
        start_hour: Start hour in ET
        end_hour: End hour in ET
        limit: Number of results
        min_volume: Minimum volume filter

    Returns: symbol, open_price, close_price, change_pct, volume
    """
    if date == "today":
        date_str = datetime.now().strftime("%Y-%m-%d")
    elif date == "yesterday":
        dt = datetime.now() - timedelta(days=1)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        date_str = dt.strftime("%Y-%m-%d")
    else:
        date_str = date

    filepath = _find_file(config.minute_aggs_path, date_str)
    if not filepath:
        filepath = _find_file(config.day_aggs_path, date_str)
        if not filepath:
            return {"error": f"No data for {date_str}"}
        # Use day aggs as fallback
        conn = _get_duckdb()
        try:
            order = "DESC" if direction == "up" else "ASC"
            sql = f"""
            SELECT ticker as symbol, open, close,
                   ROUND((close - open) / NULLIF(open, 0) * 100, 2) as change_pct,
                   volume
            FROM read_parquet('{filepath}')
            WHERE volume >= {min_volume} AND open > 0
            ORDER BY change_pct {order}
            LIMIT {limit}
            """
            result = conn.execute(sql).fetchdf()
            return {"date": date_str, "direction": direction, "movers": result.to_dict(orient="records")}
        finally:
            conn.close()

    conn = _get_duckdb()
    try:
        order = "DESC" if direction == "up" else "ASC"
        sql = f"""
        WITH bars AS (
            SELECT ticker,
                   FIRST(open) as open_price,
                   LAST(close) as close_price,
                   SUM(volume) as total_volume,
                   MAX(high) as high,
                   MIN(low) as low
            FROM read_parquet('{filepath}')
            WHERE EXTRACT(HOUR FROM window_start AT TIME ZONE 'America/New_York') >= {start_hour}
              AND EXTRACT(HOUR FROM window_start AT TIME ZONE 'America/New_York') < {end_hour}
            GROUP BY ticker
        )
        SELECT ticker as symbol, open_price, close_price,
               ROUND((close_price - open_price) / NULLIF(open_price, 0) * 100, 2) as change_pct,
               total_volume as volume, high, low
        FROM bars
        WHERE total_volume >= {min_volume} AND open_price > 0
        ORDER BY change_pct {order}
        LIMIT {limit}
        """
        result = conn.execute(sql).fetchdf()
        return {"date": date_str, "direction": direction, "movers": result.to_dict(orient="records")}
    finally:
        conn.close()


@mcp.tool()
async def available_dates() -> dict:
    """List all available dates with data files.
    Returns both day_aggs and minute_aggs available dates."""
    day_dates = []
    minute_dates = []

    if os.path.exists(config.day_aggs_path):
        for f in sorted(os.listdir(config.day_aggs_path)):
            if f.endswith((".parquet", ".csv.gz")):
                day_dates.append(f.split(".")[0])

    if os.path.exists(config.minute_aggs_path):
        for f in sorted(os.listdir(config.minute_aggs_path)):
            if f.endswith((".parquet", ".csv.gz")) and f != "today.parquet":
                minute_dates.append(f.split(".")[0])

    return {
        "day_aggs_dates": len(set(day_dates)),
        "minute_aggs_dates": len(set(minute_dates)),
        "latest_day": day_dates[-1] if day_dates else None,
        "earliest_day": day_dates[0] if day_dates else None,
        "latest_minute": minute_dates[-1] if minute_dates else None,
    }
