"""
Build Ticker Chain Task
=======================

Escanea todos los tickers activos en Polygon buscando cambios de símbolo
(ticker_change events) y construye el hash Redis `ticker:chain`.

Ejemplos de cadenas:
- META: ["FB", "META"]
- DJT: ["DWAC", "DJT"]
- INEO: ["SAG", "INEO"]

Solo ~8% de tickers tienen cambios. Se ejecuta semanalmente (domingos 1:00 AM ET).
Escaneo completo ~90 segundos con concurrency=50.
"""

import asyncio
import os
import sys
sys.path.append('/app')

from datetime import date
from typing import Dict, List, Optional

import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
TICKER_CHAIN_HASH = "ticker:chain"
CONCURRENCY = 50

logger = get_logger(__name__)


class BuildTickerChainTask:
    """
    Tarea: Construir mapa de cadenas de tickers en Redis
    
    Escanea Polygon events API para detectar ticker changes y
    construye cadenas ordenadas old→new para cada ticker afectado.
    """
    
    name = "build_ticker_chain"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient = None):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar construcción de cadenas de tickers.
        
        1. Obtener todos los tickers activos de Polygon
        2. Consultar events API para cada uno (concurrency=50)
        3. Construir cadenas y guardar en Redis hash
        """
        logger.info("build_ticker_chain_starting", target_date=str(target_date))
        
        stats = {
            "success": True,
            "tickers_scanned": 0,
            "chains_built": 0,
            "errors": 0,
            "examples": []
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # 1. Get all active tickers
                tickers = await self._fetch_all_tickers(client)
                stats["tickers_scanned"] = len(tickers)
                
                if not tickers:
                    logger.error("no_tickers_found")
                    stats["success"] = False
                    return stats
                
                logger.info("tickers_fetched", count=len(tickers))
                
                # 2. Scan events for all tickers (concurrent)
                chains = await self._scan_all_events(client, tickers)
                stats["chains_built"] = len(chains)
                
                # 3. Clear old hash and populate new one
                await self.redis.client.delete(TICKER_CHAIN_HASH)
                
                pipe = self.redis.client.pipeline()
                # Store chain for BOTH the active symbol and all legacy aliases.
                # This guarantees direct HGET for old ticker queries.
                expanded_entries = 0
                for symbol, chain in chains.items():
                    import orjson
                    encoded_chain = orjson.dumps(chain).decode()
                    members = {symbol, *chain}
                    for member in members:
                        pipe.hset(TICKER_CHAIN_HASH, str(member).upper(), encoded_chain)
                        expanded_entries += 1
                
                if chains:
                    await pipe.execute()
                
                # Log examples
                examples = list(chains.items())[:5]
                stats["examples"] = [
                    {"symbol": s, "chain": c} for s, c in examples
                ]
                
                logger.info(
                    "build_ticker_chain_completed",
                    chains_built=len(chains),
                    hash_entries=expanded_entries,
                    examples=stats["examples"]
                )
                
                # Save last run timestamp
                await self.redis.set(
                    "maintenance:last_ticker_chain_build",
                    target_date.isoformat(),
                    ttl=86400 * 30
                )
                
                return stats
                
        except Exception as e:
            logger.error("build_ticker_chain_failed", error=str(e))
            stats["success"] = False
            stats["error"] = str(e)
            return stats
    
    async def _fetch_all_tickers(self, client: httpx.AsyncClient) -> List[str]:
        """Fetch all active US stock tickers from Polygon (paginated)."""
        all_tickers = []
        next_url = None
        page = 1
        
        while page <= 20:
            try:
                if next_url:
                    url = next_url
                else:
                    url = (
                        f"https://api.polygon.io/v3/reference/tickers"
                        f"?market=stocks&locale=us&active=true&limit=1000"
                        f"&apiKey={POLYGON_API_KEY}"
                    )
                
                resp = await client.get(url)
                if resp.status_code != 200:
                    break
                
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    break
                
                all_tickers.extend(r["ticker"] for r in results)
                
                next_url = data.get("next_url")
                if not next_url:
                    break
                if "apiKey" not in next_url:
                    next_url = f"{next_url}&apiKey={POLYGON_API_KEY}"
                
                page += 1
                await asyncio.sleep(0.15)
                
            except Exception as e:
                logger.warning("ticker_fetch_page_error", page=page, error=str(e))
                break
        
        return all_tickers
    
    async def _scan_all_events(
        self, client: httpx.AsyncClient, tickers: List[str]
    ) -> Dict[str, List[str]]:
        """Scan ticker_change events for all tickers concurrently."""
        chains: Dict[str, List[str]] = {}
        semaphore = asyncio.Semaphore(CONCURRENCY)
        errors = 0
        
        async def check_ticker(ticker: str):
            nonlocal errors
            async with semaphore:
                try:
                    url = (
                        f"https://api.polygon.io/vX/reference/tickers/{ticker}/events"
                        f"?types=ticker_change&apiKey={POLYGON_API_KEY}"
                    )
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        return
                    
                    data = resp.json()
                    events = data.get("results", {}).get("events", [])
                    
                    if not events:
                        return
                    
                    # Build chain from events
                    # Events contain ticker_change with old/new ticker
                    chain_set = set()
                    chain_set.add(ticker)
                    
                    for event in events:
                        tc = event.get("ticker_change", {})
                        old = tc.get("ticker", "")
                        if old:
                            chain_set.add(old)
                    
                    if len(chain_set) > 1:
                        # Order by event dates (oldest first)
                        ordered = self._order_chain(ticker, events)
                        chains[ticker] = ordered
                        
                except Exception:
                    errors += 1
        
        # Run all concurrently
        tasks = [check_ticker(t) for t in tickers]
        await asyncio.gather(*tasks)
        
        if errors > 0:
            logger.warning("ticker_event_scan_errors", count=errors)
        
        return chains
    
    def _order_chain(self, current_ticker: str, events: List[dict]) -> List[str]:
        """
        Order ticker chain from oldest to newest.
        
        Events have ticker_change.ticker (old ticker) and date.
        We build the chain chronologically.
        """
        # Collect all (date, old_ticker) pairs
        changes = []
        for event in events:
            tc = event.get("ticker_change", {})
            old_ticker = tc.get("ticker", "")
            event_date = event.get("date", "")
            if old_ticker and event_date:
                changes.append((event_date, old_ticker))
        
        # Sort by date ascending (oldest first)
        changes.sort(key=lambda x: x[0])
        
        # Build chain: oldest ticker first, current ticker last
        chain = [c[1] for c in changes]
        if current_ticker not in chain:
            chain.append(current_ticker)
        elif chain[-1] != current_ticker:
            chain.remove(current_ticker)
            chain.append(current_ticker)
        
        return chain
