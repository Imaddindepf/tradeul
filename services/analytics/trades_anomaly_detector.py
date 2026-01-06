"""
Trades Anomaly Detector - Detección de Anomalías por Z-Score de Trades
=======================================================================

Este módulo implementa detección de anomalías en tiempo real basada en
el número de transacciones (trades), usando Z-Score estadístico.

CONCEPTO:
- Trade Count = Número de transacciones individuales ejecutadas
- Z-Score = (trades_hoy - promedio_historico) / desviacion_estandar
- Si Z-Score > 3.0 → ANOMALÍA DETECTADA

FUENTE DE DATOS:
- Polygon API: campo "n" en aggregates (barras 1min/5min/día)
- TimescaleDB: tabla volume_slots columna trades_count
- Actualizado diariamente por data_maintenance service

EJEMPLO REAL:
- BIVI: Promedio 5d = 660 trades/día
- BIVI hoy: 159,263 trades
- Z-Score: (159263 - 660) / 156 = 1015.78 → ANOMALÍA EXTREMA

REFERENCIAS:
- Polygon Aggregates: https://polygon.io/docs/stocks/get_v2_aggs_ticker__stocksticker__range__multiplier___timespan___from___to
- Similar a: Trade Ideas, Massive.com anomaly detection workflow
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple, NamedTuple
import structlog

from shared.utils.redis_client import RedisClient

logger = structlog.get_logger(__name__)


class AnomalyResult(NamedTuple):
    """Resultado de detección de anomalía para un símbolo"""
    trades_today: int           # Trades ejecutados hoy
    avg_trades_5d: float        # Promedio histórico 5 días
    std_trades_5d: float        # Desviación estándar 5 días
    z_score: float              # Z-Score calculado
    is_anomaly: bool            # True si Z-Score > threshold


class TradesAnomalyDetector:
    """
    Detector de anomalías basado en Z-Score de número de transacciones.
    
    Arquitectura:
    1. Pre-computa baselines (avg, std) desde TimescaleDB → Redis HASH
    2. En tiempo real: calcula Z-Score usando trades actuales
    3. Detecta anomalías cuando Z-Score > threshold (default 3.0)
    
    Patrón igual a RVOLCalculator:
    - Redis HASH para cache: trades:baseline:{SYMBOL}:{DAYS}
    - HTTP bulk request a Historical service para precargar
    - Detección en O(1) una vez cacheado
    """
    
    def __init__(
        self,
        redis_client: RedisClient,
        lookback_days: int = 5,
        z_score_threshold: float = 3.0
    ):
        """
        Inicializa el detector de anomalías.
        
        ARQUITECTURA:
        - Los baselines (avg, std) son pre-calculados por data_maintenance service
        - Almacenados en Redis HASH: trades:baseline:{symbol}:{days}
        - Este detector solo LEE de Redis para calcular Z-Score en tiempo real
        
        Args:
            redis_client: Cliente Redis para cache
            lookback_days: Días históricos para baseline (default 5, debe coincidir con maintenance)
            z_score_threshold: Umbral para considerar anomalía (default 3.0)
        """
        self.redis = redis_client
        self.lookback_days = lookback_days
        self.z_score_threshold = z_score_threshold
        
        # Cache prefix para Redis HASH (pre-calculado por data_maintenance)
        # Hash Key: "trades:baseline:{symbol}:{days}" → {avg: "X", std: "Y"}
        self.baseline_cache_prefix = "trades:baseline"
        
        # Cache en memoria de trades actuales por símbolo
        # {symbol: trades_count_today}
        self._trades_today: Dict[str, int] = {}
        
        # Stats
        self._total_detections = 0
        self._anomalies_found = 0
        
        logger.info(
            "trades_anomaly_detector_initialized",
            lookback_days=lookback_days,
            z_score_threshold=z_score_threshold
        )
    
    def update_trades_today(self, symbol: str, trades_count: int):
        """
        Actualiza el contador de trades de hoy para un símbolo.
        
        Args:
            symbol: Ticker symbol
            trades_count: Número de transacciones (de Polygon day.n)
        """
        if trades_count > 0:
            self._trades_today[symbol.upper()] = trades_count
    
    async def detect_anomaly(
        self,
        symbol: str,
        trades_today: Optional[int] = None
    ) -> Optional[AnomalyResult]:
        """
        Detecta si hay anomalía en el número de trades de un símbolo.
        
        Args:
            symbol: Ticker symbol
            trades_today: Trades de hoy (opcional, usa cache si no se proporciona)
        
        Returns:
            AnomalyResult con métricas o None si no hay datos suficientes
        """
        sym = symbol.upper()
        self._total_detections += 1
        
        # 1. Obtener trades de hoy
        if trades_today is None:
            trades_today = self._trades_today.get(sym, 0)
        
        if trades_today == 0:
            return None
        
        # 2. Obtener baseline histórico (avg, std)
        baseline = await self._get_baseline(sym)
        
        if baseline is None:
            return None
        
        avg_trades, std_trades = baseline
        
        # 3. Calcular Z-Score
        # Evitar división por cero
        if std_trades <= 0:
            # Si std = 0, significa que todos los días tuvieron el mismo número
            # Si trades_today es muy diferente, es anomalía
            if avg_trades > 0 and trades_today > avg_trades * 2:
                z_score = 10.0  # Asignar Z alto
            else:
                z_score = 0.0
        else:
            z_score = (trades_today - avg_trades) / std_trades
        
        # 4. Determinar si es anomalía
        is_anomaly = z_score >= self.z_score_threshold
        
        if is_anomaly:
            self._anomalies_found += 1
            logger.info(
                "🔥 ANOMALY_DETECTED",
                symbol=sym,
                trades_today=trades_today,
                avg_trades=round(avg_trades, 2),
                std_trades=round(std_trades, 2),
                z_score=round(z_score, 2)
            )
        
        return AnomalyResult(
            trades_today=trades_today,
            avg_trades_5d=avg_trades,
            std_trades_5d=std_trades,
            z_score=z_score,
            is_anomaly=is_anomaly
        )
    
    async def detect_anomaly_batch(
        self,
        symbols_with_trades: Dict[str, int]
    ) -> Dict[str, AnomalyResult]:
        """
        Detecta anomalías para múltiples símbolos en batch.
        
        NOTA: Los baselines ya están pre-calculados en Redis por data_maintenance.
        Este método solo lee de Redis y calcula Z-Scores.
        
        Args:
            symbols_with_trades: Dict {symbol: trades_today}
        
        Returns:
            Dict {symbol: AnomalyResult}
        """
        results = {}
        
        for symbol, trades_today in symbols_with_trades.items():
            result = await self.detect_anomaly(symbol, trades_today)
            if result is not None:
                results[symbol] = result
        
        return results
    
    async def _get_baseline(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        Obtiene baseline histórico (avg, std) para un símbolo desde Redis.
        
        Los baselines son pre-calculados por data_maintenance service cada noche.
        Redis HASH: trades:baseline:{symbol}:{days} → {avg, std}
        
        Returns:
            Tuple (avg_trades, std_trades) o None si no hay datos
        """
        sym = symbol.upper()
        days = self.lookback_days
        
        hash_key = f"{self.baseline_cache_prefix}:{sym}:{days}"
        
        try:
            cached_data = await self.redis.client.hgetall(hash_key)
            if cached_data:
                # Decodificar bytes si es necesario
                avg_str = cached_data.get(b'avg') or cached_data.get('avg')
                std_str = cached_data.get(b'std') or cached_data.get('std')
                
                if avg_str is not None and std_str is not None:
                    avg = float(avg_str.decode() if isinstance(avg_str, bytes) else avg_str)
                    std = float(std_str.decode() if isinstance(std_str, bytes) else std_str)
                    return (avg, std)
        except Exception as e:
            logger.debug("redis_baseline_read_failed", symbol=sym, error=str(e))
        
        # Los baselines se pre-calculan por data_maintenance.
        # Si no está en Redis, no hay datos históricos para este símbolo.
        return None
    
    async def reset_for_new_day(self):
        """
        Resetea caches en memoria para un nuevo día de trading.
        
        NOTA: NO limpia Redis. Los baselines históricos tienen TTL propio.
        """
        self._trades_today.clear()
        self._total_detections = 0
        self._anomalies_found = 0
        
        logger.info("trades_anomaly_detector_reset_for_new_day")
    
    async def close(self):
        """Cierra recursos al apagar el servicio (no hay recursos que cerrar)"""
        pass
    
    def get_stats(self) -> Dict:
        """Obtiene estadísticas del detector"""
        return {
            "lookback_days": self.lookback_days,
            "z_score_threshold": self.z_score_threshold,
            "symbols_tracked": len(self._trades_today),
            "total_detections": self._total_detections,
            "anomalies_found": self._anomalies_found,
            "anomaly_rate": round(
                self._anomalies_found / max(1, self._total_detections) * 100, 2
            )
        }

