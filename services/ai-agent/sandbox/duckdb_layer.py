"""
DuckDB Data Layer for TradeUL Sandbox
=====================================

Provides clean, tested access to historical market data.
This module is injected into the sandbox environment.

Usage in sandbox:
    # Get after-hours data from yesterday
    df = get_minute_bars('2026-01-07', start_hour=16)
    
    # Get pre-market today
    df = get_minute_bars('today', start_hour=4, end_hour=9)
    
    # Complex SQL query
    df = historical_query('''
        SELECT symbol, SUM(volume) as vol
        FROM '/data/polygon/minute_aggs/2026-01-07.csv.gz'
        GROUP BY symbol
    ''')
"""

import duckdb
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union, List
import pytz

# Constants
DATA_PATH = Path('/data/polygon')
MINUTE_AGGS_PATH = DATA_PATH / 'minute_aggs'
DAY_AGGS_PATH = DATA_PATH / 'day_aggs'
ET = pytz.timezone('America/New_York')


class MarketDataDB:
    """
    Clean interface to historical market data via DuckDB.
    
    All data is read-only. Queries are executed directly on CSV.gz/Parquet files
    without loading them entirely into memory.
    """
    
    def __init__(self):
        self._conn = duckdb.connect(':memory:')
    
    def _resolve_date(self, date_str: str) -> str:
        """Convert date string to file path."""
        now = datetime.now(ET)
        
        if date_str == 'today':
            return str(MINUTE_AGGS_PATH / 'today.parquet')
        elif date_str == 'yesterday':
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            return str(MINUTE_AGGS_PATH / f'{yesterday}.csv.gz')
        else:
            # Assume YYYY-MM-DD format
            return str(MINUTE_AGGS_PATH / f'{date_str}.csv.gz')
    
    def _get_read_function(self, file_path: str) -> str:
        """Get appropriate DuckDB read function for file type."""
        if file_path.endswith('.parquet'):
            return f"read_parquet('{file_path}')"
        else:
            return f"read_csv_auto('{file_path}')"
    
    def get_minute_bars(
        self,
        date_str: str,
        symbol: Optional[str] = None,
        start_hour: Optional[int] = None,
        end_hour: Optional[int] = None,
        min_volume: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Get minute bars for a specific date.
        
        Args:
            date_str: 'today', 'yesterday', or 'YYYY-MM-DD'
            symbol: Optional ticker filter (e.g., 'AAPL')
            start_hour: Optional start hour (0-23)
            end_hour: Optional end hour (0-23), exclusive
            min_volume: Optional minimum volume filter
        
        Returns:
            DataFrame with columns: symbol, datetime, open, high, low, close, volume
        
        Examples:
            # After-hours yesterday (4pm-8pm)
            df = db.get_minute_bars('yesterday', start_hour=16, end_hour=20)
            
            # Pre-market today (4am-9:30am)
            df = db.get_minute_bars('today', start_hour=4, end_hour=10)
            
            # Specific ticker
            df = db.get_minute_bars('2026-01-07', symbol='AAPL')
        """
        file_path = self._resolve_date(date_str)
        read_func = self._get_read_function(file_path)
        is_parquet = file_path.endswith('.parquet')
        
        # Column name differs: parquet uses 'symbol', CSV uses 'ticker'
        symbol_col = "symbol" if is_parquet else "ticker"
        
        # Timestamp divisor: parquet is milliseconds (1e3), CSV is nanoseconds (1e9)
        ts_divisor = "1000" if is_parquet else "1000000000"
        
        # Build WHERE conditions
        conditions = []
        
        if symbol:
            conditions.append(f"{symbol_col} = '{symbol}'")
        
        if start_hour is not None:
            conditions.append(f"EXTRACT(HOUR FROM to_timestamp(window_start/{ts_divisor})) >= {start_hour}")
        
        if end_hour is not None:
            conditions.append(f"EXTRACT(HOUR FROM to_timestamp(window_start/{ts_divisor})) < {end_hour}")
        
        if min_volume is not None:
            conditions.append(f"volume >= {min_volume}")
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        sql = f"""
            SELECT 
                {symbol_col} as symbol,
                to_timestamp(window_start/{ts_divisor}) as datetime,
                open, high, low, close, volume
            FROM {read_func}
            {where_clause}
            ORDER BY {symbol_col}, window_start
        """
        
        try:
            return self._conn.execute(sql).df()
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return pd.DataFrame()
    
    def get_top_movers(
        self,
        date_str: str,
        start_hour: Optional[int] = None,
        end_hour: Optional[int] = None,
        min_volume: int = 100000,
        min_bars: int = 5,
        limit: int = 20,
        ascending: bool = False
    ) -> pd.DataFrame:
        """
        Get top movers (gainers or losers) for a time period.
        
        Args:
            date_str: 'today', 'yesterday', or 'YYYY-MM-DD'
            start_hour: Optional start hour (0-23)
            end_hour: Optional end hour (0-23), exclusive
            min_volume: Minimum total volume (default 100k)
            min_bars: Minimum number of bars for statistical validity (default 5)
            limit: Number of results (default 20)
            ascending: If True, return losers instead of gainers
        
        Returns:
            DataFrame with: symbol, open_price, close_price, change_pct, volume, num_bars
        
        Examples:
            # Top after-hours gainers yesterday
            df = db.get_top_movers('yesterday', start_hour=16, end_hour=20)
            
            # Top losers in regular session
            df = db.get_top_movers('2026-01-07', start_hour=9, end_hour=16, ascending=True)
        """
        file_path = self._resolve_date(date_str)
        read_func = self._get_read_function(file_path)
        is_parquet = file_path.endswith('.parquet')
        
        # Column name differs: parquet uses 'symbol', CSV uses 'ticker'
        symbol_col = "symbol" if is_parquet else "ticker"
        
        # Timestamp divisor: parquet is milliseconds (1e3), CSV is nanoseconds (1e9)
        ts_divisor = "1000" if is_parquet else "1000000000"
        
        # Build WHERE conditions for time filter
        conditions = []
        if start_hour is not None:
            conditions.append(f"EXTRACT(HOUR FROM to_timestamp(window_start/{ts_divisor})) >= {start_hour}")
        if end_hour is not None:
            conditions.append(f"EXTRACT(HOUR FROM to_timestamp(window_start/{ts_divisor})) < {end_hour}")
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        order_dir = "ASC" if ascending else "DESC"
        
        sql = f"""
            SELECT 
                {symbol_col} as symbol,
                FIRST(open ORDER BY window_start) as open_price,
                LAST(close ORDER BY window_start) as close_price,
                ROUND((LAST(close ORDER BY window_start) - FIRST(open ORDER BY window_start)) 
                      / NULLIF(FIRST(open ORDER BY window_start), 0) * 100, 2) as change_pct,
                SUM(volume) as volume,
                COUNT(*) as num_bars
            FROM {read_func}
            {where_clause}
            GROUP BY {symbol_col}
            HAVING SUM(volume) >= {min_volume} AND COUNT(*) >= {min_bars}
            ORDER BY change_pct {order_dir}
            LIMIT {limit}
        """
        
        try:
            return self._conn.execute(sql).df()
        except Exception as e:
            print(f"Error: {e}")
            return pd.DataFrame()
    
    def query(self, sql: str) -> pd.DataFrame:
        """
        Execute raw SQL query on historical data.
        
        The SQL can reference files directly:
            '/data/polygon/minute_aggs/2026-01-07.csv.gz'
            '/data/polygon/minute_aggs/today.parquet'
            '/data/polygon/minute_aggs/2026-01-*.csv.gz'  (glob pattern)
        
        Example:
            df = db.query('''
                SELECT ticker, AVG(volume) as avg_vol
                FROM '/data/polygon/minute_aggs/2026-01-*.csv.gz'
                WHERE EXTRACT(HOUR FROM to_timestamp(window_start/1000000)) BETWEEN 9 AND 16
                GROUP BY ticker
                ORDER BY avg_vol DESC
                LIMIT 50
            ''')
        """
        try:
            return self._conn.execute(sql).df()
        except Exception as e:
            print(f"Query error: {e}")
            return pd.DataFrame()
    
    def available_dates(self) -> List[str]:
        """List available dates in minute_aggs (excluding today.parquet)."""
        if not MINUTE_AGGS_PATH.exists():
            return []
        
        files = list(MINUTE_AGGS_PATH.glob('*.csv.gz'))
        # Extract YYYY-MM-DD from filename (stem removes .csv.gz -> YYYY-MM-DD.csv, need to remove .csv too)
        dates = sorted([f.stem.replace('.csv', '') for f in files])
        
        # Check if today.parquet exists
        if (MINUTE_AGGS_PATH / 'today.parquet').exists():
            dates.append('today')
        
        return dates
    
    def file_exists(self, date_str: str) -> bool:
        """Check if data file exists for a date."""
        file_path = Path(self._resolve_date(date_str))
        return file_path.exists()


# =============================================================================
# CONVENIENCE FUNCTIONS (Injected into sandbox global scope)
# =============================================================================

# Global instance
_db = MarketDataDB()


def get_minute_bars(date_str: str, symbol: str = None, start_hour: int = None, 
                    end_hour: int = None, min_volume: int = None) -> pd.DataFrame:
    """
    Get minute bars for a specific date.
    
    Args:
        date_str: 'today', 'yesterday', or 'YYYY-MM-DD'
        symbol: Optional ticker filter
        start_hour: Optional start hour (0-23)
        end_hour: Optional end hour (0-23)
        min_volume: Optional minimum volume filter
    
    Examples:
        # After-hours yesterday
        df = get_minute_bars('yesterday', start_hour=16)
        
        # Pre-market today
        df = get_minute_bars('today', start_hour=4, end_hour=10)
        
        # Specific ticker all day
        df = get_minute_bars('2026-01-07', symbol='AAPL')
    """
    return _db.get_minute_bars(date_str, symbol, start_hour, end_hour, min_volume)


def get_top_movers(date_str: str, start_hour: int = None, end_hour: int = None,
                   min_volume: int = 100000, limit: int = 20, ascending: bool = False) -> pd.DataFrame:
    """
    Get top movers (gainers or losers) for a time period.
    
    Args:
        date_str: 'today', 'yesterday', or 'YYYY-MM-DD'
        start_hour: Optional start hour (0-23)
        end_hour: Optional end hour (0-23)
        min_volume: Minimum volume (default 100k)
        limit: Number of results (default 20)
        ascending: If True, return losers instead of gainers
    
    Examples:
        # Top after-hours gainers yesterday
        df = get_top_movers('yesterday', start_hour=16)
        
        # Top losers in regular session
        df = get_top_movers('2026-01-07', start_hour=9, end_hour=16, ascending=True)
    """
    return _db.get_top_movers(date_str, start_hour, end_hour, min_volume, 5, limit, ascending)


def historical_query(sql: str) -> pd.DataFrame:
    """
    Execute raw SQL on historical data files.
    
    Files can be referenced directly in SQL:
        '/data/polygon/minute_aggs/2026-01-07.csv.gz'
        '/data/polygon/minute_aggs/today.parquet'
        '/data/polygon/minute_aggs/2026-01-*.csv.gz'  (glob for multiple days)
    
    Example:
        df = historical_query('''
            SELECT ticker as symbol, SUM(volume) as total_vol
            FROM '/data/polygon/minute_aggs/2026-01-07.csv.gz'
            WHERE EXTRACT(HOUR FROM to_timestamp(window_start/1000000)) >= 16
            GROUP BY ticker
            ORDER BY total_vol DESC
            LIMIT 20
        ''')
    """
    return _db.query(sql)


def available_dates() -> List[str]:
    """List available dates for historical data."""
    return _db.available_dates()

