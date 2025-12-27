"""
DuckDB Screener Engine

High-performance analytical engine that queries parquet files directly.
Calculates all technical indicators using SQL window functions.
"""

import duckdb
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
import structlog

from ..indicators import register_all_indicators
from ..filters import FilterParser, FilterValidator
from config import settings

logger = structlog.get_logger(__name__)


class ScreenerEngine:
    """
    DuckDB-based screener engine
    
    Reads parquet files directly and calculates indicators on-the-fly
    using vectorized SQL operations.
    """
    
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or settings.data_path
        self.conn = duckdb.connect(":memory:")
        
        # Configure DuckDB for performance
        self.conn.execute(f"SET memory_limit='{settings.duckdb_memory_limit}'")
        self.conn.execute(f"SET threads={settings.duckdb_threads}")
        
        # Register indicators
        self.registry = register_all_indicators()
        self.parser = FilterParser(self.registry)
        self.validator = FilterValidator(self.registry)
        
        # Setup views
        self._setup_views()
        
        logger.info("screener_engine_initialized", data_path=str(self.data_path))
    
    def _setup_views(self):
        """Load CSV.GZ files into memory table for fast queries"""
        data_pattern = self.data_path / settings.daily_data_pattern
        
        # Check if files exist
        import glob
        import time
        files = glob.glob(str(data_pattern))
        if not files:
            logger.warning("no_data_files", path=str(data_pattern))
            # Create empty table for development
            self.conn.execute("""
                CREATE TABLE daily_prices (
                    symbol VARCHAR,
                    date DATE,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume BIGINT
                )
            """)
            return
        
        # Load data into memory TABLE (not VIEW) for fast queries
        # This takes ~30s at startup but queries are <100ms after
        logger.info("loading_data_into_memory", files_count=len(files))
        start = time.time()
        
        self.conn.execute(f"""
            CREATE TABLE daily_prices AS 
            SELECT 
                ticker as symbol,
                CAST(to_timestamp(window_start / 1000000000) AS DATE) as date,
                open,
                high,
                low,
                close,
                CAST(volume AS BIGINT) as volume
            FROM read_csv_auto('{data_pattern}', compression='gzip')
            WHERE to_timestamp(window_start / 1000000000) >= CURRENT_DATE - INTERVAL '{settings.default_lookback_days} days'
        """)
        
        # Create index for faster lookups
        self.conn.execute("CREATE INDEX idx_daily_symbol ON daily_prices(symbol)")
        self.conn.execute("CREATE INDEX idx_daily_date ON daily_prices(date)")
        
        count = self.conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        logger.info("raw_data_loaded", rows=count, elapsed_seconds=round(time.time() - start, 2))
        
        # Precompute indicators for fast queries
        logger.info("precomputing_indicators")
        self._precompute_indicators()
        
        elapsed = time.time() - start
        logger.info("data_loaded_into_memory", rows=count, elapsed_seconds=round(elapsed, 2))
    
    def _precompute_indicators(self):
        """Precompute all indicators into a materialized table at startup"""
        self._precompute_indicators_into("daily_prices", "screener_data")
        self.conn.execute("CREATE INDEX idx_screener_symbol ON screener_data(symbol)")
    
    def screen(
        self,
        filters: List[Dict[str, Any]],
        sort_by: str = "relative_volume",
        sort_order: str = "desc",
        limit: int = 50,
        symbols: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute screener query
        
        Args:
            filters: List of filter conditions
            sort_by: Field to sort by
            sort_order: 'asc' or 'desc'
            limit: Max results
        
        Returns:
            Dict with results, count, query_time_ms
        """
        start_time = time.time()
        
        # Validate filters
        is_valid, errors = self.validator.validate(filters)
        if not is_valid:
            return {
                "status": "error",
                "errors": errors,
                "results": [],
                "count": 0,
                "query_time_ms": 0,
            }
        
        # Build and execute query
        try:
            sql = self._build_query(filters, sort_by, sort_order, limit, symbols)
            logger.debug("executing_query", sql_length=len(sql))
            
            result = self.conn.execute(sql).fetchdf()
            
            # Convert to list of dicts
            results = result.to_dict(orient="records")
            
            query_time = (time.time() - start_time) * 1000
            
            return {
                "status": "ok",
                "results": results,
                "count": len(results),
                "total_matched": len(results),  # Could be more with pagination
                "query_time_ms": round(query_time, 2),
                "filters_applied": len(filters),
            }
            
        except Exception as e:
            logger.error("query_error", error=str(e))
            return {
                "status": "error",
                "errors": [str(e)],
                "results": [],
                "count": 0,
                "query_time_ms": (time.time() - start_time) * 1000,
            }
    
    def _build_query(
        self,
        filters: List[Dict[str, Any]],
        sort_by: str,
        sort_order: str,
        limit: int,
        symbols: List[str] = None
    ) -> str:
        """Build simple query against precomputed screener_data table"""
        
        # Parse filters to WHERE clause
        where_clause = self.parser.parse(filters)
        
        # Sort field - use column names from precomputed table
        valid_sort_fields = ['price', 'volume', 'change_1d', 'change_5d', 'change_20d', 
                            'gap_percent', 'relative_volume', 'rsi_14', 'atr_14', 
                            'atr_percent', 'from_52w_high', 'from_52w_low', 
                            'bb_width', 'bb_position', 'dist_sma_20', 'dist_sma_50']
        sort_field = sort_by if sort_by in valid_sort_fields else "volume"
        
        # Limit
        safe_limit = min(limit, settings.max_results)
        
        # Symbol filter
        if symbols and len(symbols) > 0:
            quoted_symbols = ", ".join(f"'{s.upper()}'" for s in symbols)
            symbols_filter = f"AND symbol IN ({quoted_symbols})"
        else:
            symbols_filter = ""
        
        # Simple query against precomputed table - ultra fast!
        query = f"""
        SELECT *
        FROM screener_data
        WHERE {where_clause}
          {symbols_filter}
        ORDER BY {sort_field} {sort_order.upper()} NULLS LAST
        LIMIT {safe_limit}
        """
        
        return query
    
    def refresh(self) -> Dict[str, Any]:
        """
        Hot refresh - recalculate all indicators without downtime.
        Called when new data arrives from polygon-data service.
        """
        import time
        start = time.time()
        
        logger.info("refresh_starting")
        
        try:
            # 1. Reload raw data from CSV files
            data_pattern = self.data_path / settings.daily_data_pattern
            
            self.conn.execute("DROP TABLE IF EXISTS daily_prices_new")
            self.conn.execute(f"""
                CREATE TABLE daily_prices_new AS 
                SELECT 
                    ticker as symbol,
                    CAST(to_timestamp(window_start / 1000000000) AS DATE) as date,
                    open,
                    high,
                    low,
                    close,
                    CAST(volume AS BIGINT) as volume
                FROM read_csv_auto('{data_pattern}', compression='gzip')
                WHERE to_timestamp(window_start / 1000000000) >= CURRENT_DATE - INTERVAL '{settings.default_lookback_days} days'
            """)
            
            # 2. Recompute indicators into new table
            self.conn.execute("DROP TABLE IF EXISTS screener_data_new")
            self._precompute_indicators_into("daily_prices_new", "screener_data_new")
            
            # 3. Atomic swap
            self.conn.execute("DROP TABLE IF EXISTS daily_prices_old")
            self.conn.execute("DROP TABLE IF EXISTS screener_data_old")
            self.conn.execute("ALTER TABLE daily_prices RENAME TO daily_prices_old")
            self.conn.execute("ALTER TABLE screener_data RENAME TO screener_data_old")
            self.conn.execute("ALTER TABLE daily_prices_new RENAME TO daily_prices")
            self.conn.execute("ALTER TABLE screener_data_new RENAME TO screener_data")
            self.conn.execute("DROP TABLE IF EXISTS daily_prices_old")
            self.conn.execute("DROP TABLE IF EXISTS screener_data_old")
            
            # 4. Recreate indexes
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_screener_symbol ON screener_data(symbol)")
            
            elapsed = time.time() - start
            count = self.conn.execute("SELECT COUNT(*) FROM screener_data").fetchone()[0]
            
            logger.info("refresh_completed", rows=count, elapsed_seconds=round(elapsed, 2))
            
            return {
                "status": "ok",
                "rows": count,
                "elapsed_seconds": round(elapsed, 2)
            }
            
        except Exception as e:
            logger.error("refresh_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
    
    def _precompute_indicators_into(self, source_table: str, target_table: str):
        """Precompute all indicators from source into target table"""
        self.conn.execute(f"""
            CREATE TABLE {target_table} AS
            WITH 
            price_base AS (
                SELECT 
                    symbol,
                    date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    LAG(close, 1) OVER w as prev_close,
                    LAG(close, 5) OVER w as close_5d_ago,
                    LAG(close, 20) OVER w as close_20d_ago,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 251 PRECEDING) as high_52w,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 251 PRECEDING) as low_52w,
                    AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as avg_volume_20,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as sma_20,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 49 PRECEDING) as sma_50,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 199 PRECEDING) as sma_200,
                    STDDEV(close) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as std_20
                FROM {source_table}
                WINDOW w AS (PARTITION BY symbol ORDER BY date)
            ),
            rsi_base AS (
                SELECT 
                    symbol, date, close, prev_close,
                    CASE WHEN close > prev_close THEN close - prev_close ELSE 0 END as gain,
                    CASE WHEN close < prev_close THEN prev_close - close ELSE 0 END as loss
                FROM price_base
                WHERE prev_close IS NOT NULL
            ),
            rsi_calc AS (
                SELECT 
                    symbol,
                    date,
                    100 - (100 / (1 + NULLIF(
                        AVG(gain) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING),
                    0) / NULLIF(AVG(loss) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING), 0.0001))) as rsi_14
                FROM rsi_base
            ),
            atr_calc AS (
                SELECT 
                    symbol,
                    date,
                    AVG(GREATEST(high - low, ABS(high - COALESCE(prev_close, open)), ABS(low - COALESCE(prev_close, open)))) 
                        OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) as atr_14
                FROM price_base
            ),
            latest_data AS (
                SELECT DISTINCT ON (p.symbol)
                    p.symbol,
                    p.date,
                    p.open,
                    p.close,
                    p.volume,
                    p.prev_close,
                    p.close_5d_ago,
                    p.close_20d_ago,
                    p.high_52w,
                    p.low_52w,
                    p.avg_volume_20,
                    p.sma_20,
                    p.sma_50,
                    p.sma_200,
                    p.std_20,
                    r.rsi_14,
                    a.atr_14
                FROM price_base p
                LEFT JOIN rsi_calc r ON p.symbol = r.symbol AND p.date = r.date
                LEFT JOIN atr_calc a ON p.symbol = a.symbol AND p.date = a.date
                WHERE p.date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY p.symbol, p.date DESC
            )
            SELECT 
                symbol,
                date,
                close as price,
                volume,
                ((close - prev_close) / NULLIF(prev_close, 0)) * 100 as change_1d,
                ((close - close_5d_ago) / NULLIF(close_5d_ago, 0)) * 100 as change_5d,
                ((close - close_20d_ago) / NULLIF(close_20d_ago, 0)) * 100 as change_20d,
                ((open - prev_close) / NULLIF(prev_close, 0)) * 100 as gap_percent,
                high_52w,
                low_52w,
                ((close - high_52w) / NULLIF(high_52w, 0)) * 100 as from_52w_high,
                ((close - low_52w) / NULLIF(low_52w, 0)) * 100 as from_52w_low,
                avg_volume_20,
                volume / NULLIF(avg_volume_20, 0) as relative_volume,
                sma_20,
                sma_50,
                sma_200,
                ((close - sma_20) / NULLIF(sma_20, 0)) * 100 as dist_sma_20,
                ((close - sma_50) / NULLIF(sma_50, 0)) * 100 as dist_sma_50,
                rsi_14,
                atr_14,
                (atr_14 / NULLIF(close, 0)) * 100 as atr_percent,
                sma_20 as bb_middle,
                sma_20 + 2 * std_20 as bb_upper,
                sma_20 - 2 * std_20 as bb_lower,
                ((4 * std_20) / NULLIF(sma_20, 0)) * 100 as bb_width,
                ((close - (sma_20 - 2 * std_20)) / NULLIF(4 * std_20, 0)) * 100 as bb_position
            FROM latest_data
            WHERE close IS NOT NULL AND volume > 0
        """)
    
    def get_indicators(self) -> Dict:
        """Get all available indicators"""
        return self.registry.to_dict()
    
    def get_stats(self) -> Dict:
        """Get engine statistics"""
        try:
            count = self.conn.execute("SELECT COUNT(DISTINCT symbol) FROM daily_prices").fetchone()[0]
            dates = self.conn.execute("SELECT MIN(date), MAX(date) FROM daily_prices").fetchone()
            return {
                "symbols_count": count,
                "date_range": {
                    "from": str(dates[0]) if dates[0] else None,
                    "to": str(dates[1]) if dates[1] else None,
                },
                "indicators_count": len(self.registry.get_all_indicators()),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("screener_engine_closed")

