"""
Export Screener Metadata Task
=============================

Exporta metadata de tickers a Parquet para el Screener service.
Parquet es más eficiente: compresión columnar, tipos preservados, lectura rápida.

Campos exportados:
- symbol, market_cap, free_float, free_float_percent, sector, industry
"""

from datetime import date
from pathlib import Path
from typing import Dict

import pyarrow as pa
import pyarrow.parquet as pq

import sys
sys.path.append('/app')

from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Ruta donde el screener espera el archivo
METADATA_PATH = Path("/data/polygon/screener_metadata.parquet")


class ExportScreenerMetadataTask:
    """Exporta metadata de tickers a Parquet para el Screener"""
    
    def __init__(self, redis: RedisClient, db: TimescaleClient):
        self.redis = redis
        self.db = db
    
    async def execute(self, target_date: date) -> Dict:
        """
        Exportar metadata a Parquet.
        Sobrescribe el archivo anterior.
        """
        try:
            # Query metadata desde tickers_unified
            query = """
                SELECT 
                    symbol,
                    market_cap,
                    free_float,
                    free_float_percent,
                    shares_outstanding,
                    sector,
                    industry
                FROM tickers_unified
                WHERE is_actively_trading = true
                  AND market_cap IS NOT NULL
            """
            
            rows = await self.db.fetch(query)
            
            if not rows:
                return {
                    "success": False,
                    "error": "No metadata found in tickers_unified"
                }
            
            # Crear tabla PyArrow con tipos explícitos
            table = pa.table({
                "symbol": pa.array([r["symbol"] for r in rows], type=pa.string()),
                "market_cap": pa.array([r["market_cap"] for r in rows], type=pa.int64()),
                "free_float": pa.array([r["free_float"] for r in rows], type=pa.int64()),
                "free_float_percent": pa.array([float(r["free_float_percent"]) if r["free_float_percent"] else None for r in rows], type=pa.float64()),
                "shares_outstanding": pa.array([r["shares_outstanding"] for r in rows], type=pa.int64()),
                "sector": pa.array([r["sector"] or "" for r in rows], type=pa.string()),
                "industry": pa.array([r["industry"] or "" for r in rows], type=pa.string()),
            })
            
            # Asegurar que el directorio existe
            METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            # Escribir Parquet con compresión snappy (rápida)
            pq.write_table(table, METADATA_PATH, compression='snappy')
            
            file_size = METADATA_PATH.stat().st_size
            
            logger.info(
                "screener_metadata_exported",
                rows=len(rows),
                file_size_kb=round(file_size / 1024, 1),
                format="parquet",
                compression="snappy",
                path=str(METADATA_PATH)
            )
            
            return {
                "success": True,
                "rows_exported": len(rows),
                "file_size_kb": round(file_size / 1024, 1),
                "format": "parquet",
                "path": str(METADATA_PATH)
            }
            
        except Exception as e:
            logger.error("export_screener_metadata_failed", error=str(e))
            return {"success": False, "error": str(e)}

