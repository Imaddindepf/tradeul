"""
Snapshot Manager Inteligente con Deltas
Reemplaza snapshots completos de 9MB por deltas de 50-200KB
"""

import msgpack
import zlib
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
import structlog

from .redis_client import RedisClient

logger = structlog.get_logger(__name__)


class SnapshotManager:
    """
    Manager inteligente para snapshots con estrategia delta
    
    Features:
    - Snapshots completos cada N minutos (comprimidos)
    - Deltas incrementales entre snapshots (50-200 KB vs 9 MB)
    - Compresión msgpack + zlib
    - Filtrado de cambios insignificantes
    - Auto-expiración con TTL
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        full_snapshot_interval: int = 300,  # 5 minutos
        delta_compression_threshold: int = 100,  # Comprimir si > 100 tickers
        min_price_change_percent: float = 0.001,  # 0.1% mínimo
        min_rvol_change_percent: float = 0.05  # 5% mínimo
    ):
        self.redis = redis_client
        self.full_snapshot_interval = full_snapshot_interval
        self.delta_compression_threshold = delta_compression_threshold
        self.min_price_change = min_price_change_percent
        self.min_rvol_change = min_rvol_change_percent
        
        # Estado interno
        self.previous_snapshot: Dict[str, Any] = {}
        self.last_full_snapshot_time: Optional[datetime] = None
        
        # Métricas
        self.stats = {
            "full_snapshots": 0,
            "delta_snapshots": 0,
            "total_bytes_saved": 0,
            "avg_delta_size": 0,
            "avg_full_size": 0
        }
    
    async def save_snapshot(
        self,
        current_snapshot: Dict[str, Any],
        force_full: bool = False
    ) -> Dict[str, Any]:
        """
        Guarda snapshot de forma inteligente (full o delta)
        
        Args:
            current_snapshot: Snapshot actual {symbol: data}
            force_full: Forzar snapshot completo
        
        Returns:
            Dict con info de la operación
        """
        now = datetime.now()
        
        # Decidir si enviar full o delta
        should_send_full = (
            force_full or
            self.last_full_snapshot_time is None or
            (now - self.last_full_snapshot_time).total_seconds() > self.full_snapshot_interval
        )
        
        if should_send_full:
            result = await self._save_full_snapshot(current_snapshot)
            self.last_full_snapshot_time = now
            self.stats["full_snapshots"] += 1
        else:
            result = await self._save_delta_snapshot(current_snapshot)
            self.stats["delta_snapshots"] += 1
        
        # Actualizar snapshot anterior
        self.previous_snapshot = current_snapshot
        
        return result
    
    async def _save_full_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Guarda snapshot completo con compresión agresiva
        """
        try:
            # 1. Serializar con msgpack (más eficiente que JSON)
            packed = msgpack.packb(snapshot, use_bin_type=True)
            
            # 2. Comprimir con zlib
            compressed = zlib.compress(packed, level=6)
            
            # 3. Guardar con TTL de 15 minutos (auto-expira)
            await self.redis.setex(
                "snapshot:full:latest",
                900,  # 15 min TTL
                compressed
            )
            
            # Calcular reducción
            original_size = len(str(snapshot).encode())
            compression_ratio = (1 - len(compressed) / original_size) * 100
            
            # Actualizar stats
            self.stats["avg_full_size"] = (
                (self.stats["avg_full_size"] * (self.stats["full_snapshots"] - 1) + len(compressed))
                / self.stats["full_snapshots"]
            )
            
            logger.info(
                "full_snapshot_saved",
                ticker_count=len(snapshot),
                original_size_kb=original_size / 1024,
                packed_size_kb=len(packed) / 1024,
                compressed_size_kb=len(compressed) / 1024,
                compression_ratio=f"{compression_ratio:.1f}%",
                ttl_seconds=900
            )
            
            return {
                "type": "full",
                "ticker_count": len(snapshot),
                "original_size": original_size,
                "compressed_size": len(compressed),
                "compression_ratio": compression_ratio
            }
            
        except Exception as e:
            logger.error(
                "save_full_snapshot_failed",
                error=str(e),
                ticker_count=len(snapshot),
                exc_info=True
            )
            raise
    
    async def _save_delta_snapshot(self, current: Dict[str, Any]) -> Dict[str, Any]:
        """
        Guarda solo los cambios (delta) vs snapshot anterior
        """
        try:
            # Calcular delta
            delta = self._calculate_delta(self.previous_snapshot, current)
            
            # Si no hay cambios significativos, skip
            total_changes = (
                len(delta["added"]) +
                len(delta["updated"]) +
                len(delta["removed"])
            )
            
            if total_changes == 0:
                logger.debug(
                    "delta_snapshot_skipped",
                    reason="no_significant_changes",
                    unchanged_count=delta["unchanged_count"]
                )
                return {
                    "type": "delta",
                    "skipped": True,
                    "reason": "no_changes"
                }
            
            # Serializar delta
            packed = msgpack.packb(delta, use_bin_type=True)
            
            # Comprimir solo si delta es grande
            if total_changes > self.delta_compression_threshold:
                compressed = zlib.compress(packed, level=3)  # Compresión ligera
                data = compressed
                is_compressed = True
            else:
                data = packed
                is_compressed = False
            
            # Guardar en Redis con TTL corto (deltas son temporales)
            await self.redis.setex(
                "snapshot:delta:latest",
                60,  # 1 min TTL (solo para el último delta)
                data
            )
            
            # Calcular ahorro vs full snapshot
            estimated_full_size = len(str(current).encode())
            bytes_saved = estimated_full_size - len(data)
            self.stats["total_bytes_saved"] += bytes_saved
            
            # Actualizar stats
            self.stats["avg_delta_size"] = (
                (self.stats["avg_delta_size"] * (self.stats["delta_snapshots"] - 1) + len(data))
                / self.stats["delta_snapshots"]
            )
            
            logger.info(
                "delta_snapshot_saved",
                added=len(delta["added"]),
                updated=len(delta["updated"]),
                removed=len(delta["removed"]),
                unchanged=delta["unchanged_count"],
                delta_size_kb=len(data) / 1024,
                is_compressed=is_compressed,
                bytes_saved_kb=bytes_saved / 1024,
                reduction_percent=f"{(bytes_saved / estimated_full_size) * 100:.1f}%"
            )
            
            return {
                "type": "delta",
                "added": len(delta["added"]),
                "updated": len(delta["updated"]),
                "removed": len(delta["removed"]),
                "unchanged": delta["unchanged_count"],
                "size": len(data),
                "compressed": is_compressed,
                "bytes_saved": bytes_saved
            }
            
        except Exception as e:
            logger.error(
                "save_delta_snapshot_failed",
                error=str(e),
                exc_info=True
            )
            raise
    
    def _calculate_delta(
        self,
        prev: Dict[str, Any],
        curr: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calcula delta entre dos snapshots
        Solo incluye cambios SIGNIFICATIVOS
        """
        delta = {
            "added": [],
            "updated": [],
            "removed": [],
            "unchanged_count": 0,
            "timestamp": datetime.now().isoformat()
        }
        
        prev_symbols: Set[str] = set(prev.keys())
        curr_symbols: Set[str] = set(curr.keys())
        
        # Símbolos nuevos
        for symbol in curr_symbols - prev_symbols:
            delta["added"].append({
                "symbol": symbol,
                "data": curr[symbol]
            })
        
        # Símbolos eliminados
        delta["removed"] = list(prev_symbols - curr_symbols)
        
        # Símbolos actualizados (solo cambios significativos)
        for symbol in curr_symbols & prev_symbols:
            if self._has_significant_change(prev[symbol], curr[symbol]):
                delta["updated"].append({
                    "symbol": symbol,
                    "data": curr[symbol]
                })
            else:
                delta["unchanged_count"] += 1
        
        return delta
    
    def _has_significant_change(self, old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """
        Detecta si hay cambios significativos
        Evita enviar deltas por cambios minúsculos (< 0.1%)
        """
        # Precio cambió > threshold
        old_price = old.get("price", 0)
        new_price = new.get("price", 0)
        if old_price > 0:
            price_change_pct = abs(new_price - old_price) / old_price
            if price_change_pct > self.min_price_change:
                return True
        
        # RVOL cambió > threshold
        old_rvol = old.get("rvol", 0)
        new_rvol = new.get("rvol", 0)
        if old_rvol > 0:
            rvol_change_pct = abs(new_rvol - old_rvol) / old_rvol
            if rvol_change_pct > self.min_rvol_change:
                return True
        
        # Score cambió
        if old.get("score") != new.get("score"):
            return True
        
        # Volume today cambió significativamente (> 10%)
        old_vol = old.get("volume_today", 0)
        new_vol = new.get("volume_today", 0)
        if old_vol > 0:
            vol_change_pct = abs(new_vol - old_vol) / old_vol
            if vol_change_pct > 0.1:  # 10%
                return True
        
        # Change percent cambió
        old_change = old.get("change_percent", 0)
        new_change = new.get("change_percent", 0)
        if abs(new_change - old_change) > 0.5:  # > 0.5% de cambio
            return True
        
        return False
    
    async def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene el snapshot completo más reciente
        """
        try:
            data = await self.redis.get("snapshot:full:latest")
            if not data:
                return None
            
            # Descomprimir y deserializar
            decompressed = zlib.decompress(data)
            snapshot = msgpack.unpackb(decompressed, raw=False)
            
            return snapshot
            
        except Exception as e:
            logger.error("get_latest_snapshot_failed", error=str(e))
            return None
    
    async def get_latest_delta(self) -> Optional[Dict[str, Any]]:
        """
        Obtiene el delta más reciente
        """
        try:
            data = await self.redis.get("snapshot:delta:latest")
            if not data:
                return None
            
            # Intentar descomprimir (puede no estar comprimido)
            try:
                decompressed = zlib.decompress(data)
                delta = msgpack.unpackb(decompressed, raw=False)
            except:
                # No está comprimido
                delta = msgpack.unpackb(data, raw=False)
            
            return delta
            
        except Exception as e:
            logger.error("get_latest_delta_failed", error=str(e))
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas del manager
        """
        total_snapshots = self.stats["full_snapshots"] + self.stats["delta_snapshots"]
        delta_ratio = (
            (self.stats["delta_snapshots"] / total_snapshots * 100)
            if total_snapshots > 0 else 0
        )
        
        return {
            "full_snapshots": self.stats["full_snapshots"],
            "delta_snapshots": self.stats["delta_snapshots"],
            "delta_ratio_percent": f"{delta_ratio:.1f}%",
            "avg_full_size_kb": self.stats["avg_full_size"] / 1024,
            "avg_delta_size_kb": self.stats["avg_delta_size"] / 1024,
            "total_bytes_saved_mb": self.stats["total_bytes_saved"] / (1024 * 1024),
            "last_full_snapshot": (
                self.last_full_snapshot_time.isoformat()
                if self.last_full_snapshot_time else None
            )
        }

