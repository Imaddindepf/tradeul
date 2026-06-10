"""
Flat Files Synchronization
==========================

Sincronización centralizada de flat files de Polygon.

ARQUITECTURA:
- Este módulo es llamado por FlatFilesWatcher (después del cierre del mercado)
- USA la lógica de holidays de DailyMaintenanceScheduler (sin duplicar)
- NO limpia caches, NO afecta otros servicios

FLUJO:
1. FlatFilesWatcher detecta TODOS los días de trading sin sincronizar (no solo el último)
2. Verifica si Polygon S3 ya tiene los flat files
3. Para servicios LOCALES (Screener): Descarga day_aggs + minute_aggs via Polygon-Data
4. Para Pattern Matching (REMOTO): Llama a /api/data/update-daily
   (PM descarga internamente sus propios minute_aggs)

OBSERVABILIDAD:
- Redis keys publicadas:
  · flat_files:synced:{YYYY-MM-DD}            → "1" si ese día ya está OK
  · flat_files:last_synced_date               → última fecha sincronizada con éxito
  · flat_files:last_synced_at                 → timestamp ISO del último éxito
  · flat_files:last_check_at                  → timestamp ISO del último intento
  · flat_files:last_error                     → mensaje de error si último intento falló
  · flat_files:credentials_ok                 → "1"/"0" según validación al arranque
- Logs estructurados con event=... para Datadog/log aggregation
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, TYPE_CHECKING
from zoneinfo import ZoneInfo

import httpx
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError

import os
import sys
sys.path.append('/app')

from shared.utils.logger import get_logger

if TYPE_CHECKING:
    from daily_maintenance_scheduler import DailyMaintenanceScheduler

logger = get_logger(__name__)

NY_TZ = ZoneInfo("America/New_York")

# Cap de días que el watcher intentará re-sincronizar en una sola pasada
# (protege contra re-descargas masivas si el sistema lleva semanas caído).
MAX_BACKFILL_DAYS = 14

# Si la última sincronización exitosa lleva más de este umbral en horario
# post-market, se publica un log ERROR (consumible por alertas externas).
STALE_THRESHOLD_HOURS = 18


class SyncFlatFilesTask:
    """
    Sincroniza flat files de Polygon sin afectar otros datos.
    
    IMPORTANTE:
    - NO tiene lógica de holidays propia (usa DailyMaintenanceScheduler)
    - NO limpia caches
    - Solo descarga archivos y actualiza Pattern Matching
    """

    def __init__(self):
        self.polygon_data_url = "http://tradeul_polygon_data:8000"
        self.pattern_matching_url = "http://37.27.183.194:8025"

        self.s3_access_key = os.getenv("POLYGON_S3_ACCESS_KEY", "")
        self.s3_secret_key = os.getenv("POLYGON_S3_SECRET_KEY", "")
        self.s3_endpoint = "https://files.polygon.io"
        self.s3_bucket = "flatfiles"

        self._s3_client = None

    @property
    def has_credentials(self) -> bool:
        return bool(self.s3_access_key and self.s3_secret_key)

    @property
    def s3(self):
        if self._s3_client is None and self.has_credentials:
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

    def validate_credentials(self) -> Dict:
        """
        Smoke test al arranque: lista 1 objeto del bucket para verificar que
        las credenciales son válidas. No descarga nada.
        """
        if not self.has_credentials:
            return {
                "ok": False,
                "reason": "missing_credentials",
                "message": (
                    "POLYGON_S3_ACCESS_KEY / POLYGON_S3_SECRET_KEY no están "
                    "definidas en el entorno del contenedor."
                ),
            }
        try:
            resp = self.s3.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix="us_stocks_sip/day_aggs_v1/",
                MaxKeys=1,
            )
            if resp.get("KeyCount", 0) >= 1:
                return {"ok": True, "reason": "validated"}
            return {
                "ok": False,
                "reason": "empty_listing",
                "message": "Listado vacío; ¿bucket o prefijo incorrectos?",
            }
        except ClientError as e:
            return {
                "ok": False,
                "reason": "client_error",
                "message": f"{e.response.get('Error', {}).get('Code')}: {e}",
            }
        except EndpointConnectionError as e:
            return {"ok": False, "reason": "network_error", "message": str(e)}
        except Exception as e:
            return {"ok": False, "reason": "unknown", "message": str(e)}

    def _get_s3_key(self, target_date: date, data_type: str) -> str:
        year = target_date.strftime("%Y")
        month = target_date.strftime("%m")
        date_str = target_date.isoformat()
        if data_type == "minute_aggs":
            return f"us_stocks_sip/minute_aggs_v1/{year}/{month}/{date_str}.csv.gz"
        return f"us_stocks_sip/day_aggs_v1/{year}/{month}/{date_str}.csv.gz"

    async def check_file_exists_in_polygon(
        self,
        target_date: date,
        data_type: str = "minute_aggs",
    ) -> bool:
        if not self.s3:
            logger.warning(
                "s3_client_not_initialized",
                hint="POLYGON_S3_ACCESS_KEY / POLYGON_S3_SECRET_KEY missing",
            )
            return False

        s3_key = self._get_s3_key(target_date, data_type)
        try:
            self.s3.head_object(Bucket=self.s3_bucket, Key=s3_key)
            return True
        except self.s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] in ('404', 'NoSuchKey'):
                return False
            logger.warning(
                "s3_head_object_error",
                key=s3_key,
                code=e.response.get('Error', {}).get('Code'),
                error=str(e),
            )
            raise

    async def download_flat_files_for_local_services(self, target_date: date) -> Dict:
        """
        Descargar flat files via Polygon-Data para servicios locales.
        
        Servicios que usan estos datos:
        - Screener: day_aggs (precios diarios)
        - AI Agent / MCP: minute_aggs (análisis histórico)
        - Backtester (deriva minute_aggs_adjusted)
        """
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                response = await client.post(
                    f"{self.polygon_data_url}/download",
                    json={
                        "start_date": target_date.isoformat(),
                        "end_date": target_date.isoformat(),
                        "data_types": ["day_aggs", "minute_aggs"],
                        "force": False,
                    },
                )
                result = response.json()
                logger.info(
                    "flat_files_download_queued",
                    date=target_date.isoformat(),
                    result=result,
                )
                return {"success": True, "result": result}
            except Exception as e:
                logger.error(
                    "flat_files_download_failed",
                    date=target_date.isoformat(),
                    error=str(e),
                )
                return {"success": False, "error": str(e)}

    async def update_pattern_matching(self, target_date: date) -> Dict:
        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                response = await client.post(
                    f"{self.pattern_matching_url}/api/data/update-daily",
                    json={"date": target_date.isoformat()},
                )
                result = response.json()
                logger.info(
                    "pattern_matching_update_completed",
                    date=target_date.isoformat(),
                    patterns_added=result.get("patterns_added", 0),
                )
                return {"success": result.get("success", False), "result": result}
            except httpx.TimeoutException:
                logger.error("pattern_matching_timeout")
                return {"success": False, "error": "Timeout (10 min)"}
            except Exception as e:
                logger.error("pattern_matching_update_failed", error=str(e))
                return {"success": False, "error": str(e)}

    async def get_pattern_matching_status(self) -> Dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(f"{self.pattern_matching_url}/api/data/stats")
                stats = response.json()
                response2 = await client.get(
                    f"{self.pattern_matching_url}/api/available-dates",
                    params={"limit": 5},
                )
                dates = response2.json()
                return {
                    "success": True,
                    "newest_flat_file": dates.get("last"),
                    "total_files": stats.get("files_count"),
                    "last_5_dates": dates.get("dates", []),
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

    async def sync_for_date(self, target_date: date) -> Dict:
        """
        Sincronizar flat files para una fecha específica.
        
        Proceso:
        1. Verificar disponibilidad en Polygon S3 (minute + day)
        2. Si están: descargar para servicios locales
        3. Si están: actualizar Pattern Matching
        """
        logger.info("flat_files_sync_starting", target_date=target_date.isoformat())

        result: Dict = {
            "target_date": target_date.isoformat(),
            "started_at": datetime.now(NY_TZ).isoformat(),
            "minute_aggs_available": False,
            "day_aggs_available": False,
            "flat_files_downloaded": False,
            "pattern_matching_updated": False,
            "success": False,
        }

        if not self.has_credentials:
            result["error"] = "missing_credentials"
            logger.error(
                "flat_files_sync_aborted",
                reason="missing_s3_credentials",
                target_date=target_date.isoformat(),
            )
            return result

        try:
            minute_exists = await self.check_file_exists_in_polygon(target_date, "minute_aggs")
            day_exists = await self.check_file_exists_in_polygon(target_date, "day_aggs")
        except Exception as e:
            result["error"] = f"s3_check_failed: {e}"
            logger.error("flat_files_s3_check_failed", error=str(e))
            return result

        result["minute_aggs_available"] = minute_exists
        result["day_aggs_available"] = day_exists

        if not minute_exists:
            logger.info(
                "minute_aggs_not_available_yet",
                date=target_date.isoformat(),
            )
            result["message"] = "minute_aggs not available in Polygon yet"
            return result

        if day_exists:
            download_result = await self.download_flat_files_for_local_services(target_date)
            result["flat_files_downloaded"] = download_result.get("success", False)
            result["day_aggs_downloaded"] = download_result.get("success", False)

        pm_result = await self.update_pattern_matching(target_date)
        result["pattern_matching_updated"] = pm_result.get("success", False)
        result["pattern_matching_result"] = pm_result.get("result")

        # Éxito = ambas operaciones críticas OK
        result["success"] = bool(
            result["flat_files_downloaded"] and result["pattern_matching_updated"]
        )
        result["completed_at"] = datetime.now(NY_TZ).isoformat()

        if result["success"]:
            logger.info("flat_files_sync_completed", target_date=target_date.isoformat())
        else:
            logger.warning("flat_files_sync_partial", result=result)

        return result


class FlatFilesWatcher:
    """
    Monitor que sincroniza flat files después del cierre del mercado.
    
    MEJORAS sobre la versión anterior:
    1. BACKFILL multi-día: Detecta y procesa todos los días faltantes
       (no sólo el último) hasta MAX_BACKFILL_DAYS de antigüedad.
    2. VALIDACIÓN al arranque: comprueba credenciales S3 antes de operar.
    3. OBSERVABILIDAD: publica métricas a Redis para dashboards/alertas.
    4. ALERTA staleness: si la última sincronización lleva > 18h en
       horario post-market, emite log ERROR estructurado.
    """

    REDIS_LAST_SYNCED_DATE = "flat_files:last_synced_date"
    REDIS_LAST_SYNCED_AT = "flat_files:last_synced_at"
    REDIS_LAST_CHECK_AT = "flat_files:last_check_at"
    REDIS_LAST_ERROR = "flat_files:last_error"
    REDIS_CREDENTIALS_OK = "flat_files:credentials_ok"

    def __init__(self, redis_client, daily_scheduler: "DailyMaintenanceScheduler"):
        self.redis = redis_client
        self.daily_scheduler = daily_scheduler
        self.sync_task = SyncFlatFilesTask()
        self.is_running = False
        self._check_interval = 1800  # 30 minutos

    async def _is_synced(self, target_date: date) -> bool:
        key = f"flat_files:synced:{target_date.isoformat()}"
        return await self.redis.get(key) is not None

    async def _mark_synced(self, target_date: date) -> None:
        key = f"flat_files:synced:{target_date.isoformat()}"
        await self.redis.set(key, "1", ttl=86400 * 30)  # 30 días
        # Métricas globales
        now_iso = datetime.now(NY_TZ).isoformat()
        await self.redis.set(self.REDIS_LAST_SYNCED_DATE, target_date.isoformat())
        await self.redis.set(self.REDIS_LAST_SYNCED_AT, now_iso)
        await self.redis.set(self.REDIS_LAST_ERROR, "")

    async def _record_check(self, error: Optional[str] = None) -> None:
        now_iso = datetime.now(NY_TZ).isoformat()
        await self.redis.set(self.REDIS_LAST_CHECK_AT, now_iso)
        if error:
            await self.redis.set(self.REDIS_LAST_ERROR, error)

    async def _missing_trading_days(
        self,
        today: date,
        max_days: int = MAX_BACKFILL_DAYS,
    ) -> List[date]:
        """
        Recopila los días de trading faltantes en orden ascendente.
        
        - Inspecciona los últimos `max_days` días naturales hacia atrás
        - Filtra los que NO sean trading day (fines de semana / holidays)
        - Devuelve sólo los que aún no estén marcados como sincronizados
        """
        missing: List[date] = []
        for offset in range(1, max_days + 1):
            day = today - timedelta(days=offset)
            try:
                is_trading = await self.daily_scheduler._is_trading_day(day)
            except AttributeError:
                # Fallback si el método privado tiene otro nombre/version
                is_trading = day.weekday() < 5
            if not is_trading:
                continue
            if await self._is_synced(day):
                continue
            missing.append(day)
        # Ordenar de más antiguo a más reciente para procesar en orden cronológico
        return sorted(missing)

    async def _check_staleness(self) -> None:
        """Emite log ERROR si la última sync lleva > STALE_THRESHOLD_HOURS."""
        last_at = await self.redis.get(self.REDIS_LAST_SYNCED_AT)
        if not last_at or not isinstance(last_at, str):
            return
        try:
            last_dt = datetime.fromisoformat(last_at)
        except (TypeError, ValueError):
            return
        now = datetime.now(NY_TZ)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=NY_TZ)
        delta_h = (now - last_dt).total_seconds() / 3600.0
        if delta_h > STALE_THRESHOLD_HOURS:
            logger.error(
                "flat_files_stale_alert",
                hours_since_last_sync=round(delta_h, 1),
                last_synced_at=last_at,
                threshold_hours=STALE_THRESHOLD_HOURS,
                action_required="Investigar Polygon S3 / credenciales / red",
            )

    async def check_and_sync(self) -> Optional[Dict]:
        """
        Verifica y sincroniza TODOS los días faltantes (backfill multi-día).
        
        - Sin credenciales → no-op con log claro
        - Sin días faltantes → no-op silencioso
        - Con días faltantes → procesa en orden cronológico, marcando cada éxito
        """
        await self._record_check()

        if not self.sync_task.has_credentials:
            await self._record_check(error="missing_s3_credentials")
            logger.error(
                "flat_files_watcher_no_credentials",
                hint="Define POLYGON_S3_ACCESS_KEY/POLYGON_S3_SECRET_KEY en data_maintenance",
            )
            return None

        now_et = datetime.now(NY_TZ)
        today = now_et.date()
        missing_days = await self._missing_trading_days(today)

        if not missing_days:
            logger.debug("flat_files_no_pending_days")
            await self._check_staleness()
            return None

        logger.info(
            "flat_files_backfill_starting",
            days_pending=len(missing_days),
            oldest=missing_days[0].isoformat(),
            newest=missing_days[-1].isoformat(),
        )

        results: List[Dict] = []
        first_failure: Optional[Dict] = None

        for day in missing_days:
            try:
                result = await self.sync_task.sync_for_date(day)
            except Exception as e:
                logger.error("flat_files_sync_exception", day=day.isoformat(), error=str(e))
                result = {"target_date": day.isoformat(), "success": False, "error": str(e)}

            results.append(result)

            if result.get("success"):
                await self._mark_synced(day)
                continue

            # Si fue un día reciente cuyo flat aún no se publicó, no lo
            # consideramos "fallo" — simplemente saltamos el resto.
            if result.get("message") == "minute_aggs not available in Polygon yet":
                logger.info(
                    "flat_files_skipping_unpublished_day",
                    day=day.isoformat(),
                )
                # No reintentamos los días posteriores en esta pasada
                break

            # Fallo real → registrar y abortar el backfill (lo retomará en
            # el próximo ciclo, así no martilleamos el endpoint).
            if first_failure is None:
                first_failure = result
            await self._record_check(error=str(result.get("error") or result.get("message") or "unknown"))
            logger.warning(
                "flat_files_backfill_aborted_on_failure",
                day=day.isoformat(),
                will_retry_next_cycle=True,
            )
            break

        await self._check_staleness()

        return {
            "days_attempted": len(results),
            "results": results,
            "first_failure": first_failure,
        }

    async def run(self):
        """
        Loop principal del watcher.
        
        Solo verifica después del cierre del mercado (5 PM - 9 AM ET).
        """
        self.is_running = True
        logger.info("flat_files_watcher_started")

        # Validar credenciales al arrancar (smoke test)
        validation = self.sync_task.validate_credentials()
        if validation["ok"]:
            await self.redis.set(FlatFilesWatcher.REDIS_CREDENTIALS_OK, "1")
            logger.info("flat_files_credentials_validated")
        else:
            await self.redis.set(FlatFilesWatcher.REDIS_CREDENTIALS_OK, "0")
            logger.error(
                "flat_files_credentials_invalid",
                **validation,
            )

        while self.is_running:
            try:
                now_et = datetime.now(NY_TZ)
                hour = now_et.hour
                # Sólo después del cierre del mercado (5 PM - 9 AM ET)
                should_check = hour >= 17 or hour < 9

                if should_check:
                    result = await self.check_and_sync()
                    if result and result.get("days_attempted"):
                        logger.info(
                            "flat_files_backfill_pass_completed",
                            days_attempted=result["days_attempted"],
                        )
                else:
                    logger.debug("flat_files_skipping_during_market_hours", hour=hour)

                await asyncio.sleep(self._check_interval)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("flat_files_watcher_error", error=str(e))
                await self._record_check(error=str(e))
                await asyncio.sleep(60)

        logger.info("flat_files_watcher_stopped")

    def stop(self):
        self.is_running = False
