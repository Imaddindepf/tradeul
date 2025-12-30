"""
Pattern Real-Time - Verification Worker
=======================================

Background task that verifies predictions after their horizon has passed.

Process:
1. Find predictions where scan_time + horizon < now and not yet verified
2. Fetch current/actual price at horizon time
3. Calculate actual return
4. Determine if prediction was correct (direction match)
5. Calculate PnL
6. Update database
7. Broadcast verification result via WebSocket
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import httpx

import structlog

from config import settings
from .models import (
    PredictionResult,
    VerificationResult,
    Direction,
)
from .db import PredictionsDB
from .websocket_manager import WebSocketManager

logger = structlog.get_logger(__name__)


class VerificationWorker:
    """
    Background worker that verifies predictions
    
    Runs continuously, checking every minute for predictions
    that need verification.
    """
    
    def __init__(
        self,
        db: PredictionsDB,
        ws_manager: WebSocketManager,
        check_interval: int = 60,  # seconds
        batch_size: int = 50
    ):
        self.db = db
        self.ws = ws_manager
        self.check_interval = check_interval
        self.batch_size = batch_size
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._http_client: Optional[httpx.AsyncClient] = None
        
        # Stats
        self._total_verified = 0
        self._total_correct = 0
        self._last_check: Optional[datetime] = None
        
        logger.info(
            "VerificationWorker initialized",
            check_interval=check_interval,
            batch_size=batch_size
        )
    
    async def start(self) -> None:
        """Start the verification worker"""
        if self._running:
            logger.warning("Worker already running")
            return
        
        self._running = True
        self._http_client = httpx.AsyncClient(timeout=10.0)
        self._task = asyncio.create_task(self._run_loop())
        
        logger.info("VerificationWorker started")
    
    async def stop(self) -> None:
        """Stop the verification worker"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        
        logger.info("VerificationWorker stopped")
    
    async def _run_loop(self) -> None:
        """Main verification loop"""
        logger.info("Verification loop started")
        
        while self._running:
            try:
                await self._verify_pending()
                self._last_check = datetime.utcnow()
            except Exception as e:
                logger.error("Verification loop error", error=str(e))
            
            # Wait before next check
            await asyncio.sleep(self.check_interval)
        
        logger.info("Verification loop stopped")
    
    async def _verify_pending(self) -> int:
        """
        Verify all pending predictions that are ready
        
        Returns:
            Number of predictions verified
        """
        # Get pending predictions
        pending = await self.db.get_pending_predictions(limit=self.batch_size)
        
        if not pending:
            logger.debug("No pending predictions to verify")
            return 0
        
        logger.info(f"Verifying {len(pending)} predictions")
        
        verified_count = 0
        
        for prediction in pending:
            try:
                success = await self._verify_single(prediction)
                if success:
                    verified_count += 1
            except Exception as e:
                logger.error(
                    "Failed to verify prediction",
                    prediction_id=prediction.id,
                    symbol=prediction.symbol,
                    error=str(e)
                )
        
        logger.info(f"Verified {verified_count}/{len(pending)} predictions")
        return verified_count
    
    async def _verify_single(self, prediction: PredictionResult) -> bool:
        """
        Verify a single prediction
        
        Returns:
            True if verified successfully
        """
        # Calculate expected horizon time
        horizon_time = prediction.scan_time + timedelta(minutes=prediction.horizon)
        
        # Fetch price at horizon
        current_price = await self._get_price(prediction.symbol)
        
        if current_price is None:
            logger.warning(
                "Could not get price for verification",
                symbol=prediction.symbol
            )
            return False
        
        # Calculate actual return
        actual_return = (
            (current_price - prediction.price_at_scan) 
            / prediction.price_at_scan * 100
        )
        
        # Determine if prediction was correct
        if prediction.direction == Direction.UP:
            was_correct = actual_return > 0
            pnl = actual_return  # Long position
        else:
            was_correct = actual_return < 0
            pnl = -actual_return  # Short position (profit when price goes down)
        
        # Update database
        await self.db.verify_prediction(
            prediction_id=prediction.id,
            price_at_horizon=current_price,
            actual_return=round(actual_return, 4),
            was_correct=was_correct,
            pnl=round(pnl, 4)
        )
        
        # Update stats
        self._total_verified += 1
        if was_correct:
            self._total_correct += 1
        
        # Broadcast verification
        verification = VerificationResult(
            prediction_id=prediction.id,
            symbol=prediction.symbol,
            actual_return=round(actual_return, 4),
            was_correct=was_correct,
            pnl=round(pnl, 4),
            verified_at=datetime.utcnow()
        )
        
        await self.ws.send_verification(verification)
        
        logger.info(
            "Prediction verified",
            symbol=prediction.symbol,
            direction=prediction.direction.value,
            predicted_return=prediction.mean_return,
            actual_return=round(actual_return, 4),
            was_correct=was_correct,
            pnl=round(pnl, 4)
        )
        
        return True
    
    async def _get_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol
        
        Uses Polygon API for real-time prices.
        """
        if not self._http_client:
            return None
        
        try:
            # Use Polygon snapshot endpoint for latest price
            url = (
                f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
                f"?apiKey={settings.polygon_api_key}"
            )
            
            response = await self._http_client.get(url)
            response.raise_for_status()
            
            data = response.json()
            ticker_data = data.get("ticker", {})
            
            # Get last trade price or day close
            day_data = ticker_data.get("day", {})
            last_trade = ticker_data.get("lastTrade", {})
            
            price = last_trade.get("p") or day_data.get("c")
            
            if price:
                return float(price)
            
            # Fallback: try minute aggregates
            return await self._get_price_from_aggs(symbol)
            
        except Exception as e:
            logger.warning(
                "Failed to get price from snapshot",
                symbol=symbol,
                error=str(e)
            )
            return await self._get_price_from_aggs(symbol)
    
    async def _get_price_from_aggs(self, symbol: str) -> Optional[float]:
        """
        Fallback: get latest price from minute aggregates
        """
        if not self._http_client:
            return None
        
        try:
            # Get last 5 minutes of data
            now = datetime.utcnow()
            from_ts = int((now.timestamp() - 300) * 1000)  # 5 min ago
            to_ts = int(now.timestamp() * 1000)
            
            url = (
                f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute"
                f"/{from_ts}/{to_ts}"
                f"?adjusted=true&sort=desc&limit=1"
                f"&apiKey={settings.polygon_api_key}"
            )
            
            response = await self._http_client.get(url)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if results:
                return float(results[0]["c"])  # Close price
            
            return None
            
        except Exception as e:
            logger.warning(
                "Failed to get price from aggs",
                symbol=symbol,
                error=str(e)
            )
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics"""
        win_rate = (
            self._total_correct / self._total_verified 
            if self._total_verified > 0 else 0
        )
        
        return {
            "running": self._running,
            "check_interval_seconds": self.check_interval,
            "batch_size": self.batch_size,
            "total_verified": self._total_verified,
            "total_correct": self._total_correct,
            "win_rate": round(win_rate, 4),
            "last_check": self._last_check.isoformat() if self._last_check else None
        }


# ============================================================================
# Manual Verification (for testing/backfill)
# ============================================================================

async def verify_prediction_manually(
    db: PredictionsDB,
    ws_manager: WebSocketManager,
    prediction_id: str,
    actual_price: float
) -> Optional[VerificationResult]:
    """
    Manually verify a single prediction with a known price
    
    Useful for testing or backfilling verification data.
    """
    # Get prediction from DB
    predictions = await db.get_predictions_for_job("", limit=10000)
    prediction = next((p for p in predictions if p.id == prediction_id), None)
    
    if not prediction:
        logger.error("Prediction not found", prediction_id=prediction_id)
        return None
    
    if prediction.verified_at:
        logger.warning("Prediction already verified", prediction_id=prediction_id)
        return None
    
    # Calculate
    actual_return = (
        (actual_price - prediction.price_at_scan) 
        / prediction.price_at_scan * 100
    )
    
    if prediction.direction == Direction.UP:
        was_correct = actual_return > 0
        pnl = actual_return
    else:
        was_correct = actual_return < 0
        pnl = -actual_return
    
    # Update DB
    await db.verify_prediction(
        prediction_id=prediction_id,
        price_at_horizon=actual_price,
        actual_return=round(actual_return, 4),
        was_correct=was_correct,
        pnl=round(pnl, 4)
    )
    
    # Create result
    result = VerificationResult(
        prediction_id=prediction_id,
        symbol=prediction.symbol,
        actual_return=round(actual_return, 4),
        was_correct=was_correct,
        pnl=round(pnl, 4),
        verified_at=datetime.utcnow()
    )
    
    # Broadcast
    await ws_manager.send_verification(result)
    
    return result

