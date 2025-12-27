"""
Pattern Matching Index Updater
==============================

Actualización incremental del índice FAISS de pattern matching.
Se ejecuta después del cierre del mercado (8:00 PM ET).

Proceso:
1. Descarga flat files nuevos de Polygon
2. Extrae patrones del día
3. Añade al índice FAISS existente
4. Actualiza metadata SQLite
5. Actualiza trayectorias en .npy
"""

import os
import gzip
import csv
import sqlite3
import asyncio
import httpx
from datetime import datetime, date, timedelta
from typing import List, Dict, Tuple, Optional
from zoneinfo import ZoneInfo

import numpy as np

import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")


class PatternMatchingUpdater:
    """
    Actualiza incrementalmente el índice de pattern matching
    llamando al servicio pattern_matching via HTTP.
    """
    
    def __init__(self, pattern_service_url: str = "http://pattern_matching:8000"):
        self.pattern_service_url = pattern_service_url
        self.update_hour = 20  # 8:00 PM ET
        self.update_minute = 0
        self.last_update_date: Optional[date] = None
        self.is_running = False
    
    async def _is_trading_day(self, check_date: date, redis_client=None) -> bool:
        """Verificar si es día de trading"""
        # Fin de semana
        if check_date.weekday() >= 5:
            return False
        
        # TODO: Verificar holidays via Redis si disponible
        return True
    
    async def check_pattern_service_health(self) -> bool:
        """Verificar que el servicio de pattern matching esté disponible"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.pattern_service_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("status") == "healthy"
        except Exception as e:
            logger.error("pattern_service_health_check_failed", error=str(e))
        return False
    
    async def get_missing_dates(self) -> List[str]:
        """Obtener fechas que faltan por indexar"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Obtener fechas disponibles en flat files
                response = await client.get(f"{self.pattern_service_url}/api/available-dates")
                if response.status_code != 200:
                    logger.error("failed_to_get_available_dates", status=response.status_code)
                    return []
                
                available_data = response.json()
                available_dates = set(available_data.get("dates", []))
                
                # Obtener fechas ya indexadas
                response = await client.get(f"{self.pattern_service_url}/api/index/stats")
                if response.status_code != 200:
                    logger.error("failed_to_get_index_stats", status=response.status_code)
                    return []
                
                # Las fechas indexadas están en la metadata SQLite
                # Por ahora, asumimos que el servicio tiene un endpoint para esto
                # Si no existe, lo creamos
                
                return list(available_dates)[-5:]  # Últimos 5 días por defecto
                
        except Exception as e:
            logger.error("get_missing_dates_failed", error=str(e))
            return []
    
    async def trigger_update(self, target_date: Optional[str] = None) -> Dict:
        """
        Trigger actualización via API del servicio pattern_matching
        
        Args:
            target_date: Fecha específica o None para últimos días
        """
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:  # 10 min timeout
                payload = {}
                if target_date:
                    payload["date"] = target_date
                
                logger.info(
                    "triggering_pattern_update",
                    target_date=target_date or "auto",
                    service_url=self.pattern_service_url
                )
                
                response = await client.post(
                    f"{self.pattern_service_url}/api/data/update-daily",
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        "pattern_update_completed",
                        patterns_added=result.get("patterns_added", 0),
                        dates_processed=result.get("processed_dates", [])
                    )
                    return result
                else:
                    logger.error(
                        "pattern_update_failed",
                        status=response.status_code,
                        response=response.text[:500]
                    )
                    return {"success": False, "error": response.text}
                    
        except httpx.TimeoutException:
            logger.error("pattern_update_timeout")
            return {"success": False, "error": "Timeout (10 min)"}
        except Exception as e:
            logger.error("pattern_update_exception", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def run_scheduled_update(self):
        """Ejecutar actualización programada"""
        now_et = datetime.now(NY_TZ)
        target_date = now_et.date()
        
        # Verificar si es día de trading
        if not await self._is_trading_day(target_date):
            logger.info(
                "skipping_pattern_update_not_trading_day",
                date=str(target_date)
            )
            return {"success": True, "skipped": True, "reason": "not_trading_day"}
        
        logger.info(
            "starting_scheduled_pattern_update",
            date=str(target_date)
        )
        
        # Verificar servicio disponible
        if not await self.check_pattern_service_health():
            logger.error("pattern_service_not_available")
            return {"success": False, "error": "pattern_service_not_available"}
        
        # Trigger actualización
        result = await self.trigger_update(target_date.isoformat())
        
        if result.get("success", False) or result.get("patterns_added", 0) > 0:
            self.last_update_date = target_date
        
        return result
    
    async def run(self, redis_client=None):
        """Loop principal del scheduler de pattern matching"""
        self.is_running = True
        logger.info(
            "pattern_matching_updater_started",
            schedule="8:00 PM ET daily (after market close)"
        )
        
        while self.is_running:
            try:
                now_et = datetime.now(NY_TZ)
                current_date = now_et.date()
                current_hour = now_et.hour
                current_minute = now_et.minute
                
                # Verificar si es hora de actualizar (8:00-8:05 PM ET)
                is_update_time = (
                    current_hour == self.update_hour and
                    self.update_minute <= current_minute <= self.update_minute + 5
                )
                
                if is_update_time and self.last_update_date != current_date:
                    if await self._is_trading_day(current_date, redis_client):
                        logger.info(
                            "pattern_update_time_reached",
                            current_time=now_et.strftime("%H:%M:%S %Z")
                        )
                        await self.run_scheduled_update()
                    else:
                        self.last_update_date = current_date
                        logger.info(
                            "skipping_pattern_update_not_trading_day",
                            date=str(current_date)
                        )
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                logger.info("pattern_matching_updater_cancelled")
                raise
            except Exception as e:
                logger.error(
                    "pattern_updater_loop_error",
                    error=str(e)
                )
                await asyncio.sleep(60)
    
    def stop(self):
        """Detener el updater"""
        self.is_running = False
        logger.info("pattern_matching_updater_stopped")

