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
                
                # 3. Build the new hash mapping with CURRENT-ticker priority.
                # A ticker can be the CURRENT of one chain *and* a predecessor
                # of another (e.g. META is the active ticker for Meta Platforms
                # ['FB','META'] AND is listed as predecessor of METV
                # ['META','METV'] because the Roundhill Ball Metaverse ETF used
                # to trade as META). When that happens, the "current" claim
                # must win — otherwise typing META resolves to the ETF.
                import orjson
                new_hash: Dict[str, str] = {}
                # Pass 1: every ticker that is chain[-1] of its own chain.
                for symbol, chain in chains.items():
                    if chain and chain[-1].upper() == str(symbol).upper():
                        new_hash[str(symbol).upper()] = orjson.dumps(chain).decode()
                # Pass 2: predecessors only if not already claimed as a current.
                for symbol, chain in chains.items():
                    if not chain:
                        continue
                    encoded_chain = orjson.dumps(chain).decode()
                    for old in chain[:-1]:
                        key = str(old).upper()
                        if key not in new_hash:
                            new_hash[key] = encoded_chain
                expanded_entries = len(new_hash)

                await self.redis.client.delete(TICKER_CHAIN_HASH)
                if new_hash:
                    pipe = self.redis.client.pipeline()
                    pipe.hset(TICKER_CHAIN_HASH, mapping=new_hash)
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
    
    @staticmethod
    def _instrument_suffix(ticker: str) -> str:
        """
        Return the instrument-type suffix of a ticker, or '' for common stock.

        Polygon uses the trailing letter(s) to distinguish related instruments
        issued by the same company:
          W  → warrants   (SOUNW, IPODW …)
          R  → rights     (AACGR …)
          U  → units      (OACCU …)
          p  → preferred  (TFINp, LOBpA …)

        A chain between two tickers is only valid when both have the SAME suffix
        (i.e. both are common stock, or both are warrants, etc.).
        Mixing types — e.g. SOUN (common) ↔ SOUNW (warrant) — produces false
        chains that redirect the common-stock chart to warrant price data.
        """
        import re
        # Preferred: trailing lowercase 'p' optionally followed by a class letter
        if re.search(r'p[A-Z]?$', ticker):
            return 'p'
        # Warrants, rights, units: single uppercase suffix letter
        m = re.search(r'[WRU]$', ticker)
        return m.group(0) if m else ''

    @staticmethod
    async def _fetch_figi_at(
        client: httpx.AsyncClient, ticker: str, date_str: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch the composite_figi of `ticker` as it was on `date_str` (YYYY-MM-DD).

        If `date_str` is None, returns the current composite_figi.
        Returns None on NOT_FOUND, network error, or missing field.
        """
        try:
            url = f"https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={POLYGON_API_KEY}"
            if date_str:
                url += f"&date={date_str}"
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("results", {}).get("composite_figi")
        except Exception:
            return None

    @staticmethod
    def _day_before(date_str: str) -> Optional[str]:
        """Return YYYY-MM-DD for the day before `date_str`, or None on parse error."""
        from datetime import datetime, timedelta
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            return (d - timedelta(days=1)).isoformat()
        except Exception:
            return None

    async def _scan_all_events(
        self, client: httpx.AsyncClient, tickers: List[str]
    ) -> Dict[str, List[str]]:
        """Scan ticker_change events for all tickers concurrently.

        Polygon's `/vX/reference/tickers/{T}/events?types=ticker_change` returns
        a list of events of the shape:

            { ticker_change: { ticker: "<symbol>" }, date: "YYYY-MM-DD" }

        Each event marks the date the listed `ticker` **started** trading. The
        most recent event therefore corresponds to the current ticker, and an
        OLD ticker was used between its own event date and the next event date.

        We validate every reported predecessor by fetching its historical
        `composite_figi` on the day before the next event. Only predecessors
        whose historical FIGI matches the current ticker's FIGI are accepted.

        This rejects Polygon's noisy cross-instrument events such as METV
        ("previously META, 2021-06-30") — the FIGI lookup for META on
        2022-01-30 returns NOT_FOUND, so the link is dropped.
        """
        chains: Dict[str, List[str]] = {}
        semaphore = asyncio.Semaphore(CONCURRENCY)
        errors = 0
        figi_rejections = 0
        inconsistent_events = 0

        async def check_ticker(ticker: str):
            nonlocal errors, figi_rejections, inconsistent_events
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
                    results = data.get("results", {}) or {}
                    events = results.get("events", []) or []
                    current_figi = results.get("composite_figi")

                    if not events or not current_figi:
                        return

                    # Normalize: (date, ticker), sorted ascending. Skip any
                    # event missing date or ticker.
                    normalized: List[tuple] = []
                    for event in events:
                        tc = event.get("ticker_change", {}) or {}
                        old = (tc.get("ticker", "") or "").upper()
                        ev_date = event.get("date", "") or ""
                        if old and ev_date:
                            normalized.append((ev_date, old))
                    if len(normalized) < 2:
                        # Need at least 2 events (predecessor + current) to
                        # validate any chain — otherwise the timeline is
                        # incomplete and we can't know when the predecessor
                        # stopped being valid.
                        return
                    normalized.sort(key=lambda x: x[0])

                    # The most recent event MUST be the current ticker. If
                    # Polygon's timeline doesn't end with `ticker`, the
                    # ticker_change graph is inconsistent for our purposes
                    # (e.g. a warrant whose only event references the common
                    # stock with no terminal "I became the warrant" event).
                    if normalized[-1][1] != ticker.upper():
                        inconsistent_events += 1
                        return

                    current_suffix = self._instrument_suffix(ticker)

                    # Build (old_ticker, end_date_exclusive) pairs. The end
                    # date is the date of the NEXT event — i.e. when this old
                    # ticker stopped being the active symbol.
                    candidates: List[tuple] = []
                    for i in range(len(normalized) - 1):
                        _, old = normalized[i]
                        next_date = normalized[i + 1][0]
                        if old == ticker.upper():
                            continue
                        # Cheap suffix gate first.
                        if self._instrument_suffix(old) != current_suffix:
                            continue
                        candidates.append((old, next_date))

                    if not candidates:
                        return

                    # FIGI validation. Runs serially per ticker so the outer
                    # semaphore still caps total concurrent Polygon calls.
                    validated_olds: List[tuple] = []
                    for old, end_date in candidates:
                        check_date = self._day_before(end_date)
                        if not check_date:
                            continue
                        old_figi = await self._fetch_figi_at(client, old, check_date)
                        if old_figi == current_figi:
                            validated_olds.append((end_date, old))
                        else:
                            figi_rejections += 1
                            logger.info(
                                "ticker_change_rejected_figi_mismatch",
                                current=ticker,
                                old=old,
                                check_date=check_date,
                                current_figi=current_figi,
                                old_figi=old_figi,
                            )

                    if not validated_olds:
                        return

                    # Order by end_date asc (oldest → newest) and append
                    # current as the final entry.
                    validated_olds.sort(key=lambda x: x[0])
                    ordered = [old for _, old in validated_olds]
                    ordered.append(ticker.upper())

                    if len(ordered) > 1:
                        chains[ticker] = ordered

                except Exception as e:
                    errors += 1
                    logger.debug("check_ticker_error", ticker=ticker, error=str(e))

        # Run all concurrently
        tasks = [check_ticker(t) for t in tickers]
        await asyncio.gather(*tasks)

        if errors > 0:
            logger.warning("ticker_event_scan_errors", count=errors)
        if figi_rejections > 0:
            logger.info("ticker_change_figi_rejections", count=figi_rejections)
        if inconsistent_events > 0:
            logger.info("ticker_change_inconsistent_timelines", count=inconsistent_events)

        return chains
