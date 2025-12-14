"""
Database models and repository for XBRL → Canonical mappings.

Provides:
- PostgreSQL tables for persistent mapping cache
- Repository class for CRUD operations
- Connection management via asyncpg
"""

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import logging
import os

logger = logging.getLogger(__name__)


# =============================================================================
# DATACLASSES
# =============================================================================

@dataclass
class XBRLMapping:
    """Representa un mapeo XBRL → Canonical en la base de datos."""
    id: Optional[int]
    xbrl_concept: str           # ej: "CostOfGoodsAndServicesSold"
    canonical_key: str          # ej: "cost_of_revenue"
    confidence: float           # 0.0-1.0, 1.0 = mapeo manual verificado
    source: str                 # "manual", "regex", "llm", "sec_dataset"
    statement_type: str         # "income", "balance", "cashflow"
    example_company: Optional[str]  # CIK donde se vio este concepto
    created_at: Optional[datetime]
    verified: bool              # Si fue verificado manualmente
    usage_count: int            # Cuántas veces se ha usado


# =============================================================================
# SQL SCHEMAS
# =============================================================================

CREATE_TABLES_SQL = """
-- Tabla de campos canónicos (referencia)
CREATE TABLE IF NOT EXISTS canonical_fields (
    key VARCHAR(100) PRIMARY KEY,
    label VARCHAR(200) NOT NULL,
    section VARCHAR(100) NOT NULL,
    statement_type VARCHAR(20) NOT NULL,  -- 'income', 'balance', 'cashflow'
    data_type VARCHAR(20) DEFAULT 'monetary',
    "order" INTEGER NOT NULL,
    indent INTEGER DEFAULT 0,
    is_subtotal BOOLEAN DEFAULT FALSE,
    calculated BOOLEAN DEFAULT FALSE,
    importance INTEGER DEFAULT 100,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índice para búsqueda por statement
CREATE INDEX IF NOT EXISTS idx_canonical_statement ON canonical_fields(statement_type);

-- Tabla principal de mapeos XBRL → Canonical
CREATE TABLE IF NOT EXISTS xbrl_mappings (
    id SERIAL PRIMARY KEY,
    xbrl_concept VARCHAR(300) NOT NULL,  -- Concepto XBRL (ej: CostOfGoodsAndServicesSold)
    canonical_key VARCHAR(100) NOT NULL REFERENCES canonical_fields(key),
    confidence FLOAT DEFAULT 1.0,        -- 1.0 = manual, 0.8+ = regex/fasb, <0.8 = LLM
    source VARCHAR(50) NOT NULL,         -- 'manual', 'regex', 'llm', 'sec_dataset'
    statement_type VARCHAR(20) NOT NULL,
    example_company VARCHAR(20),         -- CIK donde se vio
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    verified BOOLEAN DEFAULT FALSE,      -- Si fue verificado manualmente
    usage_count INTEGER DEFAULT 1,
    UNIQUE(xbrl_concept, canonical_key)
);

-- Índices para búsqueda eficiente
CREATE INDEX IF NOT EXISTS idx_xbrl_concept ON xbrl_mappings(xbrl_concept);
CREATE INDEX IF NOT EXISTS idx_canonical_key ON xbrl_mappings(canonical_key);
CREATE INDEX IF NOT EXISTS idx_xbrl_statement ON xbrl_mappings(statement_type);
CREATE INDEX IF NOT EXISTS idx_xbrl_confidence ON xbrl_mappings(confidence DESC);

-- Tabla de conceptos desconocidos (para review/training)
CREATE TABLE IF NOT EXISTS unknown_concepts (
    id SERIAL PRIMARY KEY,
    xbrl_concept VARCHAR(300) NOT NULL UNIQUE,
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    occurrence_count INTEGER DEFAULT 1,
    example_companies TEXT[],  -- Array de CIKs
    llm_suggestion VARCHAR(100),  -- Sugerencia del LLM
    llm_confidence FLOAT,
    reviewed BOOLEAN DEFAULT FALSE,
    ignored BOOLEAN DEFAULT FALSE  -- Si marcamos como "no mapear"
);

CREATE INDEX IF NOT EXISTS idx_unknown_reviewed ON unknown_concepts(reviewed);
CREATE INDEX IF NOT EXISTS idx_unknown_occurrences ON unknown_concepts(occurrence_count DESC);
"""


# =============================================================================
# REPOSITORY CLASS
# =============================================================================

class MappingRepository:
    """
    Repository for XBRL → Canonical mappings.
    
    Uses asyncpg for async PostgreSQL operations.
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize repository.
        
        Args:
            database_url: PostgreSQL connection URL (optional, reads from env)
        """
        self.database_url = database_url or self._get_database_url()
        self._pool = None
        self._available = ASYNCPG_AVAILABLE
        
        if not ASYNCPG_AVAILABLE:
            logger.warning("MappingRepository: asyncpg not installed, DB operations disabled")
        
    def _get_database_url(self) -> str:
        """Get database URL from environment or settings."""
        # Try environment variable first
        url = os.getenv("DATABASE_URL")
        if url:
            return url
            
        # Build from individual env vars
        host = os.getenv("DB_HOST", "timescaledb")
        port = os.getenv("DB_PORT", "5432")
        db = os.getenv("DB_NAME", "tradeul")
        user = os.getenv("DB_USER", "tradeul_user")
        password = os.getenv("DB_PASSWORD", "changeme123")
        
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    async def connect(self) -> None:
        """Create connection pool."""
        if not self._available:
            return
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10
            )
            logger.info("MappingRepository: Connected to database")
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("MappingRepository: Disconnected from database")
    
    async def initialize_tables(self) -> None:
        """Create tables if they don't exist."""
        if not self._available:
            logger.warning("Cannot initialize tables: asyncpg not available")
            return
        await self.connect()
        if self._pool is None:
            logger.warning("Cannot initialize tables: pool not connected")
            return
        async with self._pool.acquire() as conn:
            await conn.execute(CREATE_TABLES_SQL)
            logger.info("MappingRepository: Tables initialized")
    
    # =========================================================================
    # CANONICAL FIELDS
    # =========================================================================
    
    async def upsert_canonical_field(
        self,
        key: str,
        label: str,
        section: str,
        statement_type: str,
        order: int,
        data_type: str = "monetary",
        indent: int = 0,
        is_subtotal: bool = False,
        calculated: bool = False,
        importance: int = 100
    ) -> None:
        """Insert or update a canonical field."""
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO canonical_fields 
                (key, label, section, statement_type, data_type, "order", indent, is_subtotal, calculated, importance)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (key) DO UPDATE SET
                    label = $2, section = $3, statement_type = $4, data_type = $5,
                    "order" = $6, indent = $7, is_subtotal = $8, calculated = $9, importance = $10
            """, key, label, section, statement_type, data_type, order, indent, is_subtotal, calculated, importance)
    
    async def get_all_canonical_keys(self) -> List[str]:
        """Get all canonical field keys."""
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT key FROM canonical_fields")
            return [row["key"] for row in rows]
    
    # =========================================================================
    # XBRL MAPPINGS
    # =========================================================================
    
    async def get_mapping(self, xbrl_concept: str) -> Optional[XBRLMapping]:
        """
        Get mapping for an XBRL concept.
        
        Args:
            xbrl_concept: XBRL concept name (e.g., "CostOfGoodsAndServicesSold")
            
        Returns:
            XBRLMapping or None if not found
        """
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, xbrl_concept, canonical_key, confidence, source,
                       statement_type, example_company, created_at, verified, usage_count
                FROM xbrl_mappings
                WHERE xbrl_concept = $1
                ORDER BY confidence DESC, usage_count DESC
                LIMIT 1
            """, xbrl_concept)
            
            if row:
                return XBRLMapping(
                    id=row["id"],
                    xbrl_concept=row["xbrl_concept"],
                    canonical_key=row["canonical_key"],
                    confidence=row["confidence"],
                    source=row["source"],
                    statement_type=row["statement_type"],
                    example_company=row["example_company"],
                    created_at=row["created_at"],
                    verified=row["verified"],
                    usage_count=row["usage_count"]
                )
            return None
    
    async def get_mappings_batch(self, xbrl_concepts: List[str]) -> Dict[str, XBRLMapping]:
        """
        Get mappings for multiple XBRL concepts at once.
        
        Args:
            xbrl_concepts: List of XBRL concept names
            
        Returns:
            Dict mapping xbrl_concept → XBRLMapping
        """
        if not xbrl_concepts:
            return {}
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return {}
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (xbrl_concept)
                    id, xbrl_concept, canonical_key, confidence, source,
                    statement_type, example_company, created_at, verified, usage_count
                FROM xbrl_mappings
                WHERE xbrl_concept = ANY($1)
                ORDER BY xbrl_concept, confidence DESC, usage_count DESC
            """, xbrl_concepts)
            
            result = {}
            for row in rows:
                result[row["xbrl_concept"]] = XBRLMapping(
                    id=row["id"],
                    xbrl_concept=row["xbrl_concept"],
                    canonical_key=row["canonical_key"],
                    confidence=row["confidence"],
                    source=row["source"],
                    statement_type=row["statement_type"],
                    example_company=row["example_company"],
                    created_at=row["created_at"],
                    verified=row["verified"],
                    usage_count=row["usage_count"]
                )
            return result
    
    async def add_mapping(
        self,
        xbrl_concept: str,
        canonical_key: str,
        confidence: float,
        source: str,
        statement_type: str,
        example_company: Optional[str] = None
    ) -> None:
        """
        Add or update an XBRL → Canonical mapping.
        
        Args:
            xbrl_concept: XBRL concept name
            canonical_key: Canonical field key
            confidence: Confidence score (0.0-1.0)
            source: Source of mapping ("manual", "regex", "llm", "sec_dataset")
            statement_type: Statement type ("income", "balance", "cashflow")
            example_company: CIK where this was seen (optional)
        """
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO xbrl_mappings 
                (xbrl_concept, canonical_key, confidence, source, statement_type, example_company)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (xbrl_concept, canonical_key) DO UPDATE SET
                    confidence = GREATEST(xbrl_mappings.confidence, $3),
                    usage_count = xbrl_mappings.usage_count + 1,
                    updated_at = NOW()
            """, xbrl_concept, canonical_key, confidence, source, statement_type, example_company)
    
    async def add_mappings_batch(self, mappings: List[Tuple[str, str, float, str, str, Optional[str]]]) -> None:
        """
        Add multiple mappings in a single transaction.
        
        Args:
            mappings: List of tuples (xbrl_concept, canonical_key, confidence, source, statement_type, example_company)
        """
        if not mappings:
            return
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return
        async with self._pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO xbrl_mappings 
                (xbrl_concept, canonical_key, confidence, source, statement_type, example_company)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (xbrl_concept, canonical_key) DO UPDATE SET
                    confidence = GREATEST(xbrl_mappings.confidence, $3),
                    usage_count = xbrl_mappings.usage_count + 1,
                    updated_at = NOW()
            """, mappings)
            logger.info(f"MappingRepository: Added {len(mappings)} mappings")
    
    async def increment_usage(self, xbrl_concept: str) -> None:
        """Increment usage count for a mapping."""
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE xbrl_mappings 
                SET usage_count = usage_count + 1, updated_at = NOW()
                WHERE xbrl_concept = $1
            """, xbrl_concept)
    
    async def verify_mapping(self, xbrl_concept: str, canonical_key: str) -> None:
        """Mark a mapping as manually verified."""
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE xbrl_mappings 
                SET verified = TRUE, confidence = 1.0, updated_at = NOW()
                WHERE xbrl_concept = $1 AND canonical_key = $2
            """, xbrl_concept, canonical_key)
    
    # =========================================================================
    # UNKNOWN CONCEPTS
    # =========================================================================
    
    async def add_unknown_concept(
        self,
        xbrl_concept: str,
        example_company: Optional[str] = None,
        llm_suggestion: Optional[str] = None,
        llm_confidence: Optional[float] = None
    ) -> None:
        """
        Track an unknown XBRL concept for later review.
        
        Args:
            xbrl_concept: XBRL concept that couldn't be mapped
            example_company: CIK where this was seen
            llm_suggestion: Suggested canonical key from LLM
            llm_confidence: LLM confidence score
        """
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO unknown_concepts (xbrl_concept, example_companies, llm_suggestion, llm_confidence)
                VALUES ($1, ARRAY[$2]::TEXT[], $3, $4)
                ON CONFLICT (xbrl_concept) DO UPDATE SET
                    occurrence_count = unknown_concepts.occurrence_count + 1,
                    last_seen = NOW(),
                    example_companies = CASE 
                        WHEN $2 IS NOT NULL AND NOT ($2 = ANY(unknown_concepts.example_companies))
                        THEN array_append(unknown_concepts.example_companies, $2)
                        ELSE unknown_concepts.example_companies
                    END
            """, xbrl_concept, example_company, llm_suggestion, llm_confidence)
    
    async def get_unknown_concepts(
        self,
        limit: int = 100,
        only_unreviewed: bool = True
    ) -> List[Dict]:
        """Get unknown concepts for review."""
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return []
        async with self._pool.acquire() as conn:
            query = """
                SELECT xbrl_concept, occurrence_count, example_companies, 
                       llm_suggestion, llm_confidence, first_seen, last_seen
                FROM unknown_concepts
                WHERE ignored = FALSE
            """
            if only_unreviewed:
                query += " AND reviewed = FALSE"
            query += " ORDER BY occurrence_count DESC LIMIT $1"
            
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
    
    # =========================================================================
    # STATS
    # =========================================================================
    
    async def get_stats(self) -> Dict:
        """Get mapping statistics."""
        if not self._available or self._pool is None:
            await self.connect()
            if self._pool is None:
                return {"error": "Database not available"}
        async with self._pool.acquire() as conn:
            stats = {}
            
            # Total mappings
            stats["total_mappings"] = await conn.fetchval(
                "SELECT COUNT(*) FROM xbrl_mappings"
            )
            
            # By source
            rows = await conn.fetch(
                "SELECT source, COUNT(*) as count FROM xbrl_mappings GROUP BY source"
            )
            stats["by_source"] = {row["source"]: row["count"] for row in rows}
            
            # By statement type
            rows = await conn.fetch(
                "SELECT statement_type, COUNT(*) as count FROM xbrl_mappings GROUP BY statement_type"
            )
            stats["by_statement"] = {row["statement_type"]: row["count"] for row in rows}
            
            # Verified vs unverified
            stats["verified_count"] = await conn.fetchval(
                "SELECT COUNT(*) FROM xbrl_mappings WHERE verified = TRUE"
            )
            
            # Unknown concepts pending
            stats["unknown_pending"] = await conn.fetchval(
                "SELECT COUNT(*) FROM unknown_concepts WHERE reviewed = FALSE AND ignored = FALSE"
            )
            
            # Canonical fields
            stats["canonical_fields"] = await conn.fetchval(
                "SELECT COUNT(*) FROM canonical_fields"
            )
            
            return stats


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_repository: Optional[MappingRepository] = None


def get_repository() -> MappingRepository:
    """Get singleton repository instance."""
    global _repository
    if _repository is None:
        _repository = MappingRepository()
    return _repository

