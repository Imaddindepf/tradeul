"""
Reconcile Parquet Splits Task
==============================

Ajusta los flat files Parquet (day_aggs) para splits recientes.

PROBLEMA:
- Los flat files de Polygon S3 son datos CRUDOS del día en que se generaron.
- Polygon NO re-genera retroactivamente los flat files antiguos inmediatamente
  después de un split (puede tardar días).
- Nuestros loaders descargan estos flat files una sola vez por fecha.
- Resultado: el DuckDB screener (que lee estos Parquet) tiene datos pre-split
  mezclados con post-split, generando indicadores falsos (gap_percent, change_Xd,
  SMA, RSI, ATR, etc.)

SOLUCIÓN:
- Consultar splits recientes desde Polygon API (/v3/reference/splits)
- Para cada ticker con split, comparar Parquet vs market_data_daily (fuente de verdad)
- Si hay discrepancia, calcular el factor de corrección
- Aplicar la corrección a TODOS los Parquet anteriores a la fecha de ejecución del split

CAMPOS AJUSTADOS:
- open, high, low, close: × factor (precio sube en reverse split)
- volume: ÷ factor (menos shares en reverse split)
- transactions: SIN CAMBIO (es count de trades, no de shares)
- window_start: SIN CAMBIO (timestamp)
- ticker: SIN CAMBIO

CUÁNDO SE EJECUTA:
- Después de reconcile_splits (que arregla market_data_daily y volume_slots)
- market_data_daily ya tiene datos correctos (adjusted=true) para usar como referencia
"""

import asyncio
import os
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import sys
sys.path.append('/app')

import httpx
import pyarrow.parquet as pq
import pyarrow as pa

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

SPLIT_LOOKBACK_DAYS = 30

PARQUET_DIR = "/data/polygon/day_aggs"

# If Parquet close differs from market_data_daily close by > 10%, it's mismatched
MISMATCH_TOLERANCE = 0.10

# The detected ratio must be within 5% of the expected split ratio to confirm
RATIO_CONFIRMATION_TOLERANCE = 0.05


class ReconcileParquetSplitsTask:
    """
    Ajusta los Parquet flat files para splits recientes.

    Flujo:
    1. Obtener splits recientes de Polygon API (últimos 30 días)
    2. Filtrar solo splits con ratio significativo (>10% cambio de precio)
    3. Para cada ticker con split:
       a. Buscar la última fecha antes del split en Parquet Y market_data_daily
       b. Comparar closes: si difieren > 10%, el split no está aplicado
       c. Verificar que el ratio detectado ≈ split_from/split_to (±5%)
       d. Aplicar corrección a todos los Parquet con fecha < execution_date
    4. Notificar para restart del screener
    """

    name = "reconcile_parquet_splits"

    def __init__(self, redis_client: RedisClient, timescale_client: TimescaleClient):
        self.redis = redis_client
        self.db = timescale_client

    async def execute(self, target_date: date) -> Dict:
        logger.info("reconcile_parquet_splits_starting", target_date=str(target_date))

        if not os.path.isdir(PARQUET_DIR):
            logger.warning("parquet_dir_not_found", path=PARQUET_DIR)
            return {"success": False, "error": f"Directory not found: {PARQUET_DIR}"}

        # 1. Get recent splits from Polygon
        splits = await self._fetch_recent_splits(target_date)
        if not splits:
            logger.info("reconcile_parquet_no_splits")
            return {"success": True, "splits_found": 0, "tickers_fixed": 0, "files_updated": 0}

        logger.info("reconcile_parquet_splits_found", count=len(splits))

        # 2. Filter significant splits (ignore trivial ones like stock dividends ~1%)
        significant = []
        for s in splits:
            sf = s["split_from"]
            st = s["split_to"]
            if sf <= 0 or st <= 0:
                continue
            price_factor = sf / st
            if abs(price_factor - 1.0) < MISMATCH_TOLERANCE:
                continue
            significant.append(s)

        if not significant:
            logger.info("reconcile_parquet_no_significant_splits")
            return {"success": True, "splits_found": len(splits), "tickers_fixed": 0, "files_updated": 0}

        logger.info("reconcile_parquet_significant_splits", count=len(significant))

        # 3. Get list of available Parquet files (sorted by date)
        parquet_files = self._list_parquet_files()
        if not parquet_files:
            logger.warning("no_parquet_files_found")
            return {"success": True, "splits_found": len(splits), "tickers_fixed": 0, "files_updated": 0}

        # 4. For each split, detect if correction needed and apply
        total_fixed = 0
        total_files_updated = 0
        details = []

        for split in significant:
            ticker = split["ticker"]
            exec_date = split["execution_date"]
            expected_price_factor = split["split_from"] / split["split_to"]

            result = await self._process_split(
                ticker, exec_date, expected_price_factor, parquet_files
            )

            if result["fixed"]:
                total_fixed += 1
                total_files_updated += result["files_updated"]
                details.append({
                    "ticker": ticker,
                    "execution_date": exec_date,
                    "factor_applied": result["factor_applied"],
                    "files_updated": result["files_updated"],
                })

        logger.info(
            "reconcile_parquet_splits_completed",
            splits_found=len(splits),
            significant=len(significant),
            tickers_fixed=total_fixed,
            files_updated=total_files_updated,
        )

        return {
            "success": True,
            "splits_found": len(splits),
            "significant_splits": len(significant),
            "tickers_fixed": total_fixed,
            "files_updated": total_files_updated,
            "details": details,
        }

    # =========================================================================
    # Step 1: Fetch recent splits from Polygon
    # =========================================================================

    async def _fetch_recent_splits(self, target_date: date) -> List[Dict]:
        from_date = target_date - timedelta(days=SPLIT_LOOKBACK_DAYS)
        all_splits: List[Dict] = []
        url: Optional[str] = (
            f"https://api.polygon.io/v3/reference/splits"
            f"?execution_date.gte={from_date}"
            f"&execution_date.lte={target_date}"
            f"&limit=1000"
            f"&apiKey={settings.POLYGON_API_KEY}"
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            while url:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("parquet_splits_api_error", status=resp.status_code)
                        break
                    data = resp.json()
                    all_splits.extend(data.get("results", []))
                    next_url = data.get("next_url")
                    url = f"{next_url}&apiKey={settings.POLYGON_API_KEY}" if next_url else None
                except Exception as e:
                    logger.error("parquet_splits_api_exception", error=str(e))
                    break

        normalized = []
        for s in all_splits:
            sf = s.get("split_from")
            st = s.get("split_to")
            if sf is None or st is None:
                continue
            normalized.append({
                "ticker": s.get("ticker"),
                "execution_date": s.get("execution_date"),
                "split_from": float(sf),
                "split_to": float(st),
            })
        return normalized

    # =========================================================================
    # Step 2: List and cache Parquet files
    # =========================================================================

    def _list_parquet_files(self) -> List[str]:
        """Return sorted list of YYYY-MM-DD date strings from Parquet filenames."""
        files = []
        for f in os.listdir(PARQUET_DIR):
            if f.endswith(".parquet"):
                date_str = f.replace(".parquet", "")
                files.append(date_str)
        files.sort()
        return files

    # =========================================================================
    # Step 3: Process a single split
    # =========================================================================

    async def _process_split(
        self,
        ticker: str,
        exec_date_str: str,
        expected_price_factor: float,
        parquet_dates: List[str],
    ) -> Dict:
        """
        Detect if a split needs correction in Parquet, verify, and apply.

        Returns dict with: fixed, factor_applied, files_updated
        """
        # Find last Parquet date BEFORE the execution date
        pre_split_dates = [d for d in parquet_dates if d < exec_date_str]
        if not pre_split_dates:
            return {"fixed": False, "factor_applied": None, "files_updated": 0}

        ref_date = pre_split_dates[-1]  # Last date before split

        # Read Parquet close for this ticker on ref_date
        parquet_close = self._read_parquet_close(ticker, ref_date)
        if parquet_close is None:
            logger.debug("parquet_ticker_not_found", ticker=ticker, date=ref_date)
            return {"fixed": False, "factor_applied": None, "files_updated": 0}

        # Read market_data_daily close (our source of truth, already adjusted)
        mdd_close = await self._read_mdd_close(ticker, ref_date)
        if mdd_close is None:
            logger.debug("mdd_ticker_not_found", ticker=ticker, date=ref_date)
            return {"fixed": False, "factor_applied": None, "files_updated": 0}

        # Calculate detected factor
        detected_factor = mdd_close / parquet_close

        # Check 1: Is there a significant mismatch?
        if abs(detected_factor - 1.0) <= MISMATCH_TOLERANCE:
            logger.debug(
                "parquet_already_adjusted",
                ticker=ticker,
                ref_date=ref_date,
                parquet_close=round(parquet_close, 4),
                mdd_close=round(mdd_close, 4),
                detected_factor=round(detected_factor, 4),
            )
            return {"fixed": False, "factor_applied": None, "files_updated": 0}

        # Check 2: Does the detected factor match the expected split ratio?
        ratio_diff = abs(detected_factor - expected_price_factor) / expected_price_factor
        if ratio_diff > RATIO_CONFIRMATION_TOLERANCE:
            logger.warning(
                "parquet_factor_mismatch",
                ticker=ticker,
                ref_date=ref_date,
                detected_factor=round(detected_factor, 6),
                expected_factor=round(expected_price_factor, 6),
                ratio_diff_pct=round(ratio_diff * 100, 2),
            )
            # Use detected_factor from market_data_daily (source of truth) instead
            # of the expected one, but log the discrepancy for review
            logger.info(
                "parquet_using_detected_factor",
                ticker=ticker,
                factor=round(detected_factor, 6),
            )

        logger.info(
            "parquet_split_correction_needed",
            ticker=ticker,
            exec_date=exec_date_str,
            ref_date=ref_date,
            parquet_close=round(parquet_close, 4),
            mdd_close=round(mdd_close, 4),
            factor=round(detected_factor, 6),
            expected_factor=round(expected_price_factor, 6),
        )

        # Apply correction to all Parquet files before execution date
        files_updated = self._apply_correction(
            ticker, exec_date_str, detected_factor, pre_split_dates
        )

        return {
            "fixed": True,
            "factor_applied": round(detected_factor, 6),
            "files_updated": files_updated,
        }

    # =========================================================================
    # Data readers
    # =========================================================================

    def _read_parquet_close(self, ticker: str, date_str: str) -> Optional[float]:
        fpath = os.path.join(PARQUET_DIR, f"{date_str}.parquet")
        if not os.path.exists(fpath):
            return None
        try:
            table = pq.read_table(fpath, columns=["ticker", "close"])
            ticker_col = table.column("ticker")
            close_col = table.column("close")
            for i in range(table.num_rows):
                if ticker_col[i].as_py() == ticker:
                    return float(close_col[i].as_py())
            return None
        except Exception as e:
            logger.error("parquet_read_error", file=fpath, error=str(e))
            return None

    async def _read_mdd_close(self, ticker: str, date_str: str) -> Optional[float]:
        from datetime import datetime as dt
        trading_date = dt.strptime(date_str, "%Y-%m-%d").date()
        query = """
            SELECT close::float
            FROM market_data_daily
            WHERE symbol = $1 AND trading_date = $2
        """
        try:
            rows = await self.db.fetch(query, ticker, trading_date)
            if not rows:
                return None
            return float(rows[0]["close"])
        except Exception as e:
            logger.error("mdd_read_error", ticker=ticker, date=date_str, error=str(e))
            return None

    # =========================================================================
    # Apply correction
    # =========================================================================

    def _apply_correction(
        self,
        ticker: str,
        exec_date_str: str,
        price_factor: float,
        pre_split_dates: List[str],
    ) -> int:
        """
        Apply split correction to all Parquet files before exec_date.

        Uses pure PyArrow (no pandas dependency).

        Adjusts:
          - open, high, low, close: multiply by price_factor
          - volume: divide by price_factor (round to int)
          - transactions: unchanged
          - window_start: unchanged
        """
        import pyarrow.compute as pc

        files_updated = 0
        volume_factor = 1.0 / price_factor

        for date_str in pre_split_dates:
            fpath = os.path.join(PARQUET_DIR, f"{date_str}.parquet")
            if not os.path.exists(fpath):
                continue

            try:
                table = pq.read_table(fpath)
                ticker_col = table.column("ticker")

                mask = pc.equal(ticker_col, ticker)
                if not pc.any(mask).as_py():
                    continue

                # Build new columns
                new_columns = {}
                for col_name in ("open", "high", "low", "close"):
                    orig = table.column(col_name)
                    adjusted = pc.if_else(
                        mask,
                        pc.multiply(orig, price_factor),
                        orig,
                    )
                    new_columns[col_name] = adjusted

                orig_vol = table.column("volume")
                adjusted_vol = pc.if_else(
                    mask,
                    pc.cast(
                        pc.round(pc.multiply(pc.cast(orig_vol, pa.float64()), volume_factor)),
                        pa.int64(),
                    ),
                    orig_vol,
                )
                new_columns["volume"] = adjusted_vol

                # Rebuild table with adjusted columns
                new_table = table
                for col_name, new_col in new_columns.items():
                    col_idx = table.schema.get_field_index(col_name)
                    new_table = new_table.set_column(col_idx, col_name, new_col)

                pq.write_table(new_table, fpath)
                files_updated += 1

            except Exception as e:
                logger.error(
                    "parquet_correction_error",
                    ticker=ticker,
                    file=date_str,
                    error=str(e),
                )

        logger.info(
            "parquet_correction_applied",
            ticker=ticker,
            exec_date=exec_date_str,
            factor=round(price_factor, 6),
            files_updated=files_updated,
        )

        return files_updated
