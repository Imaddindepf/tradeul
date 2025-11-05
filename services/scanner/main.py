"""
Scanner Service
Core scanning engine that combines real-time and historical data,
calculates indicators (RVOL), and applies configurable filters
"""

import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import sys
sys.path.append('/app')

from shared.config.settings import settings
from shared.models.scanner import ScannerResult, ScannerTicker, FilterConfig
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger, configure_logging

from scanner_engine import ScannerEngine
from scanner_categories import ScannerCategory
from hot_ticker_manager import HotTickerManager

# Configure logging
configure_logging(service_name="scanner")
logger = get_logger(__name__)


# =============================================
# GLOBALS
# =============================================

redis_client: Optional[RedisClient] = None
timescale_client: Optional[TimescaleClient] = None
scanner_engine: Optional[ScannerEngine] = None
hot_ticker_manager: Optional[HotTickerManager] = None
background_tasks: List[asyncio.Task] = []
is_running = False


# =============================================
# LIFECYCLE
# =============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the service"""
    global redis_client, timescale_client, scanner_engine, hot_ticker_manager
    
    logger.info("Starting Scanner Service")
    
    # Initialize clients
    redis_client = RedisClient()
    await redis_client.connect()
    
    timescale_client = TimescaleClient()
    await timescale_client.connect()
    
    # Initialize scanner engine
    scanner_engine = ScannerEngine(redis_client, timescale_client)
    await scanner_engine.initialize()
    
    # Initialize hot ticker manager
    hot_ticker_manager = HotTickerManager(redis_client)
    logger.info("Hot Ticker Manager initialized")
    
    logger.info("Scanner Service started (paused)")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Scanner Service")
    
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    if timescale_client:
        await timescale_client.disconnect()
    
    if redis_client:
        await redis_client.disconnect()
    
    logger.info("Scanner Service stopped")


app = FastAPI(
    title="Scanner Service",
    description="Core scanning engine with RVOL calculation and filtering",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================
# BACKGROUND TASKS (Discovery + Hot Loops)
# =============================================

async def discovery_loop():
    """
    DISCOVERY LOOP - Procesa TODO el universo (lento)
    
    - Frecuencia: cada 30 segundos
    - Procesa: ~11,000 tickers (universo completo)
    - Objetivo: Detectar nuevos líderes que entran a rankings
    """
    global is_running
    
    logger.info("🔍 Starting DISCOVERY loop (30 seg interval)")
    
    while is_running:
        try:
            start = datetime.now()
            
            # Run FULL scan (procesa todos los snapshots)
            result = await scanner_engine.run_scan()
            
            if result:
                # Actualizar hot set basado en rankings actuales
                current_rankings = {}
                for category_name, tickers in scanner_engine.last_categories.items():
                    current_rankings[category_name] = [t.symbol for t in tickers]
                
                await hot_ticker_manager.update_hot_set(current_rankings)
                
                duration = (datetime.now() - start).total_seconds()
                logger.info(
                    "🔍 Discovery scan completed",
                    filtered_count=result.filtered_count,
                    total_scanned=result.total_universe_size,
                    duration_sec=round(duration, 2),
                    hot_tickers=len(hot_ticker_manager.hot_tickers)
                )
            
            # Wait 10 seconds before next discovery (reducido de 30 para menor latencia)
            await asyncio.sleep(10)
        
        except asyncio.CancelledError:
            logger.info("Discovery loop cancelled")
            break
        except Exception as e:
            logger.error("Error in discovery loop", error=str(e))
            await asyncio.sleep(30)

async def hot_loop():
    """
    HOT LOOP - Actualiza SOLO hot tickers (rápido)
    
    - Frecuencia: cada 1 segundo
    - Procesa: 50-200 tickers (solo hot)
    - Objetivo: Mantener rankings actualizados en tiempo real
    """
    global is_running
    
    logger.info("🔥 Starting HOT loop (1 seg interval)")
    
    while is_running:
        try:
            # Si no hay hot tickers, esperar
            if not hot_ticker_manager.hot_tickers:
                await asyncio.sleep(1)
                continue
            
            # TODO: Implementar run_hot_scan() en scanner_engine
            # Por ahora, simplemente esperamos
            # En la próxima iteración implementaremos este método
            
            await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            logger.info("Hot loop cancelled")
            break
        except Exception as e:
            logger.error("Error in hot loop", error=str(e))
            await asyncio.sleep(1)


# =============================================
# API ENDPOINTS
# =============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    db_health = await timescale_client.health_check()
    redis_health = await redis_client.ping()
    
    return {
        "status": "healthy" if (db_health and redis_health) else "degraded",
        "service": "scanner",
        "is_running": is_running,
        "database": "healthy" if db_health else "unhealthy",
        "redis": "healthy" if redis_health else "unhealthy"
    }


@app.post("/api/scanner/start")
async def start_scanner():
    """Start the scanner (discovery + hot loops)"""
    global background_tasks, is_running
    
    if is_running:
        return {"status": "already_running"}
    
    is_running = True
    
    # Iniciar ambos loops en paralelo
    discovery_task = asyncio.create_task(discovery_loop())
    hot_task = asyncio.create_task(hot_loop())
    
    background_tasks = [discovery_task, hot_task]
    
    logger.info("✅ Scanner started (discovery + hot loops)")
    
    return {
        "status": "started",
        "loops": ["discovery (10s)", "hot (1s)"]
    }


@app.post("/api/scanner/stop")
async def stop_scanner():
    """Stop the scanner"""
    global background_tasks, is_running
    
    if not is_running:
        return {"status": "not_running"}
    
    is_running = False
    
    # Cancelar ambos tasks
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    background_tasks = []
    
    logger.info("Scanner stopped")
    
    return {"status": "stopped"}


@app.get("/api/scanner/status")
async def get_scanner_status():
    """Get scanner status"""
    stats = await scanner_engine.get_stats()
    
    return {
        "is_running": is_running,
        "stats": stats
    }


@app.post("/api/scanner/scan-once")
async def scan_once():
    """Run a single scan (for testing)"""
    try:
        result = await scanner_engine.run_scan()
        
        if not result:
            return {"status": "no_data"}
        
        return {
            "status": "success",
            "result": result.model_dump()
        }
    
    except Exception as e:
        logger.error("Error running scan", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scanner/filtered", response_model=List[ScannerTicker])
async def get_filtered_tickers(limit: int = 100):
    """Get currently filtered tickers"""
    try:
        tickers = await scanner_engine.get_filtered_tickers(limit=limit)
        return tickers
    
    except Exception as e:
        logger.error("Error getting filtered tickers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/filters", response_model=List[FilterConfig])
async def get_filters():
    """Get all configured filters"""
    try:
        filters = await scanner_engine.get_filters()
        return filters
    
    except Exception as e:
        logger.error("Error getting filters", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/filters/reload")
async def reload_filters():
    """Reload filters from database"""
    try:
        await scanner_engine.reload_filters()
        filters = await scanner_engine.get_filters()
        
        return {
            "status": "reloaded",
            "count": len(filters)
        }
    
    except Exception as e:
        logger.error("Error reloading filters", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_detailed_stats():
    """Get detailed scanner statistics"""
    try:
        stats = await scanner_engine.get_stats()
        return stats
    
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# SCANNER CATEGORIES (NUEVO - Sistema Profesional)
# =============================================

@app.get("/api/categories")
async def get_available_categories():
    """
    Lista todas las categorías de scanners disponibles
    
    Returns:
        Lista de categorías con descripciones
    """
    return {
        "categories": [
            {
                "name": "gappers_up",
                "display_name": "Gap Up",
                "description": "Tickers con gap up ≥ 2% desde cierre anterior"
            },
            {
                "name": "gappers_down",
                "display_name": "Gap Down",
                "description": "Tickers con gap down ≤ -2% desde cierre anterior"
            },
            {
                "name": "momentum_up",
                "display_name": "Momentum Alcista",
                "description": "Momentum fuerte alcista (cambio ≥ 3%)"
            },
            {
                "name": "momentum_down",
                "display_name": "Momentum Bajista",
                "description": "Momentum fuerte bajista (cambio ≤ -3%)"
            },
            {
                "name": "anomalies",
                "display_name": "Anomalías",
                "description": "Patrones inusuales (RVOL ≥ 3.0)"
            },
            {
                "name": "new_highs",
                "display_name": "Nuevos Máximos",
                "description": "Nuevos máximos del día"
            },
            {
                "name": "new_lows",
                "display_name": "Nuevos Mínimos",
                "description": "Nuevos mínimos del día"
            },
            {
                "name": "winners",
                "display_name": "Mayores Ganadores",
                "description": "Top gainers (cambio ≥ 5%)"
            },
            {
                "name": "losers",
                "display_name": "Mayores Perdedores",
                "description": "Top losers (cambio ≤ -5%)"
            },
            {
                "name": "high_volume",
                "display_name": "Alto Volumen",
                "description": "Volumen inusualmente alto (RVOL ≥ 2.0)"
            },
            {
                "name": "reversals",
                "display_name": "Reversals",
                "description": "Cambios de dirección significativos"
            }
        ]
    }


@app.get("/api/categories/stats")
async def get_categories_stats():
    """
    Obtiene estadísticas de TODAS las categorías
    
    IMPORTANTE: Este endpoint debe ir ANTES del parametrizado
    
    Returns:
        Dict con cantidad de tickers en cada categoría
    """
    try:
        stats = await scanner_engine.get_category_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "session": scanner_engine.current_session,
            "categories": stats
        }
    
    except Exception as e:
        logger.error("Error getting categories stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories/{category_name}")
async def get_category_tickers(category_name: str, limit: int = 20):
    """
    Obtiene tickers de una categoría específica
    
    Args:
        category_name: Nombre de la categoría (gappers_up, momentum_up, etc.)
        limit: Número máximo de resultados (default: 20)
    
    Returns:
        Lista de tickers rankeados para esa categoría
    """
    try:
        # Validar categoría
        try:
            category = ScannerCategory(category_name)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category: {category_name}. Use /api/categories to see available categories."
            )
        
        # Obtener tickers de la categoría
        tickers = await scanner_engine.get_category(category, limit=limit)
        
        return {
            "category": category_name,
            "count": len(tickers),
            "limit": limit,
            "tickers": tickers
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting category tickers", category=category_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/categories/stats")
async def get_categories_stats():
    """
    Obtiene estadísticas de TODAS las categorías
    
    Returns:
        Dict con cantidad de tickers en cada categoría
    """
    try:
        stats = await scanner_engine.get_category_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "session": scanner_engine.current_session,
            "categories": stats
        }
    
    except Exception as e:
        logger.error("Error getting categories stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/gappers")
async def get_gappers(direction: str = "both", limit: int = 20):
    """
    🔥 ENDPOINT ESPECIALIZADO PARA GAPPERS
    
    Obtiene los mayores gap up/down del mercado
    
    Args:
        direction: 'up', 'down', o 'both'
        limit: Top N resultados (default: 200)
    
    Returns:
        Lista de tickers con mayor gap
    """
    try:
        if direction not in ['up', 'down', 'both']:
            raise HTTPException(status_code=400, detail="direction must be 'up', 'down', or 'both'")
        
        result = {}
        
        if direction in ['up', 'both']:
            gappers_up = await scanner_engine.get_category(ScannerCategory.GAPPERS_UP, limit=limit)
            result['gappers_up'] = {
                "count": len(gappers_up),
                "tickers": gappers_up
            }
        
        if direction in ['down', 'both']:
            gappers_down = await scanner_engine.get_category(ScannerCategory.GAPPERS_DOWN, limit=limit)
            result['gappers_down'] = {
                "count": len(gappers_down),
                "tickers": gappers_down
            }
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting gappers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================================
# ENTRY POINT
# =============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.scanner_port,
        reload=settings.debug
    )

