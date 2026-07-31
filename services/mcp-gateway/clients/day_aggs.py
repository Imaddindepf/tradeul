"""
Daily OHLCV bars from the parquet flat files.

Lives here rather than inside one MCP server because more than one needs it:
the historical server serves the bars directly, and the earnings server needs
the open and the close of a report date to say how a stock actually moved that
session. Copying the DuckDB access into both is how two answers to the same
question start to disagree.

Files are end-of-day, so today's date has no file — callers wanting an
intraday figure read it from the live snapshot instead.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional

import duckdb

from config import config


def get_duckdb():
    conn = duckdb.connect(":memory:")
    conn.execute("SET threads=2")
    conn.execute("SET memory_limit='1GB'")
    return conn


def find_file(base_path: str, date_str: str) -> Optional[str]:
    parquet = os.path.join(base_path, f"{date_str}.parquet")
    if os.path.exists(parquet):
        return parquet
    csvgz = os.path.join(base_path, f"{date_str}.csv.gz")
    if os.path.exists(csvgz):
        return csvgz
    return None


def resolve_date(date: str) -> str:
    if date == "today":
        return datetime.now().strftime("%Y-%m-%d")
    if date == "yesterday":
        dt = datetime.now() - timedelta(days=1)
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        return dt.strftime("%Y-%m-%d")
    return date


def day_bars(date_str: str, symbols: list[str]) -> dict[str, dict]:
    """{TICKER: {open, high, low, close, volume}} for one session.

    Empty dict when there is no file for that date — an absent session is not
    an error, and the caller decides what to say about it.
    """
    if not symbols:
        return {}
    path = find_file(config.day_aggs_path, date_str)
    if not path:
        return {}

    wanted = ", ".join("'%s'" % s.upper().replace("'", "") for s in symbols)
    conn = get_duckdb()
    try:
        rows = conn.execute(
            f"SELECT ticker, open, high, low, close, volume "
            f"FROM read_parquet('{path}') WHERE ticker IN ({wanted})"
        ).fetchall()
    except Exception:
        return {}
    finally:
        conn.close()

    return {
        r[0]: {"open": r[1], "high": r[2], "low": r[3], "close": r[4], "volume": r[5]}
        for r in rows
    }


def open_to_close_pct(bar: dict) -> Optional[float]:
    """Apertura → cierre, en porcentaje. None si la apertura no es utilizable."""
    if not isinstance(bar, dict):
        return None
    o, c = bar.get("open"), bar.get("close")
    if not o or c is None:
        return None
    return round((c - o) / o * 100, 2)
