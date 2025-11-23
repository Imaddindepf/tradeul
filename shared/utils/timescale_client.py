"""
TimescaleDB client wrapper with async support
"""

from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager
import asyncpg
from asyncpg import Pool, Connection

from ..config.settings import settings
from .logger import get_logger

logger = get_logger(__name__)


class TimescaleClient:
    """
    Async TimescaleDB (PostgreSQL) client
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize TimescaleDB client
        
        Args:
            database_url: PostgreSQL connection URL (uses settings if not provided)
        """
        self.database_url = database_url or settings.async_database_url
        self._pool: Optional[Pool] = None
    
    async def connect(
        self,
        min_size: int = 10,
        max_size: int = 20
    ) -> None:
        """
        Establish database connection pool
        
        Args:
            min_size: Minimum pool size
            max_size: Maximum pool size
        """
        try:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60
            )
            logger.info("Connected to TimescaleDB", min_size=min_size, max_size=max_size)
        except Exception as e:
            logger.error("Failed to connect to TimescaleDB", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Close database connection pool"""
        if self._pool:
            await self._pool.close()
            logger.info("Disconnected from TimescaleDB")
    
    @property
    def pool(self) -> Pool:
        """Get connection pool"""
        if not self._pool:
            raise RuntimeError("TimescaleDB client not connected. Call connect() first.")
        return self._pool
    
    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Connection]:
        """
        Acquire a connection from the pool
        
        Usage:
            async with client.acquire() as conn:
                result = await conn.fetch("SELECT * FROM tickers")
        """
        async with self.pool.acquire() as connection:
            yield connection
    
    # =============================================
    # QUERY OPERATIONS
    # =============================================
    
    async def execute(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> str:
        """
        Execute a query without returning results
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
        
        Returns:
            Status message
        """
        try:
            async with self.acquire() as conn:
                result = await conn.execute(query, *args, timeout=timeout)
                logger.debug("Query executed", query=query[:100], result=result)
                return result
        except Exception as e:
            logger.error("Query execution error", query=query[:100], error=str(e))
            raise
    
    async def fetch(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch multiple rows
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
        
        Returns:
            List of rows as dictionaries
        """
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(query, *args, timeout=timeout)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Query fetch error", query=query[:100], error=str(e))
            raise
    
    async def fetchrow(
        self,
        query: str,
        *args,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row
        
        Args:
            query: SQL query
            *args: Query parameters
            timeout: Query timeout in seconds
        
        Returns:
            Row as dictionary or None
        """
        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(query, *args, timeout=timeout)
                return dict(row) if row else None
        except Exception as e:
            logger.error("Query fetchrow error", query=query[:100], error=str(e))
            raise
    
    async def fetchval(
        self,
        query: str,
        *args,
        column: int = 0,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Fetch a single value
        
        Args:
            query: SQL query
            *args: Query parameters
            column: Column index
            timeout: Query timeout in seconds
        
        Returns:
            Single value
        """
        try:
            async with self.acquire() as conn:
                return await conn.fetchval(query, *args, column=column, timeout=timeout)
        except Exception as e:
            logger.error("Query fetchval error", query=query[:100], error=str(e))
            raise
    
    # =============================================
    # BULK OPERATIONS
    # =============================================
    
    async def executemany(
        self,
        query: str,
        args: List[tuple],
        timeout: Optional[float] = None
    ) -> None:
        """
        Execute query with many parameter sets
        
        Args:
            query: SQL query
            args: List of parameter tuples
            timeout: Query timeout in seconds
        """
        try:
            async with self.acquire() as conn:
                await conn.executemany(query, args, timeout=timeout)
                logger.debug("Bulk query executed", query=query[:100], rows=len(args))
        except Exception as e:
            logger.error("Bulk query error", query=query[:100], error=str(e))
            raise
    
    async def copy_records_to_table(
        self,
        table_name: str,
        records: List[tuple],
        columns: List[str],
        schema: str = "public"
    ) -> int:
        """
        Efficiently copy records to a table using COPY
        
        Args:
            table_name: Target table name
            records: List of record tuples
            columns: Column names
            schema: Schema name
        
        Returns:
            Number of records copied
        """
        try:
            async with self.acquire() as conn:
                result = await conn.copy_records_to_table(
                    table_name,
                    records=records,
                    columns=columns,
                    schema_name=schema
                )
                logger.info(
                    "Records copied to table",
                    table=f"{schema}.{table_name}",
                    count=len(records)
                )
                return len(records)
        except Exception as e:
            logger.error(
                "Copy records error",
                table=f"{schema}.{table_name}",
                error=str(e)
            )
            raise
    
    # =============================================
    # TRANSACTION OPERATIONS
    # =============================================
    
    @asynccontextmanager
    async def transaction(self):
        """
        Execute queries in a transaction
        
        Usage:
            async with client.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    # =============================================
    # TICKER METADATA OPERATIONS
    # =============================================
    
    async def get_ticker_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a ticker from tickers_unified
        
        Returns all 35 fields including expanded metadata (description, homepage_url, etc.)
        """
        query = """
            SELECT * FROM tickers_unified
            WHERE symbol = $1
        """
        return await self.fetchrow(query, symbol)
    
    async def upsert_ticker_metadata(
        self,
        symbol: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Insert or update ticker metadata in tickers_unified
        
        Supports both basic fields (14) and expanded fields (35 total).
        Expanded fields are optional and will be NULL if not provided.
        """
        query = """
            INSERT INTO tickers_unified (
                symbol, company_name, exchange, sector, industry,
                market_cap, float_shares, shares_outstanding,
                avg_volume_30d, avg_volume_10d, avg_price_30d,
                beta, is_etf, is_actively_trading, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW()
            )
            ON CONFLICT (symbol) DO UPDATE SET
                company_name = EXCLUDED.company_name,
                exchange = EXCLUDED.exchange,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                market_cap = EXCLUDED.market_cap,
                float_shares = EXCLUDED.float_shares,
                shares_outstanding = EXCLUDED.shares_outstanding,
                avg_volume_30d = EXCLUDED.avg_volume_30d,
                avg_volume_10d = EXCLUDED.avg_volume_10d,
                avg_price_30d = EXCLUDED.avg_price_30d,
                beta = EXCLUDED.beta,
                is_etf = EXCLUDED.is_etf,
                is_actively_trading = EXCLUDED.is_actively_trading,
                updated_at = NOW()
        """
        await self.execute(
            query,
            symbol,
            metadata.get("company_name"),
            metadata.get("exchange"),
            metadata.get("sector"),
            metadata.get("industry"),
            metadata.get("market_cap"),
            metadata.get("float_shares"),
            metadata.get("shares_outstanding"),
            metadata.get("avg_volume_30d"),
            metadata.get("avg_volume_10d"),
            metadata.get("avg_price_30d"),
            metadata.get("beta"),
            metadata.get("is_etf", False),
            metadata.get("is_actively_trading", True)
        )
    
    # =============================================
    # SCAN RESULTS OPERATIONS
    # =============================================
    
    async def insert_scan_result(self, scan_data: Dict[str, Any]) -> None:
        """Insert a scan result"""
        query = """
            INSERT INTO scan_results (
                time, symbol, session, price, volume, volume_today,
                change_percent, rvol, rvol_slot, price_from_high,
                price_from_low, market_cap, float_shares, score,
                filters_matched, metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
            )
        """
        await self.execute(
            query,
            scan_data.get("time"),
            scan_data.get("symbol"),
            scan_data.get("session"),
            scan_data.get("price"),
            scan_data.get("volume"),
            scan_data.get("volume_today"),
            scan_data.get("change_percent"),
            scan_data.get("rvol"),
            scan_data.get("rvol_slot"),
            scan_data.get("price_from_high"),
            scan_data.get("price_from_low"),
            scan_data.get("market_cap"),
            scan_data.get("float_shares"),
            scan_data.get("score"),
            scan_data.get("filters_matched", []),
            scan_data.get("metadata")
        )
    
    async def get_recent_scan_results(
        self,
        limit: int = 100,  # Mantener 100 como default razonable para esta función interna
        session: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent scan results (función interna, usa límite razonable)"""
        if session:
            query = """
                SELECT * FROM scan_results
                WHERE session = $1
                ORDER BY time DESC, score DESC
                LIMIT $2
            """
            return await self.fetch(query, session, limit)
        else:
            query = """
                SELECT * FROM scan_results
                ORDER BY time DESC, score DESC
                LIMIT $1
            """
            return await self.fetch(query, limit)
    
    # =============================================
    # HEALTH CHECK
    # =============================================
    
    async def health_check(self) -> bool:
        """Check if database is healthy"""
        try:
            result = await self.fetchval("SELECT 1")
            return result == 1
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False


# Global TimescaleDB client instance
_timescale_client: Optional[TimescaleClient] = None


async def get_timescale_client() -> TimescaleClient:
    """Get or create global TimescaleDB client"""
    global _timescale_client
    
    if _timescale_client is None:
        _timescale_client = TimescaleClient()
        await _timescale_client.connect()
    
    return _timescale_client


async def close_timescale_client() -> None:
    """Close global TimescaleDB client"""
    global _timescale_client
    
    if _timescale_client:
        await _timescale_client.disconnect()
        _timescale_client = None

