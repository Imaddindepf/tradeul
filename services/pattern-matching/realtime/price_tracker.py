"""
Price Tracker - Real-time P&L updates for pending predictions.

Subscribes to real-time price updates and broadcasts unrealized P&L
to connected WebSocket clients.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Dict, Set, Optional
import httpx
import websockets
import structlog

from .db import PredictionsDB
from .websocket_manager import WebSocketManager

logger = structlog.get_logger(__name__)

# Polygon WebSocket URL
POLYGON_WS_URL = "wss://socket.polygon.io/stocks"
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")


class PriceTracker:
    """
    Tracks real-time prices for symbols with pending predictions.
    Broadcasts unrealized P&L updates via WebSocket.
    """
    
    def __init__(
        self,
        db: PredictionsDB,
        ws_manager: WebSocketManager,
        update_interval_ms: int = 500  # Throttle updates to avoid flooding
    ):
        self.db = db
        self.ws_manager = ws_manager
        self.update_interval_ms = update_interval_ms
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._polygon_ws: Optional[websockets.WebSocketClientProtocol] = None
        
        # Track subscribed symbols and their latest prices
        self._subscribed_symbols: Set[str] = set()
        self._latest_prices: Dict[str, float] = {}
        self._pending_predictions: Dict[str, dict] = {}  # prediction_id -> prediction data
        
        # Throttling
        self._last_broadcast: Dict[str, float] = {}  # symbol -> timestamp
        
    async def start(self):
        """Start the price tracker."""
        if self._running:
            return
            
        self._running = True
        logger.info("price_tracker_starting")
        
        # Start main loop
        self._task = asyncio.create_task(self._run())
        
    async def stop(self):
        """Stop the price tracker."""
        self._running = False
        
        if self._polygon_ws:
            await self._polygon_ws.close()
            self._polygon_ws = None
            
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
        logger.info("price_tracker_stopped")
        
    async def _run(self):
        """Main loop - uses HTTP polling for price updates."""
        # Use polling mode - more reliable for both market hours and after-hours
        # WebSocket mode can be enabled later for ultra-low latency during market hours
        await self._polling_fallback()
                
    async def _connect_and_process(self):
        """Connect to Polygon WebSocket and process messages."""
        if not POLYGON_API_KEY:
            logger.warning("price_tracker_no_api_key", msg="POLYGON_API_KEY not set, using polling fallback")
            await self._polling_fallback()
            return
            
        uri = POLYGON_WS_URL
        logger.info("price_tracker_connecting", uri=uri)
        
        async with websockets.connect(uri) as ws:
            self._polygon_ws = ws
            
            # Wait for initial connected message
            initial = await ws.recv()
            initial_data = json.loads(initial)
            logger.info("price_tracker_initial_response", response=initial_data)
            
            # Authenticate
            auth_msg = {"action": "auth", "params": POLYGON_API_KEY}
            await ws.send(json.dumps(auth_msg))
            
            # Wait for auth response
            response = await ws.recv()
            data = json.loads(response)
            if isinstance(data, list) and len(data) > 0:
                status = data[0].get("status")
                if status == "auth_success":
                    logger.info("price_tracker_authenticated")
                elif status == "connected":
                    # Sometimes auth response comes as another message
                    response2 = await ws.recv()
                    data2 = json.loads(response2)
                    if isinstance(data2, list) and data2[0].get("status") == "auth_success":
                        logger.info("price_tracker_authenticated")
                    else:
                        logger.error("price_tracker_auth_failed", response=data2)
                        return
                else:
                    logger.error("price_tracker_auth_failed", response=data)
                    return
            
            # Start subscription manager task
            sub_task = asyncio.create_task(self._manage_subscriptions())
            
            try:
                # Process incoming messages
                async for message in ws:
                    if not self._running:
                        break
                    await self._process_message(message)
            finally:
                sub_task.cancel()
                
    async def _manage_subscriptions(self):
        """Periodically update subscriptions based on pending predictions."""
        while self._running:
            try:
                await self._update_subscriptions()
            except Exception as e:
                logger.error("subscription_update_error", error=str(e))
            await asyncio.sleep(5)  # Check for new predictions every 5 seconds
            
    async def _update_subscriptions(self):
        """Update Polygon subscriptions based on pending predictions."""
        # Get current pending predictions
        pending = await self.db.get_pending_predictions()
        
        # Build prediction lookup
        new_predictions = {}
        needed_symbols = set()
        
        for pred in pending:
            pred_id = pred["id"]
            symbol = pred["symbol"]
            new_predictions[pred_id] = pred
            needed_symbols.add(symbol)
            
        self._pending_predictions = new_predictions
        
        # Calculate symbols to subscribe/unsubscribe
        to_subscribe = needed_symbols - self._subscribed_symbols
        to_unsubscribe = self._subscribed_symbols - needed_symbols
        
        if not self._polygon_ws:
            return
            
        # Unsubscribe from symbols we no longer need
        if to_unsubscribe:
            unsub_msg = {
                "action": "unsubscribe",
                "params": ",".join(f"T.{s}" for s in to_unsubscribe)
            }
            await self._polygon_ws.send(json.dumps(unsub_msg))
            self._subscribed_symbols -= to_unsubscribe
            logger.info("price_tracker_unsubscribed", symbols=list(to_unsubscribe))
            
        # Subscribe to new symbols
        if to_subscribe:
            sub_msg = {
                "action": "subscribe",
                "params": ",".join(f"T.{s}" for s in to_subscribe)
            }
            await self._polygon_ws.send(json.dumps(sub_msg))
            self._subscribed_symbols |= to_subscribe
            logger.info("price_tracker_subscribed", symbols=list(to_subscribe))
            
    async def _process_message(self, message: str):
        """Process a message from Polygon WebSocket."""
        try:
            data = json.loads(message)
            
            if not isinstance(data, list):
                return
                
            for item in data:
                ev = item.get("ev")
                
                if ev == "T":  # Trade event
                    symbol = item.get("sym")
                    price = item.get("p")
                    
                    if symbol and price:
                        self._latest_prices[symbol] = price
                        await self._broadcast_price_update(symbol, price)
                        
        except json.JSONDecodeError:
            pass
        except Exception as e:
            logger.error("message_processing_error", error=str(e))
            
    async def _broadcast_price_update(self, symbol: str, current_price: float):
        """Broadcast unrealized P&L for all predictions of this symbol."""
        now = asyncio.get_event_loop().time()
        
        # Throttle updates per symbol
        last = self._last_broadcast.get(symbol, 0)
        if (now - last) * 1000 < self.update_interval_ms:
            return
        self._last_broadcast[symbol] = now
        
        # Find all pending predictions for this symbol
        for pred_id, pred in self._pending_predictions.items():
            if pred["symbol"] != symbol:
                continue
                
            price_at_scan = pred.get("price_at_scan")
            if not price_at_scan:
                continue
                
            # Calculate unrealized return
            unrealized_return = ((current_price - price_at_scan) / price_at_scan) * 100
            
            # Calculate time remaining
            scan_time_raw = pred["scan_time"]
            if isinstance(scan_time_raw, datetime):
                scan_time = scan_time_raw if scan_time_raw.tzinfo else scan_time_raw.replace(tzinfo=timezone.utc)
            else:
                scan_time = datetime.fromisoformat(str(scan_time_raw).replace("Z", "+00:00"))
            horizon_minutes = int(pred.get("horizon", 10))
            elapsed = (datetime.now(timezone.utc) - scan_time).total_seconds() / 60
            minutes_remaining = max(0, horizon_minutes - elapsed)
            
            # Determine if prediction is currently correct
            direction = pred.get("direction", "UP")
            is_correct = (direction == "UP" and unrealized_return > 0) or \
                        (direction == "DOWN" and unrealized_return < 0)
            
            # Calculate directional P&L
            if direction == "UP":
                unrealized_pnl = unrealized_return
            else:
                unrealized_pnl = -unrealized_return
            
            # Broadcast update to ALL connected clients
            # (not just job subscribers - price updates are relevant to anyone with the prediction)
            # Format: { type: "price_update", price_update: { ... } } - frontend expects this structure
            update = {
                "type": "price_update",
                "price_update": {
                "prediction_id": pred_id,
                "job_id": pred.get("job_id"),
                "symbol": symbol,
                "current_price": current_price,
                "price_at_scan": price_at_scan,
                "unrealized_return": round(unrealized_return, 4),
                "unrealized_pnl": round(unrealized_pnl, 4),
                "direction": direction,
                "is_currently_correct": is_correct,
                "minutes_remaining": round(minutes_remaining, 2),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            }
            
            # Use broadcast_all instead of broadcast_to_job - clients may have
            # unsubscribed from old jobs but still want price updates for active predictions
            sent = await self.ws_manager.broadcast_all(update)
            if sent > 0:
                logger.debug("price_update_broadcast", symbol=symbol, clients=sent)
            
    async def _polling_fallback(self):
        """Fallback to HTTP polling if WebSocket not available."""
        logger.info("price_tracker_polling_mode")
        
        while self._running:
            try:
                # Get ACTIVE predictions (still within horizon)
                pending = await self.db.get_active_predictions()
                
                if not pending:
                    await asyncio.sleep(5)
                    continue
                    
                # Group by symbol - pending are PredictionResult objects
                symbols = list(set(p.symbol for p in pending))
                self._pending_predictions = {p.id: p.model_dump() for p in pending}
                
                # Fetch current prices via HTTP
                prices = await self._fetch_prices_http(symbols)
                
                # Broadcast updates
                for symbol, price in prices.items():
                    self._latest_prices[symbol] = price
                    await self._broadcast_price_update(symbol, price)
                    
                await asyncio.sleep(1)  # Poll every second
                
            except Exception as e:
                import traceback
                logger.error("polling_error", error=str(e), trace=traceback.format_exc())
                await asyncio.sleep(5)
                
    async def _fetch_prices_http(self, symbols: list) -> Dict[str, float]:
        """Fetch current prices via HTTP API."""
        prices = {}
        
        if not symbols:
            return prices
            
        try:
            # Use Polygon snapshot endpoint
            tickers = ",".join(symbols)
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers?tickers={tickers}&apiKey={POLYGON_API_KEY}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    for ticker in data.get("tickers", []):
                        symbol = ticker.get("ticker")
                        # Use last trade price or day's close
                        price = ticker.get("lastTrade", {}).get("p") or \
                               ticker.get("day", {}).get("c") or \
                               ticker.get("prevDay", {}).get("c")
                        if symbol and price:
                            prices[symbol] = price
                            
        except Exception as e:
            logger.error("http_price_fetch_error", error=str(e))
            
        return prices
        
    def get_stats(self) -> dict:
        """Get tracker statistics."""
        return {
            "running": self._running,
            "subscribed_symbols": list(self._subscribed_symbols),
            "tracked_predictions": len(self._pending_predictions),
            "latest_prices": dict(self._latest_prices),
            "update_interval_ms": self.update_interval_ms
        }

