#!/usr/bin/env python3
"""
Script para cargar el universo de tickers desde Polygon
Usa el TickerUniverseLoader del Historical Service
"""

import sys
import os
import asyncio

# Añadir paths necesarios
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../shared'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../services/historical'))

# Ahora importar módulos
import structlog
from shared.config.settings import settings
from shared.utils.redis_client import RedisClient
from shared.utils.timescale_client import TimescaleClient

# Import ticker universe loader
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../services/historical'))
from ticker_universe_loader import TickerUniverseLoader


# Configure logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger()


async def main():
    """
    Main function to load ticker universe from Polygon
    """
    print("="*70)
    print("🚀 CARGA DE UNIVERSO DE TICKERS DESDE POLYGON")
    print("="*70)
    print()
    print("Fuente: Polygon /v3/reference/tickers")
    print("Filtros:")
    print("  - market: stocks")
    print("  - locale: us")
    print("  - active: true")
    print()
    print("="*70)
    print()
    
    # Initialize clients
    logger.info("initializing_clients")
    
    redis_client = RedisClient()
    timescale_client = TimescaleClient()
    
    try:
        # Connect
        print("📡 Conectando a Redis y TimescaleDB...")
        await redis_client.connect()
        await timescale_client.connect()
        print("✅ Conectado\n")
        
        # Create loader
        loader = TickerUniverseLoader(
            redis_client=redis_client,
            timescale_client=timescale_client,
            polygon_api_key=settings.POLYGON_API_KEY
        )
        
        # Load universe
        print("🔍 Obteniendo tickers desde Polygon...")
        print("   (esto puede tomar 2-3 minutos)\n")
        
        stats = await loader.load_universe()
        
        # Display stats
        print()
        print("="*70)
        print("✅ CARGA COMPLETADA")
        print("="*70)
        print()
        print(f"📊 Tickers obtenidos de Polygon:     {stats['fetched']:,}")
        print(f"💾 Guardados en Redis:                {stats['saved_redis']:,}")
        print(f"🗄️  Guardados en TimescaleDB:         {stats['saved_timescaledb']:,}")
        print(f"📝 Metadata actualizada:              {stats['updated_metadata']:,}")
        print()
        print("="*70)
        print()
        
        # Get current stats
        current_stats = await loader.get_universe_stats()
        
        print("📈 ESTADÍSTICAS ACTUALES:")
        print()
        print(f"   Redis:          {current_stats['redis_count']:,} tickers")
        print(f"   TimescaleDB:    {current_stats['timescaledb_active']:,} activos / {current_stats['timescaledb_total']:,} total")
        print(f"   Última actualización: {current_stats['last_update']}")
        print()
        print("="*70)
        print()
        
        # Next steps
        print("🎯 PRÓXIMOS PASOS:")
        print()
        print("1. El Historical Service enriquecerá estos tickers con datos de FMP:")
        print("   - Market cap")
        print("   - Float")
        print("   - Average volume")
        print("   - Sector/Industry")
        print()
        print("2. El Scanner Service usará este universo para filtrado")
        print()
        print("3. El sistema se actualizará automáticamente cada 24 horas")
        print()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Carga interrumpida por el usuario\n")
        return 1
        
    except Exception as e:
        logger.error("universe_load_failed", error=str(e))
        print(f"\n❌ Error: {e}\n")
        return 1
        
    finally:
        # Cleanup
        print("🧹 Cerrando conexiones...")
        await timescale_client.disconnect()
        await redis_client.disconnect()
        print("✅ Conexiones cerradas\n")


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

