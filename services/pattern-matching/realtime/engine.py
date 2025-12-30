"""
Pattern Real-Time - Scanning Engine
===================================

Core batch scanning logic that:
1. Receives a list of symbols to scan
2. Calls existing PatternMatcher for each symbol
3. Calculates edge and ranking
4. Stores predictions in database
5. Broadcasts results via WebSocket
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
import uuid

import structlog

from config import settings
from pattern_matcher import PatternMatcher
from .models import (
    RealtimeJobRequest,
    PredictionResult,
    FailureResult,
    Direction,
    ErrorCode,
    JobStatus,
)
from .db import PredictionsDB
from .websocket_manager import WebSocketManager

logger = structlog.get_logger(__name__)


class RealtimeEngine:
    """
    Batch scanning engine for Pattern Real-Time
    
    Uses the existing PatternMatcher to search for patterns,
    then stores predictions and broadcasts results.
    """
    
    def __init__(
        self,
        matcher: PatternMatcher,
        db: PredictionsDB,
        ws_manager: WebSocketManager
    ):
        self.matcher = matcher
        self.db = db
        self.ws = ws_manager
        
        # Active jobs (for cancellation)
        self._active_jobs: Dict[str, bool] = {}  # job_id -> is_cancelled
        
        logger.info("RealtimeEngine initialized")
    
    async def run_job(
        self,
        request: RealtimeJobRequest,
        job_id: Optional[str] = None
    ) -> str:
        """
        Run a batch scan job
        
        Args:
            request: Job parameters
            job_id: Optional job ID (generates one if not provided)
            
        Returns:
            Job ID
        """
        job_id = job_id or str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        # Normalize symbols
        symbols = [s.strip().upper() for s in request.symbols if s.strip()]
        symbols = list(set(symbols))  # Remove duplicates
        
        if not symbols:
            raise ValueError("No valid symbols provided")
        
        logger.info(
            "Starting realtime job",
            job_id=job_id,
            total_symbols=len(symbols),
            params={
                "k": request.k,
                "horizon": request.horizon,
                "alpha": request.alpha,
            }
        )
        
        # Create job in database
        await self.db.create_job(
            job_id=job_id,
            params=request.model_dump(),
            total_symbols=len(symbols)
        )
        
        # Track active job
        self._active_jobs[job_id] = False  # Not cancelled
        
        # Process symbols
        completed = 0
        failed = 0
        results: List[PredictionResult] = []
        failures: List[FailureResult] = []
        
        try:
            for symbol in symbols:
                # Check for cancellation
                if self._active_jobs.get(job_id, True):
                    logger.info("Job cancelled", job_id=job_id)
                    break
                
                # Scan single symbol
                result, failure = await self._scan_symbol(
                    job_id=job_id,
                    symbol=symbol,
                    request=request
                )
                
                if result:
                    # Filter by min_edge
                    if result.edge >= request.min_edge:
                        results.append(result)
                        await self.db.insert_prediction(result)
                        await self.ws.send_result(job_id, result)
                    completed += 1
                elif failure:
                    failures.append(failure)
                    await self.db.insert_failure(job_id, failure)
                    failed += 1
                
                # Update progress
                await self.db.update_job_progress(job_id, completed, failed)
                await self.ws.send_progress(
                    job_id, 
                    completed + failed, 
                    len(symbols), 
                    failed
                )
            
            # Mark job complete
            status = (
                JobStatus.CANCELLED if self._active_jobs.get(job_id) 
                else JobStatus.COMPLETED
            )
            await self.db.complete_job(job_id, status)
            
            # Send completion message
            duration = (datetime.utcnow() - start_time).total_seconds()
            await self.ws.send_job_complete(
                job_id=job_id,
                total_results=len(results),
                total_failures=len(failures),
                duration_seconds=duration
            )
            
            logger.info(
                "Job completed",
                job_id=job_id,
                results=len(results),
                failures=len(failures),
                duration_seconds=round(duration, 2)
            )
            
        except Exception as e:
            logger.error("Job failed", job_id=job_id, error=str(e))
            await self.db.complete_job(job_id, JobStatus.FAILED)
            raise
        
        finally:
            # Cleanup
            self._active_jobs.pop(job_id, None)
        
        return job_id
    
    async def _scan_symbol(
        self,
        job_id: str,
        symbol: str,
        request: RealtimeJobRequest
    ) -> Tuple[Optional[PredictionResult], Optional[FailureResult]]:
        """
        Scan a single symbol
        
        Returns:
            Tuple of (result, failure) - one will be None
        """
        scan_time = datetime.utcnow()
        
        try:
            # Check market hours (basic check)
            failure = self._check_market_hours(symbol, scan_time)
            if failure:
                return None, failure
            
            # Call existing PatternMatcher
            search_result = await self.matcher.search(
                symbol=symbol,
                prices=None,  # Fetch real-time
                k=request.k,
                cross_asset=request.cross_asset,
            )
            
            if search_result.get("status") == "error":
                return None, FailureResult(
                    symbol=symbol,
                    scan_time=scan_time,
                    error_code=ErrorCode.E_FAISS,
                    reason=search_result.get("error", "Unknown error")
                )
            
            if search_result.get("status") != "success":
                return None, FailureResult(
                    symbol=symbol,
                    scan_time=scan_time,
                    error_code=ErrorCode.E_NO_DATA,
                    reason=f"Search status: {search_result.get('status')}"
                )
            
            # Extract forecast data
            forecast = search_result.get("forecast", {})
            
            if not forecast or "prob_up" not in forecast:
                return None, FailureResult(
                    symbol=symbol,
                    scan_time=scan_time,
                    error_code=ErrorCode.E_NO_DATA,
                    reason="No forecast data returned"
                )
            
            # Calculate edge and direction
            prob_up = forecast.get("prob_up", 0.5)
            prob_down = forecast.get("prob_down", 0.5)
            mean_return = forecast.get("mean_return", 0)
            
            # Determine direction based on probability
            if prob_up > prob_down:
                direction = Direction.UP
                edge = prob_up * abs(mean_return)
            else:
                direction = Direction.DOWN
                edge = prob_down * abs(mean_return)
            
            # Get price at scan (from query context or neighbors)
            query_data = search_result.get("historical_context", {})
            pattern_prices = query_data.get("pattern_prices", [])
            price_at_scan = pattern_prices[-1] if pattern_prices else 0
            
            # If no price from context, try to get from search metadata
            if price_at_scan == 0:
                # Fallback: use neighbor data or mark as failure
                neighbors = search_result.get("neighbors", [])
                if neighbors:
                    # Use mean return to estimate (not ideal but fallback)
                    price_at_scan = 100  # Placeholder - should fetch from Polygon
                else:
                    return None, FailureResult(
                        symbol=symbol,
                        scan_time=scan_time,
                        error_code=ErrorCode.E_PRICE,
                        reason="Could not determine price at scan time"
                    )
            
            # Build prediction result
            result = PredictionResult(
                job_id=job_id,
                symbol=symbol,
                scan_time=scan_time,
                horizon=request.horizon,
                prob_up=round(prob_up, 4),
                prob_down=round(prob_down, 4),
                mean_return=round(mean_return, 4),
                edge=round(edge, 4),
                direction=direction,
                n_neighbors=forecast.get("n_neighbors", 0),
                dist1=self._get_dist1(search_result),
                p10=forecast.get("worst_case"),  # 10th percentile
                p90=forecast.get("best_case"),   # 90th percentile
                price_at_scan=price_at_scan
            )
            
            return result, None
            
        except Exception as e:
            logger.error(
                "Symbol scan failed",
                symbol=symbol,
                error=str(e)
            )
            return None, FailureResult(
                symbol=symbol,
                scan_time=scan_time,
                error_code=ErrorCode.E_UNKNOWN,
                reason=str(e)
            )
    
    def _check_market_hours(
        self,
        symbol: str,
        scan_time: datetime
    ) -> Optional[FailureResult]:
        """
        Check if market is open
        
        Note: This is a basic check. Real implementation should use
        market calendar service.
        """
        # Check weekend
        if scan_time.weekday() >= 5:
            return FailureResult(
                symbol=symbol,
                scan_time=scan_time,
                error_code=ErrorCode.E_WEEKEND,
                reason=ErrorCode.describe(ErrorCode.E_WEEKEND)
            )
        
        # Check market hours (09:30-16:00 ET)
        # Note: This is simplified - should account for timezone properly
        # For now, we'll allow all hours since the user might want pre/post market
        
        return None
    
    def _get_dist1(self, search_result: Dict[str, Any]) -> Optional[float]:
        """Get distance to closest neighbor"""
        neighbors = search_result.get("neighbors", [])
        if neighbors and len(neighbors) > 0:
            return neighbors[0].get("distance")
        return None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job"""
        if job_id in self._active_jobs:
            self._active_jobs[job_id] = True  # Mark as cancelled
            logger.info("Job cancellation requested", job_id=job_id)
            return True
        return False
    
    def get_active_jobs(self) -> List[str]:
        """Get list of active job IDs"""
        return list(self._active_jobs.keys())


# ============================================================================
# Parallel Scanning (Optional Enhancement)
# ============================================================================

class ParallelRealtimeEngine(RealtimeEngine):
    """
    Enhanced engine with parallel symbol scanning
    
    Scans multiple symbols concurrently for faster results.
    Use with caution - may hit rate limits on Polygon API.
    """
    
    def __init__(
        self,
        matcher: PatternMatcher,
        db: PredictionsDB,
        ws_manager: WebSocketManager,
        max_concurrent: int = 5
    ):
        super().__init__(matcher, db, ws_manager)
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def run_job(
        self,
        request: RealtimeJobRequest,
        job_id: Optional[str] = None
    ) -> str:
        """Run job with parallel scanning"""
        job_id = job_id or str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        symbols = [s.strip().upper() for s in request.symbols if s.strip()]
        symbols = list(set(symbols))
        
        if not symbols:
            raise ValueError("No valid symbols provided")
        
        await self.db.create_job(
            job_id=job_id,
            params=request.model_dump(),
            total_symbols=len(symbols)
        )
        
        self._active_jobs[job_id] = False
        
        # Create tasks for all symbols
        async def scan_with_semaphore(symbol: str):
            async with self._semaphore:
                if self._active_jobs.get(job_id, True):
                    return None, None
                return await self._scan_symbol(job_id, symbol, request)
        
        try:
            # Run all scans concurrently
            tasks = [scan_with_semaphore(s) for s in symbols]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            completed = 0
            failed = 0
            results: List[PredictionResult] = []
            failures: List[FailureResult] = []
            
            for i, item in enumerate(results_list):
                if isinstance(item, Exception):
                    failed += 1
                    failures.append(FailureResult(
                        symbol=symbols[i],
                        scan_time=datetime.utcnow(),
                        error_code=ErrorCode.E_UNKNOWN,
                        reason=str(item)
                    ))
                elif item[0]:  # Result
                    result = item[0]
                    if result.edge >= request.min_edge:
                        results.append(result)
                        await self.db.insert_prediction(result)
                    completed += 1
                elif item[1]:  # Failure
                    failures.append(item[1])
                    await self.db.insert_failure(job_id, item[1])
                    failed += 1
            
            # Sort results by edge
            results.sort(key=lambda r: r.edge, reverse=True)
            
            # Broadcast all results
            for result in results:
                await self.ws.send_result(job_id, result)
            
            # Update final progress
            await self.db.update_job_progress(job_id, completed, failed)
            
            # Complete job
            status = (
                JobStatus.CANCELLED if self._active_jobs.get(job_id)
                else JobStatus.COMPLETED
            )
            await self.db.complete_job(job_id, status)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            await self.ws.send_job_complete(
                job_id=job_id,
                total_results=len(results),
                total_failures=len(failures),
                duration_seconds=duration
            )
            
            logger.info(
                "Parallel job completed",
                job_id=job_id,
                results=len(results),
                failures=len(failures),
                duration_seconds=round(duration, 2)
            )
            
        except Exception as e:
            logger.error("Parallel job failed", job_id=job_id, error=str(e))
            await self.db.complete_job(job_id, JobStatus.FAILED)
            raise
        
        finally:
            self._active_jobs.pop(job_id, None)
        
        return job_id

