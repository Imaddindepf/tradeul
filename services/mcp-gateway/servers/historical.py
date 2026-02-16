"""
MCP Server: Historical Data
Access to 1760+ days of OHLCV data via DuckDB on Parquet flat files.

Actual parquet columns:
  day_aggs:    ticker, volume, open, close, high, low, window_start, transactions
  minute_aggs: ticker, volume, open, close, high, low, window_start (BIGINT epoch ms), transactions
  NOTE: no 'vwap' column. window_start in minute_aggs is epoch ms (BIGINT).
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
    "Minute-level and day-level granularity. Powered by DuckDB on Parquet flat files.",
)


def _get_duckdb():
    conn = duckdb.connect(":memory:")
    conn.execute("SET threads=2")
    conn.execute("SET memory_limit='1GB'")
    return conn


def _find_file(base_path: str, date_str: str) -> Optional[str]:
    parquet = os.path.join(base_path, f"{date_str}.parquet")
    if os.path.exists(parquet):
        return parquet
    csvgz = os.path.join(base_path, f"{date_str}.csv.gz")
    if os.path.exists(csvgz):
        return csvgz
    return None


def _resolve_date(date: str) -> str:
    if date == "today":
        return datetime.now().strftime("%Y-%m-%d")
    elif date == "yesterday":
        dt = datetime.now() - timedelta(days=1)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        return dt.strftime("%Y-%m-%d")
    return date


def _rows_to_dicts(cursor) -> list[dict]:
    """Convert DuckDB cursor to list of dicts without pandas/numpy."""
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(cols, row)) for row in rows]


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

    Returns: ticker, open, high, low, close, volume, transactions, change_pct
    """
    date_str = _resolve_date(date)
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
        SELECT ticker, open, high, low, close, volume, transactions,
               ROUND((close - open) / NULLIF(open, 0) * 100, 2) as change_pct
        FROM read_parquet('{filepath}')
        {where_clause}
        ORDER BY {sort_by} {sort_order}
        LIMIT {limit}
        """
        cursor = conn.execute(sql)
        records = _rows_to_dicts(cursor)
        return {"date": date_str, "bars": records, "count": len(records)}
    except Exception as e:
        return {"error": str(e), "date": date_str}
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
    date_str = _resolve_date(date)
    if date == "today":
        filepath = os.path.join(config.minute_aggs_path, "today.parquet")
        if not os.path.exists(filepath):
            filepath = _find_file(config.minute_aggs_path, date_str)
    else:
        filepath = _find_file(config.minute_aggs_path, date_str)

    if not filepath:
        return {"error": f"No minute data found for {date_str}"}

    conn = _get_duckdb()
    try:
        sql = f"""
        SELECT ticker, open, high, low, close, volume, transactions,
               window_start,
               EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York') as hour_et
        FROM read_parquet('{filepath}')
        WHERE ticker = '{symbol.upper()}'
          AND EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York') >= {start_hour}
          AND EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York') < {end_hour}
        ORDER BY window_start
        """
        cursor = conn.execute(sql)
        records = _rows_to_dicts(cursor)
        return {"date": date_str, "symbol": symbol, "bars": records, "count": len(records)}
    except Exception as e:
        return {"error": str(e), "date": date_str, "symbol": symbol}
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
    """Get top gaining or losing stocks for a specific date.

    Args:
        date: 'today', 'yesterday', or 'YYYY-MM-DD'
        direction: 'up' (gainers) or 'down' (losers)
        limit: Number of results
        min_volume: Minimum volume filter
    """
    date_str = _resolve_date(date)
    filepath = _find_file(config.day_aggs_path, date_str)
    if filepath:
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
            cursor = conn.execute(sql)
            records = _rows_to_dicts(cursor)
            return {"date": date_str, "direction": direction, "movers": records}
        except Exception as e:
            return {"error": str(e), "date": date_str}
        finally:
            conn.close()

    filepath = _find_file(config.minute_aggs_path, date_str)
    if not filepath:
        return {"error": f"No data for {date_str}"}

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
            WHERE EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York') >= {start_hour}
              AND EXTRACT(HOUR FROM to_timestamp(window_start / 1000000000) AT TIME ZONE 'America/New_York') < {end_hour}
            GROUP BY ticker
        )
        SELECT ticker as symbol, open_price as open, close_price as close,
               ROUND((close_price - open_price) / NULLIF(open_price, 0) * 100, 2) as change_pct,
               total_volume as volume, high, low
        FROM bars
        WHERE total_volume >= {min_volume} AND open_price > 0
        ORDER BY change_pct {order}
        LIMIT {limit}
        """
        cursor = conn.execute(sql)
        records = _rows_to_dicts(cursor)
        return {"date": date_str, "direction": direction, "movers": records}
    except Exception as e:
        return {"error": str(e), "date": date_str}
    finally:
        conn.close()


@mcp.tool()
async def available_dates() -> dict:
    """List all available dates with data files."""
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
