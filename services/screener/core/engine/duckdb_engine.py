"""
DuckDB Screener Engine

High-performance analytical engine that queries parquet files directly.
Calculates all technical indicators using SQL window functions.
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
import structlog

from ..indicators import register_all_indicators
from ..filters import FilterParser, FilterValidator
from .dynamic_indicators import extract_custom_indicators, build_hybrid_query, is_precomputed
from config import settings

logger = structlog.get_logger(__name__)

# Ruta al archivo de metadata exportado por data_maintenance (Parquet = más eficiente)
METADATA_PATH = "/data/polygon/screener_metadata.parquet"


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
        
        # Load metadata first (market_cap, float, sector)
        self._load_metadata()
        
        # Setup views (includes precompute with JOIN to metadata)
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
            FROM read_parquet('{data_pattern}')
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
    
    def _load_metadata(self):
        """Load metadata from Parquet file (market_cap, float, sector)"""
        import os
        
        if not os.path.exists(METADATA_PATH):
            logger.warning("metadata_file_not_found", path=METADATA_PATH)
            # Create empty metadata table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    symbol VARCHAR PRIMARY KEY,
                    market_cap BIGINT,
                    free_float BIGINT,
                    sector VARCHAR,
                    industry VARCHAR
                )
            """)
            return
        
        try:
            self.conn.execute("DROP TABLE IF EXISTS metadata")
            self.conn.execute(f"""
                CREATE TABLE metadata AS 
                SELECT * FROM read_parquet('{METADATA_PATH}')
            """)
            self.conn.execute("CREATE INDEX idx_metadata_symbol ON metadata(symbol)")
            
            count = self.conn.execute("SELECT COUNT(*) FROM metadata").fetchone()[0]
            logger.info("metadata_loaded", rows=count, path=METADATA_PATH)
        except Exception as e:
            logger.error("metadata_load_failed", error=str(e))
            # Create empty table as fallback
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    symbol VARCHAR PRIMARY KEY,
                    market_cap BIGINT,
                    free_float BIGINT,
                    sector VARCHAR,
                    industry VARCHAR
                )
            """)
    
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
        Execute screener query with support for dynamic indicator parameters.
        
        Args:
            filters: List of filter conditions. Each can optionally include 'params':
                     {"field": "sma", "operator": "gt", "value": 50, "params": {"period": 10}}
            sort_by: Field to sort by
            sort_order: 'asc' or 'desc'
            limit: Max results
        
        Returns:
            Dict with results, count, query_time_ms
        """
        start_time = time.time()
        
        # Validate filters (strip params for validation)
        filters_for_validation = [
            {k: v for k, v in f.items() if k != 'params'}
            for f in filters
        ]
        is_valid, errors = self.validator.validate(filters_for_validation)
        if not is_valid:
            return {
                "status": "error",
                "errors": errors,
                "results": [],
                "count": 0,
                "query_time_ms": 0,
            }
        
        # Check for custom indicator parameters
        custom_indicators = extract_custom_indicators(filters)
        use_hybrid = len(custom_indicators) > 0
        
        # Build and execute query
        try:
            if use_hybrid:
                # Use hybrid query with dynamic calculation
                sql = self._build_hybrid_query(filters, custom_indicators, sort_by, sort_order, limit, symbols)
                logger.info("executing_hybrid_query", custom_indicators=len(custom_indicators))
            else:
                # Use fast precomputed query
                sql = self._build_query(filters, sort_by, sort_order, limit, symbols)
            
            logger.debug("executing_query", sql_length=len(sql), hybrid=use_hybrid)
            
            result = self.conn.execute(sql).fetchdf()
            
            # Convert to list of dicts
            results = result.to_dict(orient="records")
            
            query_time = (time.time() - start_time) * 1000
            
            return {
                "status": "ok",
                "results": results,
                "count": len(results),
                "total_matched": len(results),
                "query_time_ms": round(query_time, 2),
                "filters_applied": len(filters),
                "dynamic_indicators": len(custom_indicators),
            }
            
        except Exception as e:
            logger.error("query_error", error=str(e), hybrid=use_hybrid)
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
        
        # Sort field - all numeric columns in screener_data
        valid_sort_fields = [
            'price', 'volume', 'change_1d', 'change_3d', 'change_5d',
            'change_10d', 'change_20d', 'gap_percent',
            'high_52w', 'low_52w', 'from_52w_high', 'from_52w_low',
            'avg_volume_5', 'avg_volume_10', 'avg_volume_20', 'avg_volume_63', 'relative_volume',
            'sma_20', 'sma_50', 'sma_200', 'dist_sma_20', 'dist_sma_50',
            'rsi_14', 'atr_14', 'atr_percent',
            'bb_width', 'bb_position', 'squeeze_momentum',
            'keltner_upper', 'keltner_lower',
            'adx_14', 'plus_di_14', 'minus_di_14',
            'market_cap', 'free_float',
        ]
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
    
    def _build_hybrid_query(
        self,
        filters: List[Dict[str, Any]],
        custom_indicators: List[Dict[str, Any]],
        sort_by: str,
        sort_order: str,
        limit: int,
        symbols: List[str] = None
    ) -> str:
        """
        Build hybrid query that joins precomputed data with dynamically calculated indicators.
        Used when user requests non-standard indicator periods.
        """
        # Parse filters without params for base WHERE clause
        filters_clean = [{k: v for k, v in f.items() if k != 'params'} for f in filters]
        base_where = self.parser.parse(filters_clean)
        
        # Sort field validation (same as _build_query)
        valid_sort_fields = [
            'price', 'volume', 'change_1d', 'change_3d', 'change_5d',
            'change_10d', 'change_20d', 'gap_percent',
            'high_52w', 'low_52w', 'from_52w_high', 'from_52w_low',
            'avg_volume_5', 'avg_volume_10', 'avg_volume_20', 'avg_volume_63', 'relative_volume',
            'sma_20', 'sma_50', 'sma_200', 'dist_sma_20', 'dist_sma_50',
            'rsi_14', 'atr_14', 'atr_percent',
            'bb_width', 'bb_position', 'squeeze_momentum',
            'keltner_upper', 'keltner_lower',
            'adx_14', 'plus_di_14', 'minus_di_14',
            'market_cap', 'free_float',
        ]
        sort_field = sort_by if sort_by in valid_sort_fields else "volume"
        
        # Limit
        safe_limit = min(limit, settings.max_results)
        
        # Symbol filter
        symbols_filter = ""
        if symbols and len(symbols) > 0:
            quoted_symbols = ", ".join(f"'{s.upper()}'" for s in symbols)
            symbols_filter = f"AND s.symbol IN ({quoted_symbols})"
        
        # Build CTE for dynamic indicators
        return build_hybrid_query(
            base_where=base_where,
            custom_indicators=custom_indicators,
            sort_by=sort_field,
            sort_order=sort_order,
            limit=safe_limit,
            symbols_filter=symbols_filter
        )
    
    def refresh(self) -> Dict[str, Any]:
        """
        Hot refresh - recalculate all indicators without downtime.
        Called when new data arrives from polygon-data service.
        """
        import time
        start = time.time()
        
        logger.info("refresh_starting")
        
        try:
            # 1. Reload raw data from parquet files into new tables
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
                FROM read_parquet('{data_pattern}')
                WHERE to_timestamp(window_start / 1000000000) >= CURRENT_DATE - INTERVAL '{settings.default_lookback_days} days'
            """)
            
            # 2. Reload metadata
            self._load_metadata()
            
            # 3. Recompute indicators into new table
            self.conn.execute("DROP TABLE IF EXISTS screener_data_new")
            self._precompute_indicators_into("daily_prices_new", "screener_data_new")
            
            # 3. Drop old tables and indexes
            self.conn.execute("DROP INDEX IF EXISTS idx_screener_symbol")
            self.conn.execute("DROP TABLE IF EXISTS screener_data")
            self.conn.execute("DROP INDEX IF EXISTS idx_daily_symbol")
            self.conn.execute("DROP INDEX IF EXISTS idx_daily_date")
            self.conn.execute("DROP TABLE IF EXISTS daily_prices")
            
            # 4. Rename new tables to production names
            self.conn.execute("ALTER TABLE daily_prices_new RENAME TO daily_prices")
            self.conn.execute("ALTER TABLE screener_data_new RENAME TO screener_data")
            
            # 5. Create indexes on renamed tables
            self.conn.execute("CREATE INDEX idx_daily_symbol ON daily_prices(symbol)")
            self.conn.execute("CREATE INDEX idx_daily_date ON daily_prices(date)")
            self.conn.execute("CREATE INDEX idx_screener_symbol ON screener_data(symbol)")
            
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
                    LAG(high, 1) OVER w as prev_high,
                    LAG(low, 1) OVER w as prev_low,
                    LAG(close, 3) OVER w as close_3d_ago,
                    LAG(close, 5) OVER w as close_5d_ago,
                    LAG(close, 10) OVER w as close_10d_ago,
                    LAG(close, 20) OVER w as close_20d_ago,
                    LAG(close, 251) OVER w as close_252d_ago,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 4 PRECEDING) as high_5d,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 4 PRECEDING) as low_5d,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 9 PRECEDING) as high_10d,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 9 PRECEDING) as low_10d,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as high_20d,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as low_20d,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 62 PRECEDING) as high_3m,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 62 PRECEDING) as low_3m,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 125 PRECEDING) as high_6m,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 125 PRECEDING) as low_6m,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 188 PRECEDING) as high_9m,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 188 PRECEDING) as low_9m,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 251 PRECEDING) as high_52w,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 251 PRECEDING) as low_52w,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS 503 PRECEDING) as high_2y,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS 503 PRECEDING) as low_2y,
                    MAX(high) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as high_all,
                    MIN(low) OVER (PARTITION BY symbol ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) as low_all,
                    AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS 4 PRECEDING) as avg_volume_5,
                    AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS 9 PRECEDING) as avg_volume_10,
                    AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as avg_volume_20,
                    AVG(volume) OVER (PARTITION BY symbol ORDER BY date ROWS 62 PRECEDING) as avg_volume_63,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 4 PRECEDING) as sma_5,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 7 PRECEDING) as sma_8,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 9 PRECEDING) as sma_10,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as sma_20,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 49 PRECEDING) as sma_50,
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 199 PRECEDING) as sma_200,
                    STDDEV(close) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as std_20,
                    STDDEV(close) OVER (PARTITION BY symbol ORDER BY date ROWS 251 PRECEDING) as std_252,
                    -- EMA approximation using weighted average (good enough for Keltner)
                    AVG(close) OVER (PARTITION BY symbol ORDER BY date ROWS 19 PRECEDING) as ema_20
                FROM {source_table}
                WINDOW w AS (PARTITION BY symbol ORDER BY date)
            ),
            atr_calc AS (
                SELECT 
                    symbol,
                    date,
                    AVG(GREATEST(high - low, ABS(high - COALESCE(prev_close, open)), ABS(low - COALESCE(prev_close, open)))) 
                        OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) as atr_14,
                    -- ATR 10 for Keltner Channels
                    AVG(GREATEST(high - low, ABS(high - COALESCE(prev_close, open)), ABS(low - COALESCE(prev_close, open)))) 
                        OVER (PARTITION BY symbol ORDER BY date ROWS 9 PRECEDING) as atr_10
                FROM price_base
            ),
            -- ADX calculation: +DM, -DM, +DI, -DI, DX, ADX
            dm_calc AS (
                SELECT 
                    symbol, date,
                    CASE WHEN (high - prev_high) > (prev_low - low) AND (high - prev_high) > 0 
                         THEN high - prev_high ELSE 0 END as plus_dm,
                    CASE WHEN (prev_low - low) > (high - prev_high) AND (prev_low - low) > 0 
                         THEN prev_low - low ELSE 0 END as minus_dm,
                    GREATEST(high - low, ABS(high - COALESCE(prev_close, open)), ABS(low - COALESCE(prev_close, open))) as tr
                FROM price_base
                WHERE prev_close IS NOT NULL
            ),
            di_calc AS (
                SELECT 
                    symbol, date,
                    (AVG(plus_dm) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) / 
                     NULLIF(AVG(tr) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING), 0)) * 100 as plus_di_14,
                    (AVG(minus_dm) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) / 
                     NULLIF(AVG(tr) OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING), 0)) * 100 as minus_di_14
                FROM dm_calc
            ),
            adx_calc AS (
                SELECT 
                    symbol, date,
                    plus_di_14,
                    minus_di_14,
                    AVG(ABS(plus_di_14 - minus_di_14) / NULLIF(plus_di_14 + minus_di_14, 0) * 100) 
                        OVER (PARTITION BY symbol ORDER BY date ROWS 13 PRECEDING) as adx_14
                FROM di_calc
            ),
            latest_data AS (
                SELECT DISTINCT ON (p.symbol)
                    p.symbol,
                    p.date,
                    p.open,
                    p.close,
                    p.volume,
                    p.prev_close,
                    p.close_3d_ago,
                    p.close_5d_ago,
                    p.close_10d_ago,
                    p.close_20d_ago,
                    p.close_252d_ago,
                    p.high_5d,
                    p.low_5d,
                    p.high_10d,
                    p.low_10d,
                    p.high_20d,
                    p.low_20d,
                    p.high_3m,
                    p.low_3m,
                    p.high_6m,
                    p.low_6m,
                    p.high_9m,
                    p.low_9m,
                    p.high_52w,
                    p.low_52w,
                    p.high_2y,
                    p.low_2y,
                    p.high_all,
                    p.low_all,
                    p.avg_volume_5,
                    p.avg_volume_10,
                    p.avg_volume_20,
                    p.avg_volume_63,
                    p.sma_5,
                    p.sma_8,
                    p.sma_10,
                    p.sma_20,
                    p.sma_50,
                    p.sma_200,
                    p.std_20,
                    p.std_252,
                    p.ema_20,
                    a.atr_14,
                    a.atr_10,
                    x.plus_di_14,
                    x.minus_di_14,
                    x.adx_14
                FROM price_base p
                LEFT JOIN atr_calc a ON p.symbol = a.symbol AND p.date = a.date
                LEFT JOIN adx_calc x ON p.symbol = x.symbol AND p.date = x.date
                WHERE p.date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY p.symbol, p.date DESC
            )
            SELECT 
                d.symbol,
                d.date,
                d.close as price,
                d.volume,
                ((d.close - d.prev_close) / NULLIF(d.prev_close, 0)) * 100 as change_1d,
                ((d.close - d.close_3d_ago) / NULLIF(d.close_3d_ago, 0)) * 100 as change_3d,
                ((d.close - d.close_5d_ago) / NULLIF(d.close_5d_ago, 0)) * 100 as change_5d,
                ((d.close - d.close_10d_ago) / NULLIF(d.close_10d_ago, 0)) * 100 as change_10d,
                ((d.close - d.close_20d_ago) / NULLIF(d.close_20d_ago, 0)) * 100 as change_20d,
                d.close - d.close_5d_ago as change_5d_dollars,
                d.close - d.close_10d_ago as change_10d_dollars,
                d.close - d.close_20d_ago as change_20d_dollars,
                ((d.close - d.close_252d_ago) / NULLIF(d.close_252d_ago, 0)) * 100 as change_1y,
                d.close - d.close_252d_ago as change_1y_dollars,
                ((d.open - d.prev_close) / NULLIF(d.prev_close, 0)) * 100 as gap_percent,
                d.high_5d,
                d.low_5d,
                d.high_5d - d.low_5d as range_5d,
                d.high_10d,
                d.low_10d,
                d.high_10d - d.low_10d as range_10d,
                d.high_20d,
                d.low_20d,
                d.high_20d - d.low_20d as range_20d,
                d.high_3m,
                d.low_3m,
                d.high_6m,
                d.low_6m,
                d.high_9m,
                d.low_9m,
                d.high_52w,
                d.low_52w,
                d.high_2y,
                d.low_2y,
                d.high_all,
                d.low_all,
                ((d.close - d.high_52w) / NULLIF(d.high_52w, 0)) * 100 as from_52w_high,
                ((d.close - d.low_52w) / NULLIF(d.low_52w, 0)) * 100 as from_52w_low,
                d.avg_volume_5,
                d.avg_volume_10,
                d.avg_volume_20,
                d.avg_volume_63,
                d.volume / NULLIF(d.avg_volume_20, 0) as relative_volume,
                d.sma_5,
                d.sma_8,
                d.sma_10,
                d.sma_20,
                d.sma_50,
                d.sma_200,
                ((d.close - d.sma_5) / NULLIF(d.sma_5, 0)) * 100 as dist_sma_5,
                ((d.close - d.sma_8) / NULLIF(d.sma_8, 0)) * 100 as dist_sma_8,
                ((d.close - d.sma_10) / NULLIF(d.sma_10, 0)) * 100 as dist_sma_10,
                ((d.close - d.sma_20) / NULLIF(d.sma_20, 0)) * 100 as dist_sma_20,
                ((d.close - d.sma_50) / NULLIF(d.sma_50, 0)) * 100 as dist_sma_50,
                ((d.close - d.sma_200) / NULLIF(d.sma_200, 0)) * 100 as dist_sma_200,
                d.std_252 as yearly_std_dev,
                NULL as rsi_14,
                d.atr_14,
                (d.atr_14 / NULLIF(d.close, 0)) * 100 as atr_percent,
                -- Bollinger Bands
                d.sma_20 as bb_middle,
                d.sma_20 + 2 * d.std_20 as bb_upper,
                d.sma_20 - 2 * d.std_20 as bb_lower,
                ((4 * d.std_20) / NULLIF(d.sma_20, 0)) * 100 as bb_width,
                ((d.close - (d.sma_20 - 2 * d.std_20)) / NULLIF(4 * d.std_20, 0)) * 100 as bb_position,
                -- Keltner Channels (EMA 20 + ATR 10 * 1.5)
                d.ema_20 as keltner_middle,
                d.ema_20 + 1.5 * d.atr_10 as keltner_upper,
                d.ema_20 - 1.5 * d.atr_10 as keltner_lower,
                -- TTM Squeeze: BB inside Keltner = squeeze ON (low volatility, breakout coming)
                CASE WHEN (d.sma_20 - 2 * d.std_20) > (d.ema_20 - 1.5 * d.atr_10) 
                      AND (d.sma_20 + 2 * d.std_20) < (d.ema_20 + 1.5 * d.atr_10)
                     THEN 1 ELSE 0 END as squeeze_on,
                -- Squeeze momentum (simplified): price vs middle band
                ((d.close - d.sma_20) / NULLIF(d.std_20, 0)) as squeeze_momentum,
                -- ADX (trend strength)
                d.adx_14,
                d.plus_di_14,
                d.minus_di_14,
                -- ADX trend direction
                CASE WHEN d.adx_14 > 25 AND d.plus_di_14 > d.minus_di_14 THEN 1
                     WHEN d.adx_14 > 25 AND d.minus_di_14 > d.plus_di_14 THEN -1
                     ELSE 0 END as adx_trend,
                m.market_cap,
                m.free_float,
                m.sector
            FROM latest_data d
            LEFT JOIN metadata m ON d.symbol = m.symbol
            WHERE d.close IS NOT NULL AND d.volume > 0
        """)

        self._compute_rsi_wilder(source_table, target_table)
        self._compute_consecutive_days(source_table, target_table)
        self._compute_change_since_jan1(source_table, target_table)
        self._compute_consolidation(source_table, target_table)
        self._compute_linear_regression(source_table, target_table)

    def _compute_consecutive_days(self, source_table: str, target_table: str):
        """Compute consecutive days up/down [Up] — Trade Ideas parity."""
        df = self.conn.execute(f"""
            SELECT symbol, date, close
            FROM {source_table}
            WHERE close IS NOT NULL
            ORDER BY symbol, date
        """).fetchdf()

        if df.empty:
            return

        df['prev_close'] = df.groupby('symbol')['close'].shift(1)
        df['up'] = (df['close'] > df['prev_close']).astype(int)
        df['down'] = (df['close'] < df['prev_close']).astype(int)

        def streak(series):
            result = []
            count = 0
            for val in series:
                if val:
                    count += 1
                else:
                    count = 0
                result.append(count)
            return result

        df['consec_up'] = df.groupby('symbol')['up'].transform(streak)
        df['consec_down'] = df.groupby('symbol')['down'].transform(streak)
        df['consecutive_days_up'] = df['consec_up'] - df['consec_down']

        latest = df.sort_values('date').groupby('symbol').tail(1)[['symbol', 'consecutive_days_up']]

        if latest.empty:
            return

        self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS consecutive_days_up INTEGER")
        self.conn.register('_consec_update', latest)
        self.conn.execute(f"""
            UPDATE {target_table} t
            SET consecutive_days_up = r.consecutive_days_up
            FROM _consec_update r
            WHERE t.symbol = r.symbol
        """)
        self.conn.unregister('_consec_update')
        logger.info("consecutive_days_computed", symbols=len(latest))

    def _compute_change_since_jan1(self, source_table: str, target_table: str):
        """Compute change since January 1 [UpJan1D/UpJan1P]."""
        try:
            jan1_df = self.conn.execute(f"""
                WITH jan1_close AS (
                    SELECT DISTINCT ON (symbol) symbol, close as jan1_close
                    FROM {source_table}
                    WHERE date >= DATE_TRUNC('year', CURRENT_DATE) - INTERVAL '7 days'
                      AND date < DATE_TRUNC('year', CURRENT_DATE)
                      AND close IS NOT NULL
                    ORDER BY symbol, date DESC
                )
                SELECT symbol, jan1_close FROM jan1_close
            """).fetchdf()

            if jan1_df.empty:
                return

            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS change_ytd DOUBLE")
            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS change_ytd_dollars DOUBLE")
            self.conn.register('_jan1_update', jan1_df)
            self.conn.execute(f"""
                UPDATE {target_table} t
                SET change_ytd = ((t.price - r.jan1_close) / NULLIF(r.jan1_close, 0)) * 100,
                    change_ytd_dollars = t.price - r.jan1_close
                FROM _jan1_update r
                WHERE t.symbol = r.symbol
            """)
            self.conn.unregister('_jan1_update')
            logger.info("change_ytd_computed", symbols=len(jan1_df))
        except Exception as e:
            logger.error("change_ytd_failed", error=str(e))

    def _compute_consolidation(self, source_table: str, target_table: str):
        """Compute Consolidation Days [ConDays], Range Contraction [RC],
        consolidation_high/low for Position in Consolidation [RCon].

        Sqrt-scaling ATR algorithm:
        Under Brownian motion the expected range grows with sqrt(N), so the
        threshold scales as ATR(14) * K * sqrt(N) where N = window size in days.
        This keeps the consolidation criterion statistically consistent across
        short (5-day) and long (60+ day) bases.

        K = 1.3:
          5 days:  threshold ≈ ATR × 2.91
          20 days: threshold ≈ ATR × 5.81
          60 days: threshold ≈ ATR × 10.07

        Range Contraction [RC] = avg_range_5d / avg_range_20d (unchanged).
        """
        SQRT_K = 1.3
        MAX_CONSOL_DAYS = 120
        ATR_PERIOD = 14

        try:
            df = self.conn.execute(f"""
                SELECT symbol, date, high, low, close
                FROM {source_table}
                WHERE close IS NOT NULL
                ORDER BY symbol, date
            """).fetchdf()
            if df.empty:
                return

            df['daily_range'] = df['high'] - df['low']
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    abs(df['high'] - df.groupby('symbol')['close'].shift(1)),
                    abs(df['low'] - df.groupby('symbol')['close'].shift(1))
                )
            )
            df['atr'] = df.groupby('symbol')['tr'].transform(
                lambda x: x.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
            )

            avg_range_20 = df.groupby('symbol')['daily_range'].transform(
                lambda x: x.rolling(20, min_periods=5).mean()
            )
            avg_range_5 = df.groupby('symbol')['daily_range'].transform(
                lambda x: x.rolling(5, min_periods=2).mean()
            )
            df['range_contraction'] = np.where(
                avg_range_20 > 0,
                (avg_range_5 / avg_range_20).round(4),
                np.nan
            )

            df_sorted = df.sort_values(['symbol', 'date'])
            results = []
            sqrt_table = [np.sqrt(n) for n in range(MAX_CONSOL_DAYS + 2)]

            for symbol, grp in df_sorted.groupby('symbol'):
                if len(grp) < ATR_PERIOD + 2:
                    results.append({
                        'symbol': symbol,
                        'consolidation_days': 0,
                        'consolidation_high': np.nan,
                        'consolidation_low': np.nan,
                        'range_contraction': grp['range_contraction'].iloc[-1] if len(grp) > 0 else np.nan,
                    })
                    continue

                highs = grp['high'].values
                lows = grp['low'].values
                atrs = grp['atr'].values
                rc = grp['range_contraction'].iloc[-1]

                last_idx = len(highs) - 1
                last_atr = atrs[last_idx]

                if np.isnan(last_atr) or last_atr <= 0:
                    results.append({
                        'symbol': symbol, 'consolidation_days': 0,
                        'consolidation_high': np.nan, 'consolidation_low': np.nan,
                        'range_contraction': rc,
                    })
                    continue

                con_days = 0
                rolling_high = highs[last_idx]
                rolling_low = lows[last_idx]

                for i in range(1, min(MAX_CONSOL_DAYS + 1, last_idx + 1)):
                    look_idx = last_idx - i
                    candidate_high = max(rolling_high, highs[look_idx])
                    candidate_low = min(rolling_low, lows[look_idx])
                    rng = candidate_high - candidate_low
                    threshold = last_atr * SQRT_K * sqrt_table[i + 1]

                    if rng < threshold:
                        rolling_high = candidate_high
                        rolling_low = candidate_low
                        con_days += 1
                    else:
                        break

                results.append({
                    'symbol': symbol,
                    'consolidation_days': con_days,
                    'consolidation_high': rolling_high if con_days > 0 else np.nan,
                    'consolidation_low': rolling_low if con_days > 0 else np.nan,
                    'range_contraction': rc,
                })

            latest = pd.DataFrame(results)
            if latest.empty:
                return

            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS consolidation_days INTEGER")
            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS range_contraction DOUBLE")
            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS consolidation_high DOUBLE")
            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS consolidation_low DOUBLE")
            self.conn.register('_consol_update', latest)
            self.conn.execute(f"""
                UPDATE {target_table} t
                SET consolidation_days = r.consolidation_days,
                    range_contraction = r.range_contraction,
                    consolidation_high = r.consolidation_high,
                    consolidation_low = r.consolidation_low
                FROM _consol_update r
                WHERE t.symbol = r.symbol
            """)
            self.conn.unregister('_consol_update')
            logger.info("consolidation_computed", symbols=len(latest),
                        avg_days=round(latest['consolidation_days'].mean(), 1),
                        with_consolidation=int((latest['consolidation_days'] > 0).sum()))
        except Exception as e:
            logger.error("consolidation_failed", error=str(e))

    def _compute_linear_regression(self, source_table: str, target_table: str):
        """Compute Linear Regression Divergence [LR130]."""
        try:
            import numpy as np
            df = self.conn.execute(f"""
                SELECT symbol, date, close FROM {source_table}
                WHERE close IS NOT NULL ORDER BY symbol, date
            """).fetchdf()
            if df.empty:
                return
            results = []
            for symbol, grp in df.groupby('symbol'):
                closes = grp['close'].values
                if len(closes) < 130:
                    results.append({'symbol': symbol, 'lr_divergence_130': None})
                    continue
                last_130 = closes[-130:]
                if np.any(np.isnan(last_130)) or np.any(np.isinf(last_130)):
                    results.append({'symbol': symbol, 'lr_divergence_130': None})
                    continue
                x = np.arange(130)
                coeffs = np.polyfit(x, last_130, 1)
                lr_value = coeffs[0] * 129 + coeffs[1]
                if np.isnan(lr_value) or np.isinf(lr_value) or lr_value == 0:
                    results.append({'symbol': symbol, 'lr_divergence_130': None})
                    continue
                current_price = closes[-1]
                div = round(((current_price - lr_value) / lr_value) * 100, 2)
                results.append({'symbol': symbol, 'lr_divergence_130': div})
            if not results:
                return
            import pandas as pd
            lr_df = pd.DataFrame(results)
            self.conn.execute(f"ALTER TABLE {target_table} ADD COLUMN IF NOT EXISTS lr_divergence_130 DOUBLE")
            self.conn.register('_lr_update', lr_df)
            self.conn.execute(f"""
                UPDATE {target_table} t SET lr_divergence_130 = r.lr_divergence_130
                FROM _lr_update r WHERE t.symbol = r.symbol
            """)
            self.conn.unregister('_lr_update')
            logger.info("linear_regression_computed", symbols=len(lr_df))
        except Exception as e:
            logger.error("linear_regression_failed", error=str(e))

    def _compute_rsi_wilder(self, source_table: str, target_table: str, period: int = 14):
        """Compute RSI using Wilder's smoothing (identical to TradingView ta.rma)."""
        df = self.conn.execute(f"""
            SELECT symbol, date, close
            FROM {source_table}
            WHERE close IS NOT NULL
            ORDER BY symbol, date
        """).fetchdf()

        if df.empty:
            return

        df['delta'] = df.groupby('symbol')['close'].diff()
        df['gain'] = df['delta'].clip(lower=0)
        df['loss'] = (-df['delta']).clip(lower=0)

        alpha = 1.0 / period
        df['avg_gain'] = df.groupby('symbol')['gain'].transform(
            lambda x: x.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        )
        df['avg_loss'] = df.groupby('symbol')['loss'].transform(
            lambda x: x.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
        )

        df['rsi_14'] = np.where(
            df['avg_loss'] == 0,
            100.0,
            100 - (100 / (1 + df['avg_gain'] / df['avg_loss']))
        )

        latest = df.sort_values('date').groupby('symbol').tail(1)[['symbol', 'rsi_14']].dropna()

        if latest.empty:
            return

        self.conn.register('_rsi_update', latest)
        self.conn.execute(f"""
            UPDATE {target_table} t
            SET rsi_14 = r.rsi_14
            FROM _rsi_update r
            WHERE t.symbol = r.symbol
        """)
        self.conn.unregister('_rsi_update')

        logger.info("rsi_wilder_computed", symbols=len(latest))

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
    
    def export_daily_indicators(self) -> List[Dict[str, Any]]:
        """
        Export daily indicator values for all tickers.
        
        Used by the alert_engine to detect SMA crosses, Bollinger breakouts, etc.
        Only exports the latest values (most recent trading day per symbol).
        
        Returns:
            List of dicts with symbol + indicator values
        """
        try:
            result = self.conn.execute("""
                SELECT
                    symbol,
                    price as last_close,
                    sma_5,
                    sma_8,
                    sma_10,
                    sma_20,
                    sma_50,
                    sma_200,
                    bb_upper,
                    bb_lower,
                    bb_position,
                    rsi_14 as rsi,
                    atr_14,
                    atr_percent,
                    adx_14,
                    high_5d,
                    low_5d,
                    range_5d,
                    high_10d,
                    low_10d,
                    range_10d,
                    high_20d,
                    low_20d,
                    range_20d,
                    high_52w,
                    low_52w,
                    from_52w_high,
                    from_52w_low,
                    market_cap,
                    free_float,
                    -- Multi-day changes (%)
                    change_1d,
                    change_3d,
                    change_5d,
                    change_10d,
                    change_20d,
                    -- Multi-day changes ($)
                    change_5d_dollars,
                    change_10d_dollars,
                    change_20d_dollars,
                    -- 1-year change
                    change_1y,
                    change_1y_dollars,
                    gap_percent,
                    -- Average volumes
                    avg_volume_5,
                    avg_volume_10,
                    avg_volume_20,
                    avg_volume_63,
                    -- Distance from SMA (%)
                    dist_sma_5,
                    dist_sma_8,
                    dist_sma_10,
                    dist_sma_20,
                    dist_sma_50,
                    dist_sma_200,
                    -- Yearly standard deviation
                    yearly_std_dev,
                    -- Directional indicators
                    plus_di_14,
                    minus_di_14,
                    -- Consecutive days up/down
                    consecutive_days_up,
                    -- YTD change
                    change_ytd,
                    change_ytd_dollars,
                    -- Position in range (high/low for 3M/6M/9M/2Y/lifetime)
                    high_3m,
                    low_3m,
                    high_6m,
                    low_6m,
                    high_9m,
                    low_9m,
                    high_2y,
                    low_2y,
                    high_all,
                    low_all,
                    -- Consolidation / Range Contraction / Linear Regression
                    consolidation_days,
                    consolidation_high,
                    consolidation_low,
                    range_contraction,
                    lr_divergence_130
                FROM screener_data
                WHERE sma_20 IS NOT NULL
            """).fetchdf()
            
            import math
            records = result.to_dict(orient="records")
            for rec in records:
                for k, v in rec.items():
                    try:
                        if v is not None and isinstance(v, (float, np.floating)) and (math.isnan(v) or math.isinf(v)):
                            rec[k] = None
                    except (TypeError, ValueError):
                        pass
            logger.info("daily_indicators_exported", count=len(records))
            return records
        except Exception as e:
            logger.error("export_daily_indicators_failed", error=str(e))
            return []
    
    def close(self):
        """Close database connection"""
        self.conn.close()
        logger.info("screener_engine_closed")

