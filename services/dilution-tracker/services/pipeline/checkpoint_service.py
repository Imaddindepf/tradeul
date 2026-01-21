"""
Pipeline Checkpoint Service
============================
Sistema de persistencia intermedia para debugging del pipeline de dilución.

Cada paso del pipeline guarda sus datos en Redis con TTL de 1 hora.
Esto permite:
1. Ver exactamente qué datos tenía cada paso
2. Identificar dónde falló la deduplicación/transformación
3. Re-ejecutar solo desde cierto paso (futuro)

Uso:
    checkpoint = PipelineCheckpoint(redis, ticker)
    await checkpoint.save("step1_filings", filings_data)
    await checkpoint.save("step2_gemini", extracted_data)
    ...
    
    # Para debugging:
    step2_data = await checkpoint.get("step2_gemini")
    all_steps = await checkpoint.get_all()
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# TTL por defecto: 24 horas (para debugging profundo)
DEFAULT_TTL = 86400  # 24 hours

# Pasos del pipeline en orden
PIPELINE_STEPS = [
    "step1_filings_fetched",
    "step2_gemini_extracted",
    "step3_pre_dedup",
    "step4_post_dedup", 
    "step5_post_enrichment",
    "step9_final"
]


class PipelineCheckpoint:
    """
    Servicio para guardar y recuperar checkpoints del pipeline.
    """
    
    REDIS_PREFIX = "pipeline_checkpoint"
    
    def __init__(self, redis_client, ticker: str):
        """
        Args:
            redis_client: Cliente Redis (RedisClient de shared.utils)
            ticker: Ticker siendo procesado
        """
        self.redis = redis_client
        self.ticker = ticker.upper()
        self.start_time = datetime.utcnow()
        self._step_times: Dict[str, datetime] = {}
    
    def _get_key(self, step: str) -> str:
        """Genera la key de Redis para un paso."""
        return f"{self.REDIS_PREFIX}:{self.ticker}:{step}"
    
    async def save(self, step: str, data: Any, metadata: Optional[Dict] = None) -> bool:
        """
        Guarda un checkpoint para un paso del pipeline.
        
        Args:
            step: Nombre del paso (ej: "step3_pre_dedup")
            data: Datos a guardar (será serializado a JSON)
            metadata: Información adicional (timestamp, counts, etc.)
            
        Returns:
            True si se guardó correctamente
        """
        try:
            now = datetime.utcnow()
            self._step_times[step] = now
            
            # Calcular estadísticas de los datos
            stats = self._calculate_stats(data)
            
            checkpoint = {
                "ticker": self.ticker,
                "step": step,
                "timestamp": now.isoformat(),
                "elapsed_seconds": (now - self.start_time).total_seconds(),
                "stats": stats,
                "metadata": metadata or {},
                "data": data
            }
            
            key = self._get_key(step)
            
            # Guardar en Redis con TTL
            # RedisClient.set() con serialize=True ya hace json.dumps internamente
            # pero como queremos control total, pasamos el dict directamente
            result = await self.redis.set(key, checkpoint, ttl=DEFAULT_TTL, serialize=True)
            
            if result:
                logger.info("pipeline_checkpoint_saved",
                           ticker=self.ticker,
                           step=step,
                           stats=stats,
                           elapsed=checkpoint["elapsed_seconds"])
            else:
                logger.warning("pipeline_checkpoint_save_returned_false",
                              ticker=self.ticker,
                              step=step)
            
            return result
            
        except Exception as e:
            logger.error("pipeline_checkpoint_save_failed",
                        ticker=self.ticker,
                        step=step,
                        error=str(e))
            return False
    
    async def get(self, step: str) -> Optional[Dict]:
        """
        Recupera un checkpoint específico.
        
        Args:
            step: Nombre del paso
            
        Returns:
            Dict con datos del checkpoint o None si no existe
        """
        try:
            key = self._get_key(step)
            # RedisClient.get() con deserialize=True ya hace json.loads internamente
            data = await self.redis.get(key, deserialize=True)
            return data
            
        except Exception as e:
            logger.error("pipeline_checkpoint_get_failed",
                        ticker=self.ticker,
                        step=step,
                        error=str(e))
            return None
    
    async def get_all(self) -> Dict[str, Dict]:
        """
        Recupera todos los checkpoints para este ticker.
        
        Returns:
            Dict con step -> checkpoint_data
        """
        result = {}
        
        for step in PIPELINE_STEPS:
            checkpoint = await self.get(step)
            if checkpoint:
                result[step] = checkpoint
        
        return result
    
    async def get_summary(self) -> Dict:
        """
        Obtiene un resumen de todos los checkpoints (sin los datos completos).
        Útil para ver rápidamente el estado del pipeline.
        
        Returns:
            Dict con resumen de cada paso
        """
        summary = {
            "ticker": self.ticker,
            "steps": {}
        }
        
        for step in PIPELINE_STEPS:
            checkpoint = await self.get(step)
            if checkpoint:
                summary["steps"][step] = {
                    "timestamp": checkpoint.get("timestamp"),
                    "elapsed_seconds": checkpoint.get("elapsed_seconds"),
                    "stats": checkpoint.get("stats"),
                    "metadata": checkpoint.get("metadata")
                }
        
        return summary
    
    async def clear(self) -> int:
        """
        Limpia todos los checkpoints para este ticker.
        
        Returns:
            Número de checkpoints eliminados
        """
        count = 0
        for step in PIPELINE_STEPS:
            key = self._get_key(step)
            try:
                deleted = await self.redis.delete(key)
                if deleted:
                    count += 1
            except Exception as e:
                logger.warning("checkpoint_delete_failed", 
                             ticker=self.ticker, 
                             step=step, 
                             error=str(e))
        
        logger.info("pipeline_checkpoints_cleared",
                   ticker=self.ticker,
                   count=count)
        return count
    
    def _calculate_stats(self, data: Any) -> Dict:
        """
        Calcula estadísticas de los datos para logging rápido.
        """
        stats = {}
        
        if isinstance(data, dict):
            for key, value in data.items():
                if key.startswith('_'):
                    continue  # Skip internal keys
                if isinstance(value, list):
                    stats[key] = len(value)
                elif isinstance(value, dict):
                    stats[key] = len(value)
                elif isinstance(value, (int, float)):
                    stats[key] = value
                elif value is not None:
                    stats[key] = "present"
        elif isinstance(data, list):
            stats["total_items"] = len(data)
        
        return stats


async def compare_checkpoints(redis_client, ticker: str, step1: str, step2: str) -> Dict:
    """
    Compara dos checkpoints para ver diferencias.
    Útil para debugging de deduplicación.
    
    Args:
        redis_client: Cliente Redis
        ticker: Ticker a analizar
        step1: Paso anterior (ej: "step3_pre_dedup")
        step2: Paso posterior (ej: "step4_post_dedup")
        
    Returns:
        Dict con diferencias entre los pasos
    """
    checkpoint = PipelineCheckpoint(redis_client, ticker)
    
    data1 = await checkpoint.get(step1)
    data2 = await checkpoint.get(step2)
    
    if not data1 or not data2:
        return {
            "error": "One or both checkpoints not found",
            "step1_exists": data1 is not None,
            "step2_exists": data2 is not None
        }
    
    comparison = {
        "ticker": ticker,
        "step1": step1,
        "step2": step2,
        "step1_stats": data1.get("stats", {}),
        "step2_stats": data2.get("stats", {}),
        "differences": {}
    }
    
    # Comparar conteos
    stats1 = data1.get("stats", {})
    stats2 = data2.get("stats", {})
    
    all_keys = set(stats1.keys()) | set(stats2.keys())
    for key in all_keys:
        v1 = stats1.get(key, 0)
        v2 = stats2.get(key, 0)
        if isinstance(v1, int) and isinstance(v2, int) and v1 != v2:
            comparison["differences"][key] = {
                "before": v1,
                "after": v2,
                "change": v2 - v1
            }
    
    return comparison
