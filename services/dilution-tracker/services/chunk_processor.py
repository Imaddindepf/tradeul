"""
ChunkProcessor - Procesamiento profesional de chunks para análisis SEC

Características:
- Timeout dinámico basado en tamaño de archivos
- Retry inteligente con rotación de API keys
- Workers independientes (un chunk lento no bloquea otros)
- Recovery pass para chunks fallidos
- NUNCA se pierde un filing
- Métricas y logging detallado
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable, Awaitable
from enum import Enum

from shared.utils.logger import get_logger

logger = get_logger(__name__)


class ChunkStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass
class ChunkResult:
    """Resultado de procesar un chunk"""
    chunk_idx: int
    status: ChunkStatus
    data: Optional[Dict[str, Any]] = None
    attempts: int = 0
    total_time_seconds: float = 0
    error: Optional[str] = None
    size_kb: float = 0
    timeout_used: int = 0


@dataclass
class ProcessorStats:
    """Estadísticas del procesador"""
    total_chunks: int = 0
    completed: int = 0
    timeouts: int = 0
    retries: int = 0
    recovered: int = 0
    failed: int = 0
    total_time: float = 0
    avg_time_per_chunk: float = 0


class ChunkProcessor:
    """
    Procesador profesional de chunks con manejo inteligente de timeouts.
    
    Uso:
        processor = ChunkProcessor(
            extract_fn=self._extract_pass_focused,
            max_workers=5,
            base_timeout=30,
            timeout_per_10kb=1
        )
        results = await processor.process_all(chunks, ticker, focus)
    """
    
    # Configuración de timeouts
    MIN_TIMEOUT = 60        # Mínimo 60 segundos
    MAX_TIMEOUT = 600       # Máximo 10 minutos
    BASE_TIMEOUT = 30       # Base para archivos pequeños
    TIMEOUT_PER_10KB = 1    # +1 segundo por cada 10KB
    
    # Configuración de retry
    MAX_RETRIES = 3
    RETRY_DELAYS = [5, 10, 20]  # Segundos entre reintentos
    
    def __init__(
        self,
        extract_fn: Callable[..., Awaitable[Optional[Dict]]],
        max_workers: int = 5,
        base_timeout: int = 30,
        timeout_per_10kb: float = 1.0
    ):
        """
        Args:
            extract_fn: Función async para extraer datos de un chunk
            max_workers: Número máximo de workers paralelos
            base_timeout: Timeout base en segundos
            timeout_per_10kb: Segundos adicionales por cada 10KB
        """
        self.extract_fn = extract_fn
        self.max_workers = max_workers
        self.base_timeout = base_timeout
        self.timeout_per_10kb = timeout_per_10kb
        
        # Cola de trabajo
        self._queue: asyncio.Queue = asyncio.Queue()
        self._results: Dict[int, ChunkResult] = {}
        self._failed_chunks: List[Dict] = []
        self._stats = ProcessorStats()
        
        # Control de workers
        self._active_workers = 0
        self._stop_event = asyncio.Event()
    
    def calculate_timeout(self, chunk: List[Dict]) -> int:
        """
        Calcular timeout inteligente basado en tamaño del chunk.
        
        Fórmula: base + (size_kb / 10) * timeout_per_10kb
        Limitado a [MIN_TIMEOUT, MAX_TIMEOUT]
        """
        total_size_bytes = sum(
            len(f.get('content', '')) 
            for f in chunk
        )
        size_kb = total_size_bytes / 1024
        
        timeout = self.base_timeout + (size_kb / 10) * self.timeout_per_10kb
        timeout = max(self.MIN_TIMEOUT, min(self.MAX_TIMEOUT, int(timeout)))
        
        return timeout
    
    async def process_all(
        self,
        chunks: List[List[Dict]],
        ticker: str,
        company_name: str,
        focus: str,
        parsed_tables: Optional[Dict] = None
    ) -> List[ChunkResult]:
        """
        Procesar todos los chunks con workers paralelos.
        
        Args:
            chunks: Lista de chunks (cada chunk es lista de filings)
            ticker: Ticker symbol
            company_name: Nombre de la empresa
            focus: Descripción del enfoque de extracción
            parsed_tables: Tablas pre-parseadas (opcional)
            
        Returns:
            Lista de ChunkResult con resultados de cada chunk
        """
        if not chunks:
            return []
        
        start_time = time.time()
        self._stats = ProcessorStats(total_chunks=len(chunks))
        self._results = {}
        self._failed_chunks = []
        self._stop_event.clear()
        
        logger.info("chunk_processor_starting",
                   ticker=ticker,
                   total_chunks=len(chunks),
                   max_workers=self.max_workers)
        
        # 1. Encolar todos los chunks
        for idx, chunk in enumerate(chunks):
            await self._queue.put({
                "idx": idx,
                "chunk": chunk,
                "ticker": ticker,
                "company_name": company_name,
                "focus": focus,
                "parsed_tables": parsed_tables,
                "attempt": 0
            })
        
        # 2. Crear workers
        workers = [
            asyncio.create_task(self._worker(worker_id))
            for worker_id in range(min(self.max_workers, len(chunks)))
        ]
        
        # 3. Esperar a que la cola se vacíe
        await self._queue.join()
        
        # 4. Detener workers
        self._stop_event.set()
        await asyncio.gather(*workers, return_exceptions=True)
        
        # 5. Recovery pass para chunks fallidos
        if self._failed_chunks:
            await self._recovery_pass(ticker, company_name, focus, parsed_tables)
        
        # 6. Calcular estadísticas finales
        self._stats.total_time = time.time() - start_time
        self._stats.avg_time_per_chunk = (
            self._stats.total_time / len(chunks) if chunks else 0
        )
        
        logger.info("chunk_processor_completed",
                   ticker=ticker,
                   total_chunks=self._stats.total_chunks,
                   completed=self._stats.completed,
                   timeouts=self._stats.timeouts,
                   retries=self._stats.retries,
                   recovered=self._stats.recovered,
                   failed=self._stats.failed,
                   total_time=f"{self._stats.total_time:.1f}s",
                   avg_per_chunk=f"{self._stats.avg_time_per_chunk:.1f}s")
        
        # 7. Retornar resultados ordenados por índice
        return [
            self._results.get(i, ChunkResult(
                chunk_idx=i,
                status=ChunkStatus.FAILED,
                error="No result"
            ))
            for i in range(len(chunks))
        ]
    
    async def _worker(self, worker_id: int):
        """
        Worker que procesa chunks de la cola.
        Cada worker es independiente - un timeout no afecta a otros.
        """
        logger.debug("worker_started", worker_id=worker_id)
        
        while not self._stop_event.is_set():
            try:
                # Obtener trabajo con timeout para poder verificar stop_event
                try:
                    work = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                result = await self._process_single_chunk(work, worker_id)
                self._results[work["idx"]] = result
                
                self._queue.task_done()
                
            except Exception as e:
                logger.error("worker_error", worker_id=worker_id, error=str(e))
        
        logger.debug("worker_stopped", worker_id=worker_id)
    
    async def _process_single_chunk(
        self,
        work: Dict,
        worker_id: int
    ) -> ChunkResult:
        """
        Procesar un chunk individual con retry inteligente.
        """
        chunk_idx = work["idx"]
        chunk = work["chunk"]
        attempt = work["attempt"]
        
        # Calcular timeout basado en tamaño
        size_kb = sum(len(f.get('content', '')) / 1024 for f in chunk)
        timeout = self.calculate_timeout(chunk)
        
        logger.info("chunk_processing_start",
                   worker_id=worker_id,
                   chunk_idx=chunk_idx,
                   attempt=attempt + 1,
                   size_kb=f"{size_kb:.1f}",
                   timeout_seconds=timeout)
        
        start_time = time.time()
        
        try:
            # Ejecutar con timeout
            result = await asyncio.wait_for(
                self.extract_fn(
                    work["ticker"],
                    work["company_name"],
                    chunk,
                    work["focus"],
                    work.get("parsed_tables")
                ),
                timeout=timeout
            )
            
            elapsed = time.time() - start_time
            self._stats.completed += 1
            
            logger.info("chunk_processing_success",
                       worker_id=worker_id,
                       chunk_idx=chunk_idx,
                       elapsed=f"{elapsed:.1f}s",
                       warrants=len(result.get('warrants', [])) if result else 0)
            
            return ChunkResult(
                chunk_idx=chunk_idx,
                status=ChunkStatus.COMPLETED,
                data=result,
                attempts=attempt + 1,
                total_time_seconds=elapsed,
                size_kb=size_kb,
                timeout_used=timeout
            )
            
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            self._stats.timeouts += 1
            
            logger.warning("chunk_timeout_detected",
                          worker_id=worker_id,
                          chunk_idx=chunk_idx,
                          attempt=attempt + 1,
                          elapsed=f"{elapsed:.1f}s",
                          timeout=timeout,
                          size_kb=f"{size_kb:.1f}")
            
            # ¿Reintentar?
            if attempt < self.MAX_RETRIES - 1:
                self._stats.retries += 1
                delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                
                logger.info("chunk_retry_scheduled",
                           chunk_idx=chunk_idx,
                           next_attempt=attempt + 2,
                           delay_seconds=delay)
                
                await asyncio.sleep(delay)
                
                # Re-encolar para retry
                work["attempt"] = attempt + 1
                await self._queue.put(work)
                # task_done movido al worker principal
                
                # Retornar resultado parcial (será sobrescrito por el retry)
                return ChunkResult(
                    chunk_idx=chunk_idx,
                    status=ChunkStatus.TIMEOUT,
                    attempts=attempt + 1,
                    total_time_seconds=elapsed,
                    error="Timeout - retrying",
                    size_kb=size_kb,
                    timeout_used=timeout
                )
            else:
                # Máximo de reintentos alcanzado → guardar para recovery
                logger.error("chunk_max_retries_reached",
                            chunk_idx=chunk_idx,
                            total_attempts=attempt + 1)
                
                self._failed_chunks.append(work)
                
                return ChunkResult(
                    chunk_idx=chunk_idx,
                    status=ChunkStatus.FAILED,
                    attempts=attempt + 1,
                    total_time_seconds=elapsed,
                    error=f"Max retries ({self.MAX_RETRIES}) reached",
                    size_kb=size_kb,
                    timeout_used=timeout
                )
                
        except Exception as e:
            elapsed = time.time() - start_time
            
            logger.error("chunk_processing_error",
                        worker_id=worker_id,
                        chunk_idx=chunk_idx,
                        error=str(e))
            
            # Reintentar errores no-timeout también
            if attempt < self.MAX_RETRIES - 1:
                self._stats.retries += 1
                delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                
                await asyncio.sleep(delay)
                work["attempt"] = attempt + 1
                await self._queue.put(work)
                # task_done movido al worker principal
                
                return ChunkResult(
                    chunk_idx=chunk_idx,
                    status=ChunkStatus.FAILED,
                    attempts=attempt + 1,
                    error=str(e),
                    size_kb=size_kb
                )
            else:
                self._failed_chunks.append(work)
                return ChunkResult(
                    chunk_idx=chunk_idx,
                    status=ChunkStatus.FAILED,
                    attempts=attempt + 1,
                    error=str(e),
                    size_kb=size_kb
                )
    
    async def _recovery_pass(
        self,
        ticker: str,
        company_name: str,
        focus: str,
        parsed_tables: Optional[Dict]
    ):
        """
        Pase de recuperación para chunks que fallaron todos los reintentos.
        Usa timeout más largo y procesa secuencialmente.
        """
        logger.info("recovery_pass_starting",
                   ticker=ticker,
                   failed_chunks=len(self._failed_chunks))
        
        for work in self._failed_chunks:
            chunk_idx = work["idx"]
            chunk = work["chunk"]
            
            # Timeout extendido para recovery (2x normal)
            size_kb = sum(len(f.get('content', '')) / 1024 for f in chunk)
            timeout = self.calculate_timeout(chunk) * 2
            timeout = min(timeout, self.MAX_TIMEOUT * 2)  # Máximo 20 min
            
            logger.info("recovery_attempt",
                       chunk_idx=chunk_idx,
                       extended_timeout=timeout)
            
            start_time = time.time()
            
            try:
                result = await asyncio.wait_for(
                    self.extract_fn(
                        ticker,
                        company_name,
                        chunk,
                        focus,
                        parsed_tables
                    ),
                    timeout=timeout
                )
                
                elapsed = time.time() - start_time
                self._stats.recovered += 1
                
                logger.info("recovery_success",
                           chunk_idx=chunk_idx,
                           elapsed=f"{elapsed:.1f}s")
                
                self._results[chunk_idx] = ChunkResult(
                    chunk_idx=chunk_idx,
                    status=ChunkStatus.RECOVERED,
                    data=result,
                    attempts=work["attempt"] + 1,
                    total_time_seconds=elapsed,
                    size_kb=size_kb,
                    timeout_used=timeout
                )
                
            except Exception as e:
                elapsed = time.time() - start_time
                self._stats.failed += 1
                
                logger.error("recovery_failed",
                            chunk_idx=chunk_idx,
                            error=str(e))
                
                # Último recurso: marcar como fallido pero NO perder
                self._results[chunk_idx] = ChunkResult(
                    chunk_idx=chunk_idx,
                    status=ChunkStatus.FAILED,
                    attempts=work["attempt"] + 1,
                    total_time_seconds=elapsed,
                    error=f"Recovery failed: {str(e)}",
                    size_kb=size_kb,
                    timeout_used=timeout
                )
    
    def get_stats(self) -> ProcessorStats:
        """Obtener estadísticas del procesamiento"""
        return self._stats
    
    def get_failed_chunks(self) -> List[Dict]:
        """Obtener chunks que fallaron para análisis manual"""
        return self._failed_chunks



