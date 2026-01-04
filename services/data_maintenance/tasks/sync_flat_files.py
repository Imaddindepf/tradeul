"""
Flat Files Synchronization
==========================

Sincronización centralizada de flat files de Polygon.

ARQUITECTURA:
- Este módulo es llamado por FlatFilesWatcher (después del cierre del mercado)
- USA la lógica de holidays de DailyMaintenanceScheduler (sin duplicar)
- NO limpia caches, NO afecta otros servicios

FLUJO:
1. FlatFilesWatcher detecta que hay nuevo día de trading pendiente
2. Verifica si Polygon S3 ya tiene los flat files
3. Para servicios LOCALES (Screener): Descarga day_aggs via Polygon-Data
4. Para Pattern Matching (REMOTO): Llama a /api/data/update-daily
   (PM descarga internamente sus propios minute_aggs)
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Optional, Dict, TYPE_CHECKING
from zoneinfo import ZoneInfo

import httpx
import boto3
from botocore.config import Config

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from daily_maintenance_scheduler import DailyMaintenanceScheduler

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")


class SyncFlatFilesTask:
    """
    Sincroniza flat files de Polygon sin afectar otros datos.
    
    IMPORTANTE:
    - NO tiene lógica de holidays propia (usa DailyMaintenanceScheduler)
    - NO limpia caches
    - Solo descarga archivos y actualiza Pattern Matching
    """
    
    def __init__(self):
        # URLs de servicios
        self.polygon_data_url = "http://tradeul_polygon_data:8000"
        self.pattern_matching_url = "http://37.27.183.194:8025"
        
        # Polygon S3 credentials
        import os
        self.s3_access_key = os.getenv("POLYGON_S3_ACCESS_KEY", "")
        self.s3_secret_key = os.getenv("POLYGON_S3_SECRET_KEY", "")
        self.s3_endpoint = "https://files.polygon.io"
        self.s3_bucket = "flatfiles"
        
        self._s3_client = None
    
    @property
    def s3(self):
        """Lazy initialization of S3 client"""
        if self._s3_client is None and self.s3_access_key:
            session = boto3.Session(
                aws_access_key_id=self.s3_access_key,
                aws_secret_access_key=self.s3_secret_key,
            )
            self._s3_client = session.client(
                's3',
                endpoint_url=self.s3_endpoint,
                config=Config(signature_version='s3v4'),
            )
        return self._s3_client
    
    def _get_s3_key(self, target_date: date, data_type: str) -> str:
        """Generar S3 key para una fecha"""
        year = target_date.strftime("%Y")
        month = target_date.strftime("%m")
        date_str = target_date.isoformat()
        
        if data_type == "minute_aggs":
            return f"us_stocks_sip/minute_aggs_v1/{year}/{month}/{date_str}.csv.gz"
        else:
            return f"us_stocks_sip/day_aggs_v1/{year}/{month}/{date_str}.csv.gz"
    
    async def check_file_exists_in_polygon(self, target_date: date, data_type: str = "minute_aggs") -> bool:
        """Verificar si un flat file existe en Polygon S3"""
        if not self.s3:
            logger.warning("s3_client_not_initialized")
            return False
        
        s3_key = self._get_s3_key(target_date, data_type)
        
        try:
            self.s3.head_object(Bucket=self.s3_bucket, Key=s3_key)
            return True
        except self.s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    async def download_day_aggs_for_screener(self, target_date: date) -> Dict:
        """
        Descargar day_aggs via Polygon-Data para servicios locales (Screener).
        
        NOTA: Solo day_aggs porque Screener no usa minute_aggs.
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    f"{self.polygon_data_url}/download",
                    json={
                        "start_date": target_date.isoformat(),
                        "end_date": target_date.isoformat(),
                        "data_types": ["day_aggs"],  # Solo day_aggs para Screener
                        "force": False
                    }
                )
                result = response.json()
                logger.info(
                    "day_aggs_download_queued",
                    date=target_date.isoformat(),
                    result=result
                )
                return {"success": True, "result": result}
                
            except Exception as e:
                logger.error("day_aggs_download_failed", date=target_date.isoformat(), error=str(e))
                return {"success": False, "error": str(e)}
    
    async def update_pattern_matching(self, target_date: date) -> Dict:
        """
        Actualizar Pattern Matching (servidor remoto).
        
        IMPORTANTE: Pattern Matching descarga internamente sus propios minute_aggs.
        Este método solo llama a su API /api/data/update-daily.
        """
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                response = await client.post(
                    f"{self.pattern_matching_url}/api/data/update-daily",
                    json={"date": target_date.isoformat()}
                )
                result = response.json()
                
                logger.info(
                    "pattern_matching_update_completed",
                    date=target_date.isoformat(),
                    patterns_added=result.get("patterns_added", 0)
                )
                return {"success": result.get("success", False), "result": result}
                
            except httpx.TimeoutException:
                logger.error("pattern_matching_timeout")
                return {"success": False, "error": "Timeout (10 min)"}
            except Exception as e:
                logger.error("pattern_matching_update_failed", error=str(e))
                return {"success": False, "error": str(e)}
    
    async def get_pattern_matching_status(self) -> Dict:
        """Obtener estado actual del Pattern Matching"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{self.pattern_matching_url}/api/data/stats")
                stats = response.json()
                
                response2 = await client.get(
                    f"{self.pattern_matching_url}/api/available-dates",
                    params={"limit": 5}
                )
                dates = response2.json()
                
                return {
                    "success": True,
                    "newest_flat_file": dates.get("last"),
                    "total_files": stats.get("files_count"),
                    "last_5_dates": dates.get("dates", [])
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    async def sync_for_date(self, target_date: date) -> Dict:
        """
        Sincronizar flat files para una fecha específica.
        
        Proceso:
        1. Verificar si minute_aggs existe en Polygon S3 (es el último en liberarse)
        2. Descargar day_aggs para servicios locales (Screener)
        3. Actualizar Pattern Matching (descarga + actualiza índice internamente)
        """
        logger.info("🔄 sync_starting", target_date=target_date.isoformat())
        
        result = {
            "target_date": target_date.isoformat(),
            "started_at": datetime.now(NY_TZ).isoformat(),
            "minute_aggs_available": False,
            "day_aggs_downloaded": False,
            "pattern_matching_updated": False,
            "success": False
        }
        
        # 1. Verificar disponibilidad en Polygon S3
        minute_exists = await self.check_file_exists_in_polygon(target_date, "minute_aggs")
        day_exists = await self.check_file_exists_in_polygon(target_date, "day_aggs")
        
        result["minute_aggs_available"] = minute_exists
        result["day_aggs_available"] = day_exists
        
        if not minute_exists:
            logger.info("⏳ minute_aggs_not_available_yet", date=target_date.isoformat())
            result["message"] = "minute_aggs not available in Polygon yet"
            return result
        
        # 2. Descargar day_aggs para servicios locales
        if day_exists:
            download_result = await self.download_day_aggs_for_screener(target_date)
            result["day_aggs_downloaded"] = download_result.get("success", False)
        
        # 3. Actualizar Pattern Matching
        pm_result = await self.update_pattern_matching(target_date)
        result["pattern_matching_updated"] = pm_result.get("success", False)
        result["pattern_matching_result"] = pm_result.get("result")
        
        result["success"] = result["pattern_matching_updated"]
        result["completed_at"] = datetime.now(NY_TZ).isoformat()
        
        if result["success"]:
            logger.info("✅ sync_completed", target_date=target_date.isoformat())
        else:
            logger.warning("⚠️ sync_partial", result=result)
        
        return result


class FlatFilesWatcher:
    """
    Monitor que sincroniza flat files después del cierre del mercado.
    
    ARQUITECTURA:
    - USA DailyMaintenanceScheduler para lógica de holidays (sin duplicar)
    - Verifica Polygon S3 cada 30 minutos (5 PM - 9 AM ET)
    - Sincroniza cuando detecta flat files disponibles
    
    IMPORTANTE: No tiene lista de holidays propia.
    """
    
    def __init__(self, redis_client, daily_scheduler: "DailyMaintenanceScheduler"):
        self.redis = redis_client
        self.daily_scheduler = daily_scheduler  # Fuente de verdad para holidays
        self.sync_task = SyncFlatFilesTask()
        self.is_running = False
        self._check_interval = 1800  # 30 minutos
    
    async def _is_already_synced(self, target_date: date) -> bool:
        """Verificar si ya sincronizamos esta fecha"""
        key = f"flat_files:synced:{target_date.isoformat()}"
        value = await self.redis.get(key)
        return value is not None
    
    async def _mark_as_synced(self, target_date: date):
        """Marcar fecha como sincronizada"""
        key = f"flat_files:synced:{target_date.isoformat()}"
        await self.redis.set(key, "1", ttl=86400 * 7)  # 7 días
    
    async def check_and_sync(self) -> Optional[Dict]:
        """
        Verificar y sincronizar si hay flat files pendientes.
        
        USA daily_scheduler._get_last_trading_day_async() para determinar
        el último día de trading (respetando holidays).
        """
        now_et = datetime.now(NY_TZ)
        today = now_et.date()
        
        # Obtener último día de trading USANDO DailyMaintenanceScheduler
        last_trading = await self.daily_scheduler._get_last_trading_day_async(today)
        
        # ¿Ya sincronizamos?
        if await self._is_already_synced(last_trading):
            logger.debug("flat_files_already_synced", date=last_trading.isoformat())
            return None
        
        # Intentar sincronizar
        result = await self.sync_task.sync_for_date(last_trading)
        
        if result.get("success"):
            await self._mark_as_synced(last_trading)
        
        return result
    
    async def run(self):
        """
        Loop principal del watcher.
        
        Solo verifica después del cierre del mercado (5 PM - 9 AM ET).
        """
        self.is_running = True
        logger.info("🔍 FlatFilesWatcher started")
        
        while self.is_running:
            try:
                now_et = datetime.now(NY_TZ)
                hour = now_et.hour
                
                # Solo verificar entre 5 PM y 9 AM ET (después del cierre)
                should_check = hour >= 17 or hour < 9
                
                if should_check:
                    result = await self.check_and_sync()
                    if result and result.get("success"):
                        logger.info("✅ Flat files synced", result=result)
                else:
                    logger.debug("Skipping check during market hours", hour=hour)
                
                await asyncio.sleep(self._check_interval)
                
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("flat_files_watcher_error", error=str(e))
                await asyncio.sleep(60)
        
        logger.info("🔍 FlatFilesWatcher stopped")
    
    def stop(self):
        """Detener el watcher"""
        self.is_running = False
