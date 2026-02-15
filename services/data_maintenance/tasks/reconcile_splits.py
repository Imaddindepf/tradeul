"""
Reconcile Splits Task
=====================

Detecta splits recientes de Polygon y re-descarga los datos históricos
afectados que los loaders normales no actualizan.

PROBLEMA:
- load_volume_slots solo recarga los últimos 10 días
- load_ohlc / ohlc_loader solo cargan días "incompletos" (< 10K symbols)
- Cuando un ticker hace split, Polygon ajusta retroactivamente TODOS los datos
  con adjusted=true, pero nuestros datos antiguos quedan con valores pre-split

SOLUCIÓN:
- Consultar splits recientes a Polygon API (últimos 30 días)
- Para cada ticker con split, comparar nuestros datos vs market_data_daily (fuente de verdad)
- Si hay discrepancia, re-descargar minute bars de Polygon API adjusted=true
- Reconstruir volume_slots con la lógica exacta del loader
- También re-descargar daily bars para market_data_daily si es necesario

CUÁNDO SE EJECUTA:
- Después de load_ohlc y load_volume_slots en el ciclo de mantenimiento de 3:00 AM
- Solo si hay splits detectados que afectan nuestros datos
"""

import asyncio
import json
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Set, Tuple

import sys
sys.path.append('/app')

import httpx

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# Número de días hacia atrás para buscar splits
SPLIT_LOOKBACK_DAYS = 30

# Tolerancia para detectar discrepancias VS vs MDD (15%)
MISMATCH_TOLERANCE = 0.15

# Concurrencia para API calls
MAX_CONCURRENT_API = 50


class ReconcileSplitsTask:
    """
    Tarea: Reconciliar datos históricos después de splits
    
    Flujo:
    1. Consultar Polygon API por splits recientes (últimos 30 días)
    2. Para cada ticker con split, verificar si volume_slots tiene datos desajustados
    3. Re-descargar minute aggregates (adjusted=true) de Polygon API
    4. Reconstruir slots de 5 min con lógica PineScript
    5. UPSERT en volume_slots y market_data_daily
    """
    
    name = "reconcile_splits"
    
    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client
    
    async def execute(self, target_date: date) -> Dict:
        """
        Ejecutar reconciliación de splits
        
        Args:
            target_date: Fecha objetivo (normalmente ayer)
        
        Returns:
            Dict con resultado
        """
        logger.info("reconcile_splits_starting", target_date=str(target_date))
        start_time = datetime.now()
        
        try:
            # ── 1. Obtener splits recientes de Polygon ──
            splits = await self._fetch_recent_splits(target_date)
            
            if not splits:
                logger.info("reconcile_splits_no_splits_found")
                return {
                    "success": True,
                    "splits_found": 0,
                    "tickers_fixed": 0,
                    "rows_updated": 0,
                    "message": "No recent splits found"
                }
            
            logger.info(
                "reconcile_splits_found",
                total_splits=len(splits),
                tickers=len(set(s['ticker'] for s in splits))
            )
            
            # ── 2. Identificar tickers que necesitan fix en volume_slots ──
            vs_tickers_to_fix = await self._detect_volume_slots_issues(splits)
            
            # ── 3. Identificar tickers que necesitan fix en market_data_daily ──
            mdd_tickers_to_fix = await self._detect_mdd_issues(splits)
            
            total_to_fix = len(vs_tickers_to_fix) + len(mdd_tickers_to_fix)
            
            if total_to_fix == 0:
                logger.info("reconcile_splits_all_clean")
                return {
                    "success": True,
                    "splits_found": len(splits),
                    "tickers_fixed": 0,
                    "rows_updated": 0,
                    "message": "All data already adjusted"
                }
            
            logger.info(
                "reconcile_splits_issues_detected",
                vs_tickers=len(vs_tickers_to_fix),
                mdd_tickers=len(mdd_tickers_to_fix)
            )
            
            # ── 4. Fix volume_slots ──
            vs_rows = 0
            if vs_tickers_to_fix:
                vs_rows = await self._fix_volume_slots(vs_tickers_to_fix)
            
            # ── 5. Fix market_data_daily ──
            mdd_rows = 0
            if mdd_tickers_to_fix:
                mdd_rows = await self._fix_market_data_daily(mdd_tickers_to_fix)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                "reconcile_splits_completed",
                splits_found=len(splits),
                vs_tickers_fixed=len(vs_tickers_to_fix),
                vs_rows_updated=vs_rows,
                mdd_tickers_fixed=len(mdd_tickers_to_fix),
                mdd_rows_updated=mdd_rows,
                duration_seconds=round(elapsed, 2)
            )
            
            return {
                "success": True,
                "splits_found": len(splits),
                "tickers_fixed": len(vs_tickers_to_fix) + len(mdd_tickers_to_fix),
                "vs_rows_updated": vs_rows,
                "mdd_rows_updated": mdd_rows,
                "duration_seconds": round(elapsed, 2)
            }
            
        except Exception as e:
            logger.error("reconcile_splits_failed", error=str(e), error_type=type(e).__name__)
            return {"success": False, "error": str(e)}
    
    # =========================================================================
    # PASO 1: Obtener splits de Polygon
    # =========================================================================
    
    async def _fetch_recent_splits(self, target_date: date) -> List[Dict]:
        """Obtener splits de los últimos SPLIT_LOOKBACK_DAYS días desde Polygon API"""
        from_date = target_date - timedelta(days=SPLIT_LOOKBACK_DAYS)
        all_splits = []
        next_url = None
        
        base_url = (
            f"https://api.polygon.io/v3/reference/splits"
            f"?execution_date.gte={from_date}"
            f"&execution_date.lte={target_date}"
            f"&limit=1000"
            f"&apiKey={settings.POLYGON_API_KEY}"
        )
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            url = base_url
            while url:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("splits_api_error", status=resp.status_code)
                        break
                    
                    data = resp.json()
                    results = data.get('results', [])
                    all_splits.extend(results)
                    
                    # Pagination
                    next_url = data.get('next_url')
                    if next_url:
                        url = f"{next_url}&apiKey={settings.POLYGON_API_KEY}"
                    else:
                        url = None
                        
                except Exception as e:
                    logger.error("splits_api_exception", error=str(e))
                    break
        
        # Normalizar formato
        normalized = []
        for s in all_splits:
            normalized.append({
                'ticker': s.get('ticker'),
                'execution_date': s.get('execution_date'),
                'split_from': s.get('split_from'),
                'split_to': s.get('split_to'),
            })
        
        return normalized
    
    # =========================================================================
    # PASO 2: Detectar issues en volume_slots
    # =========================================================================
    
    async def _detect_volume_slots_issues(self, splits: List[Dict]) -> Dict[str, List[str]]:
        """
        Detectar tickers con datos desajustados en volume_slots.
        
        Compara volume_slots.avg_price vs market_data_daily.close (fuente de verdad).
        
        Returns:
            Dict[ticker, List[dates_to_fix]]
        """
        tickers_to_fix = {}
        
        for split in splits:
            ticker = split['ticker']
            exec_date_str = split['execution_date']
            sf = split['split_from']
            st = split['split_to']
            
            # Convertir string a date object para asyncpg
            exec_date_obj = date.fromisoformat(exec_date_str)
            
            # Ignorar splits triviales (factor < 10%)
            factor = sf / st
            if abs(factor - 1.0) < 0.1:
                continue
            
            inv_factor = st / sf  # Lo que veríamos si VS no está ajustado vs MDD
            
            # Obtener datos pre-split de ambas tablas
            query_vs = """
                SELECT date::text, AVG(avg_price)::float as avg_p
                FROM volume_slots 
                WHERE symbol=$1 AND date < $2
                GROUP BY date ORDER BY date
            """
            query_mdd = """
                SELECT trading_date::text, close::float
                FROM market_data_daily
                WHERE symbol=$1 AND trading_date < $2
                ORDER BY trading_date
            """
            
            vs_rows = await self.db.fetch(query_vs, ticker, exec_date_obj)
            mdd_rows = await self.db.fetch(query_mdd, ticker, exec_date_obj)
            
            if not vs_rows or not mdd_rows:
                continue
            
            vs_map = {r['date']: r['avg_p'] for r in vs_rows}
            mdd_map = {r['trading_date']: r['close'] for r in mdd_rows}
            
            common_dates = sorted(set(vs_map.keys()) & set(mdd_map.keys()))
            
            bad_dates = []
            for d in common_dates:
                vs_p = vs_map[d]
                mdd_p = mdd_map[d]
                
                if vs_p == 0 or mdd_p == 0:
                    continue
                
                ratio = vs_p / mdd_p
                
                # Para que sea un issue real de split, el ratio debe:
                # 1. Ser cercano al factor inverso del split
                # 2. Ser significativamente diferente de 1.0 (no es variación normal)
                close_to_factor = abs(ratio - inv_factor) / max(abs(inv_factor), 0.01) < 0.25
                far_from_one = abs(ratio - 1.0) > 0.2
                
                if close_to_factor and far_from_one:
                    bad_dates.append(d)
            
            # También buscar post-split mismatches (data loaded between split and reload)
            query_vs_post = """
                SELECT date::text, AVG(avg_price)::float as avg_p
                FROM volume_slots 
                WHERE symbol=$1 AND date >= $2
                GROUP BY date ORDER BY date
            """
            query_mdd_post = """
                SELECT trading_date::text, close::float
                FROM market_data_daily
                WHERE symbol=$1 AND trading_date >= $2
                ORDER BY trading_date
            """
            
            vs_post = await self.db.fetch(query_vs_post, ticker, exec_date_obj)
            mdd_post = await self.db.fetch(query_mdd_post, ticker, exec_date_obj)
            
            if vs_post and mdd_post:
                vs_post_map = {r['date']: r['avg_p'] for r in vs_post}
                mdd_post_map = {r['trading_date']: r['close'] for r in mdd_post}
                
                for d in sorted(set(vs_post_map.keys()) & set(mdd_post_map.keys())):
                    vs_p = vs_post_map[d]
                    mdd_p = mdd_post_map[d]
                    
                    if vs_p == 0 or mdd_p == 0:
                        continue
                    
                    ratio = vs_p / mdd_p
                    # Post-split mismatch: ratio should be ~1.0, flag if > 50% off
                    if abs(ratio - 1.0) > 0.5:
                        bad_dates.append(d)
            
            if bad_dates:
                # Si hay issues, re-descargar TODOS los días del ticker
                # (es más seguro que solo los bad_dates)
                all_dates_query = """
                    SELECT DISTINCT date::text
                    FROM volume_slots WHERE symbol=$1
                    ORDER BY date
                """
                all_rows = await self.db.fetch(all_dates_query, ticker)
                all_dates = [r['date'] for r in all_rows]
                
                tickers_to_fix[ticker] = all_dates
                
                logger.info(
                    "reconcile_split_detected",
                    ticker=ticker,
                    split=f"{sf}:{st}",
                    exec_date=exec_date_str,
                    bad_dates=len(bad_dates),
                    total_dates=len(all_dates)
                )
        
        return tickers_to_fix
    
    # =========================================================================
    # PASO 3: Detectar issues en market_data_daily
    # =========================================================================
    
    async def _detect_mdd_issues(self, splits: List[Dict]) -> Dict[str, str]:
        """
        Detectar tickers con datos desajustados en market_data_daily.
        
        Compara market_data_daily vs Polygon API adjusted=true.
        Solo verifica un par de fechas para ser eficiente.
        
        Returns:
            Dict[ticker, date_range_str] con tickers que necesitan fix
        """
        tickers_to_fix = {}
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for split in splits:
                ticker = split['ticker']
                exec_date_str = split['execution_date']
                sf = split['split_from']
                st = split['split_to']
                
                if abs(sf/st - 1.0) < 0.1:
                    continue
                
                exec_date_obj = date.fromisoformat(exec_date_str)
                
                # Obtener primera fecha pre-split de MDD
                query = """
                    SELECT trading_date::text, close::float
                    FROM market_data_daily
                    WHERE symbol=$1 AND trading_date < $2
                    ORDER BY trading_date
                    LIMIT 1
                """
                rows = await self.db.fetch(query, ticker, exec_date_obj)
                
                if not rows:
                    continue
                
                d = rows[0]['trading_date']
                mdd_close = rows[0]['close']
                
                # Comparar con Polygon API
                url = (
                    f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{d}/{d}"
                    f"?adjusted=true&apiKey={settings.POLYGON_API_KEY}"
                )
                
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    
                    data = resp.json()
                    results = data.get('results', [])
                    if not results:
                        continue
                    
                    api_close = results[0]['c']
                    
                    if api_close == 0:
                        continue
                    
                    ratio = mdd_close / api_close
                    if abs(ratio - 1.0) > 0.02:
                        # MDD no coincide con API → necesita fix
                        tickers_to_fix[ticker] = exec_date_str
                        
                        logger.info(
                            "reconcile_mdd_issue_detected",
                            ticker=ticker,
                            date=d,
                            mdd_close=mdd_close,
                            api_close=api_close,
                            ratio=round(ratio, 4)
                        )
                        
                except Exception as e:
                    logger.debug(f"MDD check failed for {ticker}: {e}")
                    continue
        
        return tickers_to_fix
    
    # =========================================================================
    # PASO 4: Fix volume_slots
    # =========================================================================
    
    async def _fix_volume_slots(self, tickers_to_fix: Dict[str, List[str]]) -> int:
        """
        Re-descargar minute aggregates de Polygon y reconstruir volume_slots.
        
        Usa la misma lógica de conversión a 5-min slots que load_volume_slots.py.
        """
        total_upserted = 0
        
        # Construir lista de trabajo (ticker, date)
        work_items = []
        for ticker, dates in tickers_to_fix.items():
            for d in dates:
                work_items.append((ticker, d))
        
        logger.info(
            "reconcile_fixing_volume_slots",
            tickers=len(tickers_to_fix),
            ticker_date_pairs=len(work_items)
        )
        
        # Procesar en batches con concurrencia limitada
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_API)
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            
            async def process_one(ticker: str, day_str: str) -> List[Tuple]:
                """Fetch minute bars y convertir a slots"""
                async with semaphore:
                    aggs = await self._fetch_minute_aggs(client, ticker, day_str)
                    if not aggs:
                        return []
                    slots = self._convert_to_5min_slots(aggs)
                    day_obj = date.fromisoformat(day_str)
                    return [(day_obj, ticker, s['slot_index'], s['slot_time'],
                             s['volume_accumulated'], s['trades_count'],
                             s['avg_price']) for s in slots]
            
            # Procesar en batches de 500 para evitar acumulación en memoria
            batch_size = 500
            for i in range(0, len(work_items), batch_size):
                batch = work_items[i:i + batch_size]
                
                tasks = [process_one(ticker, d) for ticker, d in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Recoger records válidos
                records = []
                for result in results:
                    if isinstance(result, list):
                        records.extend(result)
                
                # Batch UPSERT
                if records:
                    upserted = await self._upsert_volume_slots(records)
                    total_upserted += upserted
                
                logger.info(
                    "reconcile_vs_batch_progress",
                    processed=min(i + batch_size, len(work_items)),
                    total=len(work_items),
                    rows_so_far=total_upserted
                )
        
        return total_upserted
    
    async def _fetch_minute_aggs(
        self, client: httpx.AsyncClient, ticker: str, day_str: str
    ) -> List[Dict]:
        """Fetch 1-minute aggregates from Polygon API (adjusted=true)"""
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/"
            f"{day_str}/{day_str}"
        )
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, params={
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": 50000,
                    "apiKey": settings.POLYGON_API_KEY
                })
                
                if resp.status_code == 200:
                    return resp.json().get('results', [])
                elif resp.status_code == 429:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    return []
                    
            except Exception:
                if attempt == max_retries - 1:
                    return []
                await asyncio.sleep(0.2)
        
        return []
    
    def _convert_to_5min_slots(self, aggs: List[Dict]) -> List[Dict]:
        """
        Convertir 1-minute aggregates a 5-minute slots con VOLUMEN ACUMULADO.
        
        LÓGICA IDÉNTICA a load_volume_slots.py:
        - Acumula BARRA POR BARRA (PineScript)
        - Mantiene último valor acumulado de cada slot
        - Extended hours: 4:00-20:00 ET (192 slots)
        - avg_price = close (c) del último bar de 1 min en el slot
        """
        from datetime import time
        
        if not aggs:
            return []
        
        accumulated = 0
        slots_dict = {}
        
        for bar in sorted(aggs, key=lambda x: x['t']):
            dt = datetime.fromtimestamp(bar['t'] / 1000, tz=NY_TZ)
            accumulated += bar.get('v', 0)
            
            if dt.hour < 4 or dt.hour >= 20:
                continue
            
            slot_num = ((dt.hour - 4) * 60 + dt.minute) // 5
            slot_h = 4 + (slot_num * 5) // 60
            slot_m = (slot_num * 5) % 60
            
            slots_dict[slot_num] = {
                "slot_index": slot_num,
                "slot_time": time(slot_h, slot_m, 0),
                "volume_accumulated": accumulated,
                "trades_count": bar.get('n', 0),
                "avg_price": bar.get('c', 0.0)
            }
        
        return list(slots_dict.values())
    
    async def _upsert_volume_slots(self, records: List[Tuple]) -> int:
        """Batch UPSERT volume_slots records"""
        if not records:
            return 0
        
        query = """
            INSERT INTO volume_slots 
            (date, symbol, slot_number, slot_time, volume_accumulated, trades_count, avg_price)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (date, symbol, slot_number)
            DO UPDATE SET 
                volume_accumulated = EXCLUDED.volume_accumulated,
                trades_count = EXCLUDED.trades_count,
                avg_price = EXCLUDED.avg_price
        """
        
        try:
            await self.db.executemany(query, records)
            return len(records)
        except Exception as e:
            logger.error("reconcile_vs_upsert_error", error=str(e), batch_size=len(records))
            return 0
    
    # =========================================================================
    # PASO 5: Fix market_data_daily
    # =========================================================================
    
    async def _fix_market_data_daily(self, tickers_to_fix: Dict[str, str]) -> int:
        """
        Re-descargar daily bars de Polygon y actualizar market_data_daily.
        """
        total_upserted = 0
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for ticker, exec_date in tickers_to_fix.items():
                try:
                    # Obtener rango completo de MDD para este ticker
                    range_query = """
                        SELECT MIN(trading_date)::text, MAX(trading_date)::text
                        FROM market_data_daily WHERE symbol=$1
                    """
                    range_rows = await self.db.fetch(range_query, ticker)
                    
                    if not range_rows or not range_rows[0]['min']:
                        continue
                    
                    min_d = range_rows[0]['min']
                    max_d = range_rows[0]['max']
                    
                    # Fetch daily bars from Polygon
                    resp = await client.get(
                        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{min_d}/{max_d}",
                        params={
                            "adjusted": "true",
                            "sort": "asc",
                            "limit": 5000,
                            "apiKey": settings.POLYGON_API_KEY
                        }
                    )
                    
                    if resp.status_code != 200:
                        continue
                    
                    bars = resp.json().get('results', [])
                    if not bars:
                        continue
                    
                    # UPSERT
                    records = []
                    for bar in bars:
                        bar_date = date.fromtimestamp(bar['t'] / 1000)
                        records.append((
                            bar_date, ticker,
                            bar['o'], bar['h'], bar['l'], bar['c'],
                            bar['v'], bar.get('vw'), bar.get('n')
                        ))
                    
                    query = """
                        INSERT INTO market_data_daily 
                        (trading_date, symbol, open, high, low, close, volume, vwap, trades_count)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (trading_date, symbol) 
                        DO UPDATE SET
                            open = EXCLUDED.open, high = EXCLUDED.high,
                            low = EXCLUDED.low, close = EXCLUDED.close,
                            volume = EXCLUDED.volume, vwap = EXCLUDED.vwap,
                            trades_count = EXCLUDED.trades_count
                    """
                    
                    await self.db.executemany(query, records)
                    total_upserted += len(records)
                    
                    logger.info(
                        "reconcile_mdd_fixed",
                        ticker=ticker,
                        rows=len(records)
                    )
                    
                except Exception as e:
                    logger.error("reconcile_mdd_fix_error", ticker=ticker, error=str(e))
        
        return total_upserted
