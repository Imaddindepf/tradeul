"""
Subscription Reconciler - Patrón Profesional de Reconciliación

Inspirado en sistemas profesionales como Bloomberg Terminal y TradingView.

Este componente implementa un "Reconciliation Loop" que:
1. Lee el estado deseado desde Redis (source of truth)
2. Compara con el estado actual en Polygon WebSocket
3. Corrige automáticamente cualquier drift/desincronización

Ventajas:
- Tolerante a fallos: Auto-recovery automático
- Sin race conditions: Solo lee de source of truth
- Idempotente: Se puede ejecutar múltiples veces sin efectos adversos
- Observable: Métricas claras de drift y correcciones
"""

import asyncio
from typing import Set, Dict
from datetime import datetime

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class SubscriptionReconciler:
    """
    Reconciliation Loop para mantener sincronización entre:
    - Source of Truth (Redis SET polygon_ws:active_tickers)
    - Estado Actual (Polygon WebSocket subscribed_tickers)
    
    IMPORTANTE: Excluye del cálculo de 'extra' los tickers que están siendo
    monitoreados por otros sistemas (ej: catalyst alerts, quotes) para no
    interferir con sus suscripciones temporales.
    """
    
    def __init__(
        self,
        redis_client,
        ws_client,
        event_types: Set[str],
        interval_seconds: int = 30,
        source_of_truth_key: str = "polygon_ws:active_tickers",
        exclude_sets: list = None
    ):
        """
        Args:
            redis_client: Cliente de Redis
            ws_client: Cliente WebSocket de Polygon
            event_types: Tipos de eventos ({"A"} para aggregates)
            interval_seconds: Intervalo de reconciliación (default: 30s)
            source_of_truth_key: Key en Redis con tickers deseados
            exclude_sets: Lista de sets de tickers a excluir del cálculo de 'extra'
                          (ej: catalyst_subscribed_tickers, quote_subscribed_tickers)
        """
        self.redis = redis_client
        self.ws_client = ws_client
        self.event_types = event_types
        self.interval = interval_seconds
        self.source_key = source_of_truth_key
        self.exclude_sets = exclude_sets or []
        
        # Métricas
        self.reconciliations_count = 0
        self.total_drift_detected = 0
        self.total_corrections = 0
        self.last_reconciliation_time = None
        self.is_running = False
    
    async def start(self):
        """Iniciar el reconciliation loop"""
        self.is_running = True
        logger.info(
            "reconciliation_loop_started",
            interval_seconds=self.interval,
            source_key=self.source_key
        )
        
        while self.is_running:
            try:
                await self.reconcile()
                await asyncio.sleep(self.interval)
            
            except asyncio.CancelledError:
                logger.info("reconciliation_loop_cancelled")
                break
            
            except Exception as e:
                logger.error(
                    "reconciliation_loop_error",
                    error=str(e),
                    error_type=type(e).__name__
                )
                await asyncio.sleep(self.interval)
    
    async def reconcile(self):
        """
        Ejecutar una reconciliación completa
        
        Patrón Profesional:
        1. Leer estado deseado (source of truth)
        2. Leer estado actual
        3. Calcular diff
        4. Aplicar correcciones (subscribe faltantes, unsubscribe extra)
        5. Registrar métricas
        """
        try:
            # Solo reconciliar si estamos conectados y autenticados
            if not self.ws_client.is_authenticated:
                logger.debug("skipping_reconciliation_not_authenticated")
                return
            
            start_time = datetime.now()
            
            # 1. LEER ESTADO DESEADO (Source of Truth)
            desired_raw = await self.redis.client.smembers(self.source_key)
            desired_tickers = {
                t.decode() if isinstance(t, bytes) else t 
                for t in desired_raw
            }
            
            # 2. LEER ESTADO ACTUAL
            actual_tickers = self.ws_client.subscribed_tickers.copy()
            
            # 3. CALCULAR DIFF
            missing = desired_tickers - actual_tickers  # Faltan en Polygon
            
            # Calcular extra excluyendo tickers de otros sistemas (catalyst, quotes, etc.)
            # para no interferir con sus suscripciones temporales
            excluded_tickers: Set[str] = set()
            for exclude_set in self.exclude_sets:
                if exclude_set:
                    excluded_tickers.update(exclude_set)
            
            extra = actual_tickers - desired_tickers - excluded_tickers
            
            drift = len(missing) + len(extra)
            
            # 4. APLICAR CORRECCIONES
            corrections_made = 0
            
            if missing:
                logger.info(
                    "reconciliation_subscribing_missing",
                    count=len(missing),
                    examples=sorted(list(missing))[:10]
                )
                await self.ws_client.subscribe_to_tickers(missing, self.event_types)
                corrections_made += len(missing)
            
            if extra:
                logger.info(
                    "reconciliation_unsubscribing_extra",
                    count=len(extra),
                    examples=sorted(list(extra))[:10]
                )
                await self.ws_client.unsubscribe_from_tickers(extra, self.event_types)
                corrections_made += len(extra)
            
            # 5. REGISTRAR MÉTRICAS
            duration = (datetime.now() - start_time).total_seconds()
            
            self.reconciliations_count += 1
            self.total_drift_detected += drift
            self.total_corrections += corrections_made
            self.last_reconciliation_time = datetime.now()
            
            if drift > 0:
                logger.warning(
                    "reconciliation_drift_detected",
                    drift=drift,
                    missing=len(missing),
                    extra=len(extra),
                    corrections=corrections_made,
                    duration_seconds=round(duration, 3)
                )
            else:
                logger.info(
                    "reconciliation_perfect_sync",
                    desired=len(desired_tickers),
                    actual=len(actual_tickers),
                    duration_seconds=round(duration, 3)
                )
        
        except Exception as e:
            logger.error(
                "reconciliation_failed",
                error=str(e),
                error_type=type(e).__name__
            )
    
    async def force_reconcile(self):
        """Forzar reconciliación inmediata (útil para testing)"""
        logger.info("force_reconciliation_requested")
        await self.reconcile()
    
    def get_metrics(self) -> Dict:
        """Obtener métricas del reconciliador"""
        return {
            "reconciliations_count": self.reconciliations_count,
            "total_drift_detected": self.total_drift_detected,
            "total_corrections": self.total_corrections,
            "last_reconciliation": self.last_reconciliation_time.isoformat() if self.last_reconciliation_time else None,
            "is_running": self.is_running,
            "interval_seconds": self.interval
        }
    
    async def stop(self):
        """Detener el reconciliation loop"""
        self.is_running = False
        logger.info("reconciliation_loop_stopped")

