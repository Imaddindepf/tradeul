"""
Pattern Real-Time - SQLite Database Client
==========================================

Async-compatible SQLite database for storing predictions and verification results.
Uses aiosqlite for async operations.

Database: data/predictions.db (separate from patterns_metadata.db)
"""

import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from contextlib import asynccontextmanager
import uuid
import json

import aiosqlite
import structlog

from config import settings
from .models import (
    JobStatus,
    Direction,
    PredictionResult,
    FailureResult,
    RealtimeJobStatus,
    PerformanceStats,
    BucketStats,
    SortBy,
)

logger = structlog.get_logger(__name__)


class PredictionsDB:
    """
    SQLite database for Pattern Real-Time predictions
    
    Stores:
    - Jobs: Batch scan jobs with parameters and status
    - Predictions: Individual predictions with verification results
    - Failures: Failed scans with error details
    """
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(settings.data_dir, "predictions.db")
        self._connection: Optional[aiosqlite.Connection] = None
        self._initialized = False
        
        logger.info("PredictionsDB initialized", path=self.db_path)
    
    async def connect(self) -> None:
        """Initialize database connection and create tables"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self._connection = await aiosqlite.connect(
            self.db_path,
            check_same_thread=False
        )
        
        # Enable foreign keys and WAL mode for better concurrency
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._connection.execute("PRAGMA synchronous = NORMAL")
        
        await self._create_tables()
        self._initialized = True
        
        logger.info("PredictionsDB connected", path=self.db_path)
    
    async def disconnect(self) -> None:
        """Close database connection"""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._initialized = False
            logger.info("PredictionsDB disconnected")
    
    @property
    def conn(self) -> aiosqlite.Connection:
        """Get connection (raises if not connected)"""
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection
    
    async def _create_tables(self) -> None:
        """Create database tables if they don't exist"""
        
        # Jobs table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                started_at TEXT NOT NULL,
                completed_at TEXT,
                params TEXT NOT NULL,  -- JSON
                total_symbols INTEGER NOT NULL,
                completed_symbols INTEGER DEFAULT 0,
                failed_symbols INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        # Predictions table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                scan_time TEXT NOT NULL,
                horizon INTEGER NOT NULL,
                
                -- Prediction
                prob_up REAL NOT NULL,
                prob_down REAL NOT NULL,
                mean_return REAL NOT NULL,
                edge REAL NOT NULL,
                direction TEXT NOT NULL,
                n_neighbors INTEGER NOT NULL,
                dist1 REAL,
                p10 REAL,
                p90 REAL,
                
                -- Price at scan
                price_at_scan REAL NOT NULL,
                
                -- Verification (null until verified)
                price_at_horizon REAL,
                actual_return REAL,
                was_correct INTEGER,  -- SQLite doesn't have BOOLEAN
                pnl REAL,
                verified_at TEXT,
                
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
        
        # Failures table
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS failures (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                scan_time TEXT NOT NULL,
                error_code TEXT NOT NULL,
                reason TEXT NOT NULL,
                bars_since_open INTEGER,
                bars_until_close INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
        
        # Indexes for common queries
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_job 
            ON predictions(job_id)
        """)
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_symbol 
            ON predictions(symbol)
        """)
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_pending 
            ON predictions(scan_time) 
            WHERE verified_at IS NULL
        """)
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_predictions_scan_time 
            ON predictions(scan_time)
        """)
        await self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_failures_job 
            ON failures(job_id)
        """)
        
        await self.conn.commit()
        logger.info("Database tables created/verified")
    
    # ========================================================================
    # Job Operations
    # ========================================================================
    
    async def create_job(
        self,
        job_id: str,
        params: Dict[str, Any],
        total_symbols: int
    ) -> str:
        """Create a new job"""
        await self.conn.execute(
            """
            INSERT INTO jobs (id, status, started_at, params, total_symbols)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                job_id,
                JobStatus.RUNNING.value,
                datetime.utcnow().isoformat(),
                json.dumps(params),
                total_symbols
            )
        )
        await self.conn.commit()
        logger.info("Job created", job_id=job_id, total_symbols=total_symbols)
        return job_id
    
    async def update_job_progress(
        self,
        job_id: str,
        completed: int,
        failed: int
    ) -> None:
        """Update job progress"""
        await self.conn.execute(
            """
            UPDATE jobs 
            SET completed_symbols = ?, failed_symbols = ?
            WHERE id = ?
            """,
            (completed, failed, job_id)
        )
        await self.conn.commit()
    
    async def complete_job(
        self,
        job_id: str,
        status: JobStatus = JobStatus.COMPLETED
    ) -> None:
        """Mark job as completed"""
        await self.conn.execute(
            """
            UPDATE jobs 
            SET status = ?, completed_at = ?
            WHERE id = ?
            """,
            (status.value, datetime.utcnow().isoformat(), job_id)
        )
        await self.conn.commit()
        logger.info("Job completed", job_id=job_id, status=status.value)
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        async with self.conn.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None
    
    async def get_job_status(self, job_id: str) -> Optional[RealtimeJobStatus]:
        """Get full job status with results"""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        # Get predictions
        predictions = await self.get_predictions_for_job(job_id)
        
        # Get failures
        failures = await self.get_failures_for_job(job_id)
        
        # Calculate duration
        started_at = datetime.fromisoformat(job["started_at"])
        completed_at = (
            datetime.fromisoformat(job["completed_at"]) 
            if job["completed_at"] else None
        )
        duration = (
            (completed_at - started_at).total_seconds() 
            if completed_at else None
        )
        
        return RealtimeJobStatus(
            job_id=job["id"],
            status=JobStatus(job["status"]),
            progress={
                "completed": job["completed_symbols"],
                "total": job["total_symbols"],
                "failed": job["failed_symbols"]
            },
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            results=predictions,
            failures=failures,
            params=json.loads(job["params"])
        )
    
    # ========================================================================
    # Prediction Operations
    # ========================================================================
    
    async def insert_prediction(self, prediction: PredictionResult) -> str:
        """Insert a new prediction"""
        await self.conn.execute(
            """
            INSERT INTO predictions (
                id, job_id, symbol, scan_time, horizon,
                prob_up, prob_down, mean_return, edge, direction,
                n_neighbors, dist1, p10, p90, price_at_scan
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction.id,
                prediction.job_id,
                prediction.symbol,
                prediction.scan_time.isoformat(),
                prediction.horizon,
                prediction.prob_up,
                prediction.prob_down,
                prediction.mean_return,
                prediction.edge,
                prediction.direction.value,
                prediction.n_neighbors,
                prediction.dist1,
                prediction.p10,
                prediction.p90,
                prediction.price_at_scan
            )
        )
        await self.conn.commit()
        return prediction.id
    
    async def get_predictions_for_job(
        self,
        job_id: str,
        sort_by: SortBy = SortBy.EDGE,
        direction: Optional[Direction] = None,
        limit: int = 500
    ) -> List[PredictionResult]:
        """Get predictions for a job"""
        
        # Build query
        query = "SELECT * FROM predictions WHERE job_id = ?"
        params = [job_id]
        
        if direction:
            query += " AND direction = ?"
            params.append(direction.value)
        
        # Sort
        sort_column = {
            SortBy.EDGE: "edge DESC",
            SortBy.PROB_UP: "prob_up DESC",
            SortBy.MEAN_RETURN: "mean_return DESC",
            SortBy.SYMBOL: "symbol ASC"
        }.get(sort_by, "edge DESC")
        
        query += f" ORDER BY {sort_column} LIMIT ?"
        params.append(limit)
        
        async with self.conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            results = []
            for row in rows:
                data = dict(zip(columns, row))
                results.append(self._row_to_prediction(data))
            
            return results
    
    async def get_pending_predictions(
        self,
        limit: int = 100
    ) -> List[PredictionResult]:
        """Get predictions that need verification"""
        query = """
            SELECT * FROM predictions 
            WHERE verified_at IS NULL 
            AND datetime(scan_time, '+' || horizon || ' minutes') < datetime('now')
            ORDER BY scan_time ASC
            LIMIT ?
        """
        
        async with self.conn.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            results = []
            for row in rows:
                data = dict(zip(columns, row))
                results.append(self._row_to_prediction(data))
            
            return results
    
    async def verify_prediction(
        self,
        prediction_id: str,
        price_at_horizon: float,
        actual_return: float,
        was_correct: bool,
        pnl: float
    ) -> None:
        """Update prediction with verification results"""
        await self.conn.execute(
            """
            UPDATE predictions 
            SET price_at_horizon = ?,
                actual_return = ?,
                was_correct = ?,
                pnl = ?,
                verified_at = ?
            WHERE id = ?
            """,
            (
                price_at_horizon,
                actual_return,
                1 if was_correct else 0,
                pnl,
                datetime.utcnow().isoformat(),
                prediction_id
            )
        )
        await self.conn.commit()
    
    def _row_to_prediction(self, data: Dict[str, Any]) -> PredictionResult:
        """Convert database row to PredictionResult"""
        return PredictionResult(
            id=data["id"],
            job_id=data["job_id"],
            symbol=data["symbol"],
            scan_time=datetime.fromisoformat(data["scan_time"]),
            horizon=data["horizon"],
            prob_up=data["prob_up"],
            prob_down=data["prob_down"],
            mean_return=data["mean_return"],
            edge=data["edge"],
            direction=Direction(data["direction"]),
            n_neighbors=data["n_neighbors"],
            dist1=data["dist1"],
            p10=data["p10"],
            p90=data["p90"],
            price_at_scan=data["price_at_scan"],
            price_at_horizon=data["price_at_horizon"],
            actual_return=data["actual_return"],
            was_correct=bool(data["was_correct"]) if data["was_correct"] is not None else None,
            pnl=data["pnl"],
            verified_at=(
                datetime.fromisoformat(data["verified_at"]) 
                if data["verified_at"] else None
            )
        )
    
    # ========================================================================
    # Failure Operations
    # ========================================================================
    
    async def insert_failure(
        self,
        job_id: str,
        failure: FailureResult
    ) -> str:
        """Insert a failure record"""
        failure_id = str(uuid.uuid4())
        
        await self.conn.execute(
            """
            INSERT INTO failures (
                id, job_id, symbol, scan_time, error_code, reason,
                bars_since_open, bars_until_close
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                failure_id,
                job_id,
                failure.symbol,
                failure.scan_time.isoformat(),
                failure.error_code,
                failure.reason,
                failure.bars_since_open,
                failure.bars_until_close
            )
        )
        await self.conn.commit()
        return failure_id
    
    async def get_failures_for_job(self, job_id: str) -> List[FailureResult]:
        """Get failures for a job"""
        async with self.conn.execute(
            "SELECT * FROM failures WHERE job_id = ?",
            (job_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            return [
                FailureResult(
                    symbol=row[columns.index("symbol")],
                    scan_time=datetime.fromisoformat(row[columns.index("scan_time")]),
                    error_code=row[columns.index("error_code")],
                    reason=row[columns.index("reason")],
                    bars_since_open=row[columns.index("bars_since_open")],
                    bars_until_close=row[columns.index("bars_until_close")]
                )
                for row in rows
            ]
    
    # ========================================================================
    # Performance Statistics
    # ========================================================================
    
    async def get_performance_stats(
        self,
        period: str = "today"
    ) -> PerformanceStats:
        """Calculate performance statistics"""
        
        # Determine time filter
        now = datetime.utcnow()
        if period == "1h":
            since = now - timedelta(hours=1)
        elif period == "today":
            since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            since = now - timedelta(days=7)
        else:  # "all"
            since = datetime(2000, 1, 1)
        
        since_str = since.isoformat()
        
        # Get total counts
        async with self.conn.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) as verified,
                SUM(CASE WHEN verified_at IS NULL THEN 1 ELSE 0 END) as pending
            FROM predictions
            WHERE scan_time >= ?
            """,
            (since_str,)
        ) as cursor:
            row = await cursor.fetchone()
            total, verified, pending = row
        
        # Get verified predictions for stats calculation
        async with self.conn.execute(
            """
            SELECT direction, was_correct, pnl, edge
            FROM predictions
            WHERE scan_time >= ? AND verified_at IS NOT NULL
            ORDER BY edge DESC
            """,
            (since_str,)
        ) as cursor:
            rows = await cursor.fetchall()
        
        # Calculate stats
        all_stats = self._calculate_bucket_stats(rows)
        
        # Top percentile stats
        n = len(rows)
        top_1pct = self._calculate_bucket_stats(rows[:max(1, n // 100)]) if n > 0 else None
        top_5pct = self._calculate_bucket_stats(rows[:max(1, n // 20)]) if n > 0 else None
        top_10pct = self._calculate_bucket_stats(rows[:max(1, n // 10)]) if n > 0 else None
        
        # By direction
        long_rows = [r for r in rows if r[0] == "UP"]
        short_rows = [r for r in rows if r[0] == "DOWN"]
        long_stats = self._calculate_bucket_stats(long_rows) if long_rows else None
        short_stats = self._calculate_bucket_stats(short_rows) if short_rows else None
        
        return PerformanceStats(
            period=period,
            total_predictions=total or 0,
            verified=verified or 0,
            pending=pending or 0,
            all_stats=all_stats,
            top_1pct=top_1pct,
            top_5pct=top_5pct,
            top_10pct=top_10pct,
            long_stats=long_stats,
            short_stats=short_stats
        )
    
    def _calculate_bucket_stats(
        self,
        rows: List[Tuple]
    ) -> Optional[BucketStats]:
        """Calculate stats for a subset of predictions"""
        if not rows:
            return None
        
        # rows format: (direction, was_correct, pnl, edge)
        n = len(rows)
        long_count = sum(1 for r in rows if r[0] == "UP")
        short_count = n - long_count
        wins = sum(1 for r in rows if r[1])  # was_correct
        pnls = [r[2] for r in rows if r[2] is not None]
        
        win_rate = wins / n if n > 0 else None
        mean_pnl = sum(pnls) / len(pnls) if pnls else None
        
        # Median PnL
        median_pnl = None
        if pnls:
            sorted_pnls = sorted(pnls)
            mid = len(sorted_pnls) // 2
            median_pnl = (
                sorted_pnls[mid] if len(sorted_pnls) % 2 
                else (sorted_pnls[mid - 1] + sorted_pnls[mid]) / 2
            )
        
        return BucketStats(
            n=n,
            long_count=long_count,
            short_count=short_count,
            win_rate=round(win_rate, 4) if win_rate else None,
            mean_pnl=round(mean_pnl, 4) if mean_pnl else None,
            median_pnl=round(median_pnl, 4) if median_pnl else None
        )
    
    # ========================================================================
    # History/Cleanup
    # ========================================================================
    
    async def get_recent_jobs(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent jobs"""
        async with self.conn.execute(
            """
            SELECT * FROM jobs 
            ORDER BY started_at DESC 
            LIMIT ?
            """,
            (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
    
    async def cleanup_old_data(self, days: int = 30) -> int:
        """Delete data older than N days"""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Delete old predictions
        result = await self.conn.execute(
            "DELETE FROM predictions WHERE scan_time < ?",
            (cutoff,)
        )
        predictions_deleted = result.rowcount
        
        # Delete old failures
        await self.conn.execute(
            "DELETE FROM failures WHERE scan_time < ?",
            (cutoff,)
        )
        
        # Delete old jobs (only if all predictions deleted)
        await self.conn.execute(
            """
            DELETE FROM jobs 
            WHERE started_at < ? 
            AND id NOT IN (SELECT DISTINCT job_id FROM predictions)
            """,
            (cutoff,)
        )
        
        await self.conn.commit()
        logger.info("Cleanup completed", days=days, predictions_deleted=predictions_deleted)
        
        return predictions_deleted


# ============================================================================
# Global Instance
# ============================================================================

_predictions_db: Optional[PredictionsDB] = None


async def get_predictions_db() -> PredictionsDB:
    """Get or create global database instance"""
    global _predictions_db
    
    if _predictions_db is None:
        _predictions_db = PredictionsDB()
        await _predictions_db.connect()
    
    return _predictions_db


async def close_predictions_db() -> None:
    """Close global database instance"""
    global _predictions_db
    
    if _predictions_db:
        await _predictions_db.disconnect()
        _predictions_db = None

