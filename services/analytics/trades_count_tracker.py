"""
TradesCountTracker - Acumulador de trades del día desde WebSocket aggregates.

Consume el stream:realtime:aggregates y suma los trades (n) de cada símbolo
para proporcionar trades_today en tiempo real.
"""
import asyncio
from typing import Dict, Optional
from datetime import datetime
import pytz
import structlog

logger = structlog.get_logger(__name__)

ET = pytz.timezone("America/New_York")


class TradesCountTracker:
    """
    Acumula el número de trades del día para cada símbolo.
    
    Consume: stream:realtime:aggregates (campo 'trades')
    Provee: trades_today por símbolo
    
    MEMORIA: ~20 bytes por símbolo (string + int)
    Para 5000 símbolos = ~100KB máximo
    """
    
    name = "trades_count_tracker"
    
    # Límite de seguridad para evitar memory leaks
    MAX_SYMBOLS = 5000
    
    def __init__(self, redis_client):
        self.redis = redis_client
        
        # trades_today por símbolo
        self._trades_today: Dict[str, int] = {}
        
        # Control
        self._running = False
        self._last_consumer_id = "$"  # $ = solo mensajes nuevos (no históricos)
        
        # Stats
        self._updates_processed = 0
        self._current_date: Optional[str] = None
        
        logger.info("trades_count_tracker_initialized", max_symbols=self.MAX_SYMBOLS)
    
    async def run_consumer(self):
        """
        Ejecuta el consumidor del stream de aggregates.
        Este método corre indefinidamente - diseñado para ser ejecutado con asyncio.create_task().
        """
        if self._running:
            return
        
        self._running = True
        logger.info("trades_count_tracker_consumer_started")
        await self._consume_aggregates()  # Corre indefinidamente
    
    async def stop(self):
        """Detiene el tracker."""
        self._running = False
        logger.info("trades_count_tracker_stopped", 
                   total_updates=self._updates_processed,
                   symbols_tracked=len(self._trades_today))
    
    async def _consume_aggregates(self):
        """Consume aggregates y acumula trades usando consumer group."""
        stream_name = "stream:realtime:aggregates"
        consumer_group = "analytics_trades_count_consumer"
        consumer_name = "analytics_trades_count_1"
        
        # Crear consumer group si no existe
        try:
            await self.redis.create_consumer_group(
                stream_name,
                consumer_group,
                mkstream=True
            )
            logger.info("trades_count_consumer_group_created", group=consumer_group)
        except Exception as e:
            logger.debug("trades_count_consumer_group_exists", error=str(e))
        
        while self._running:
            try:
                # Leer mensajes usando consumer group
                messages = await self.redis.read_stream(
                    stream_name=stream_name,
                    consumer_group=consumer_group,
                    consumer_name=consumer_name,
                    count=500,  # Batch grande
                    block=1000  # 1 segundo
                )
                
                if not messages:
                    continue
                
                message_ids_to_ack = []
                
                for stream, stream_messages in messages:
                    for msg_id, fields in stream_messages:
                        message_ids_to_ack.append(msg_id)
                        await self._process_aggregate(fields)
                
                # ACK mensajes procesados
                if message_ids_to_ack:
                    try:
                        await self.redis.xack(
                            stream_name,
                            consumer_group,
                            *message_ids_to_ack
                        )
                    except Exception as e:
                        logger.error("trades_count_xack_error", error=str(e))
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Auto-healing para NOGROUP
                if 'NOGROUP' in str(e):
                    logger.warn("trades_count_consumer_group_missing_recreating")
                    try:
                        await self.redis.create_consumer_group(
                            stream_name,
                            consumer_group,
                            start_id="0",
                            mkstream=True
                        )
                        continue
                    except Exception:
                        pass
                
                logger.error("trades_consumer_error", error=str(e))
                await asyncio.sleep(1)
    
    async def _process_aggregate(self, fields: Dict):
        """Procesa un mensaje de aggregate y acumula trades."""
        try:
            symbol = fields.get('symbol') or fields.get(b'symbol')
            trades_str = fields.get('trades') or fields.get(b'trades')
            
            if isinstance(symbol, bytes):
                symbol = symbol.decode('utf-8')
            if isinstance(trades_str, bytes):
                trades_str = trades_str.decode('utf-8')
            
            if not symbol or not trades_str:
                return
            
            trades = int(trades_str) if trades_str else 0
            if trades <= 0:
                return
            
            # Verificar si es un nuevo día
            now = datetime.now(ET)
            today_str = now.strftime("%Y-%m-%d")
            
            if self._current_date != today_str:
                # Nuevo día - resetear
                self._trades_today.clear()
                self._current_date = today_str
                logger.info("trades_tracker_new_day", date=today_str)
            
            # Acumular trades (con límite de seguridad)
            if symbol not in self._trades_today:
                # Protección contra memory leak
                if len(self._trades_today) >= self.MAX_SYMBOLS:
                    # Loggear solo una vez cada 1000 intentos
                    if self._updates_processed % 1000 == 0:
                        logger.warning("trades_tracker_max_symbols_reached", 
                                      max=self.MAX_SYMBOLS,
                                      current=len(self._trades_today))
                    return
                self._trades_today[symbol] = 0
            
            self._trades_today[symbol] += trades
            self._updates_processed += 1
            
        except Exception as e:
            logger.error("process_aggregate_error", error=str(e))
    
    def get_trades_today(self, symbol: str) -> Optional[int]:
        """Obtiene trades acumulados del día para un símbolo."""
        return self._trades_today.get(symbol)
    
    def reset_for_new_day(self):
        """Resetea los contadores para un nuevo día."""
        prev_count = len(self._trades_today)
        self._trades_today.clear()
        self._current_date = datetime.now(ET).strftime("%Y-%m-%d")
        logger.info("trades_tracker_reset", 
                   previous_symbols=prev_count,
                   new_date=self._current_date)
    
    def get_stats(self) -> Dict:
        """Retorna estadísticas del tracker."""
        symbols_count = len(self._trades_today)
        # Estimación: ~20 bytes por símbolo (key string ~12 bytes + int 8 bytes)
        estimated_memory_kb = round(symbols_count * 20 / 1024, 2)
        
        return {
            "symbols_tracked": symbols_count,
            "max_symbols": self.MAX_SYMBOLS,
            "updates_processed": self._updates_processed,
            "current_date": self._current_date,
            "estimated_memory_kb": estimated_memory_kb,
            "sample_data": dict(list(self._trades_today.items())[:5])
        }

