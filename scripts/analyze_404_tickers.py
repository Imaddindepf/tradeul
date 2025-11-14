#!/usr/bin/env python3
"""
Script para analizar tickers que generan 404 en historical service
Identifica cuáles existen en Polygon y cuáles son fantasma
"""

import asyncio
import sys
import csv
from datetime import datetime
import httpx
import re

sys.path.append('/app')
from shared.config.settings import settings
from shared.utils.timescale_client import TimescaleClient
from shared.utils.logger import get_logger, configure_logging

configure_logging(service_name="analyze_404")
logger = get_logger(__name__)


async def get_404_tickers_from_logs(container_name: str = "tradeul_analytics") -> set:
    """Extrae tickers con 404 de los logs de analytics"""
    import subprocess
    
    cmd = f"docker logs {container_name} --tail 1000 2>&1 | grep '404 Not Found' | grep -o 'symbol=[A-Z]*' | cut -d= -f2 | sort | uniq"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    tickers = set(result.stdout.strip().split('\n'))
    tickers.discard('')  # Remove empty strings
    
    return tickers


async def check_ticker_in_polygon(symbol: str, api_key: str) -> dict:
    """Verifica si un ticker existe en Polygon API"""
    url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params={"apiKey": api_key})
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'OK':
                    results = data.get('results', {})
                    return {
                        'exists_in_polygon': True,
                        'name': results.get('name', 'N/A'),
                        'type': results.get('type', 'N/A'),
                        'market': results.get('market', 'N/A'),
                        'active': results.get('active', False),
                        'exchange': results.get('primary_exchange', 'N/A')
                    }
            
            return {'exists_in_polygon': False}
    
    except Exception as e:
        logger.error(f"Error checking {symbol}: {e}")
        return {'exists_in_polygon': False, 'error': str(e)}


async def check_ticker_in_db(symbol: str, db: TimescaleClient) -> dict:
    """Verifica si un ticker está en nuestras tablas"""
    try:
        # ticker_universe
        universe_row = await db.fetchrow(
            "SELECT is_active, last_seen FROM ticker_universe WHERE symbol = $1",
            symbol
        )
        
        # volume_slots
        slots_count = await db.fetchval(
            "SELECT COUNT(*) FROM volume_slots WHERE symbol = $1",
            symbol
        )
        
        # market_data_daily
        ohlc_count = await db.fetchval(
            "SELECT COUNT(*) FROM market_data_daily WHERE symbol = $1",
            symbol
        )
        
        return {
            'in_universe': universe_row is not None,
            'is_active': universe_row['is_active'] if universe_row else False,
            'last_seen': universe_row['last_seen'].isoformat() if universe_row else None,
            'volume_slots_count': slots_count,
            'ohlc_days_count': ohlc_count
        }
    
    except Exception as e:
        logger.error(f"Error checking {symbol} in DB: {e}")
        return {
            'in_universe': False,
            'volume_slots_count': 0,
            'ohlc_days_count': 0
        }


async def analyze_and_save_to_csv(output_file: str = "tickers_404_analysis.csv"):
    """Analiza todos los tickers con 404 y guarda en CSV"""
    
    logger.info("🔍 Iniciando análisis de tickers con 404...")
    
    # 1. Obtener tickers con 404 de los logs
    logger.info("Extrayendo tickers de logs...")
    tickers_404 = await get_404_tickers_from_logs()
    
    if not tickers_404:
        logger.info("No se encontraron tickers con 404 en los logs recientes")
        return
    
    logger.info(f"Encontrados {len(tickers_404)} tickers únicos con 404")
    
    # 2. Conectar a BD
    db = TimescaleClient()
    await db.connect()
    
    # 3. Analizar cada ticker
    results = []
    
    for i, symbol in enumerate(sorted(tickers_404)):
        logger.info(f"Analizando {symbol} ({i+1}/{len(tickers_404)})...")
        
        # Verificar en BD
        db_info = await check_ticker_in_db(symbol, db)
        
        # Verificar en Polygon
        polygon_info = await check_ticker_in_polygon(symbol, settings.POLYGON_API_KEY)
        
        # Combinar información
        result = {
            'symbol': symbol,
            'in_our_universe': db_info['in_universe'],
            'volume_slots_count': db_info['volume_slots_count'],
            'ohlc_days': db_info['ohlc_days_count'],
            'exists_in_polygon': polygon_info.get('exists_in_polygon', False),
            'polygon_name': polygon_info.get('name', 'N/A'),
            'polygon_type': polygon_info.get('type', 'N/A'),
            'polygon_active': polygon_info.get('active', False),
            'exchange': polygon_info.get('exchange', 'N/A'),
            'classification': 'UNKNOWN'
        }
        
        # Clasificar el ticker
        if not result['exists_in_polygon']:
            result['classification'] = 'FANTASMA'
        elif not result['in_our_universe']:
            result['classification'] = 'NUEVO_O_FALTANTE'
        elif result['volume_slots_count'] == 0:
            result['classification'] = 'EN_UNIVERSO_SIN_DATOS'
        
        results.append(result)
        
        # Rate limiting
        await asyncio.sleep(0.21)  # 5 req/seg
    
    await db.disconnect()
    
    # 4. Guardar en CSV
    logger.info(f"Guardando resultados en {output_file}...")
    
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = [
            'symbol', 'classification', 'in_our_universe', 'volume_slots_count',
            'ohlc_days', 'exists_in_polygon', 'polygon_name', 'polygon_type',
            'polygon_active', 'exchange'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for result in results:
            writer.writerow(result)
    
    # 5. Resumen
    logger.info("=" * 70)
    logger.info("RESUMEN DE ANÁLISIS")
    logger.info("=" * 70)
    logger.info(f"Total tickers analizados: {len(results)}")
    
    fantasma = [r for r in results if r['classification'] == 'FANTASMA']
    nuevos = [r for r in results if r['classification'] == 'NUEVO_O_FALTANTE']
    sin_datos = [r for r in results if r['classification'] == 'EN_UNIVERSO_SIN_DATOS']
    
    logger.info(f"")
    logger.info(f"FANTASMA (no existen en Polygon): {len(fantasma)}")
    for r in fantasma:
        logger.info(f"  - {r['symbol']}")
    
    logger.info(f"")
    logger.info(f"NUEVOS/FALTANTES (existen en Polygon, no en universo): {len(nuevos)}")
    for r in nuevos:
        logger.info(f"  - {r['symbol']}: {r['polygon_name'][:40]}")
    
    logger.info(f"")
    logger.info(f"EN UNIVERSO SIN DATOS: {len(sin_datos)}")
    for r in sin_datos:
        logger.info(f"  - {r['symbol']}")
    
    logger.info("")
    logger.info(f"✅ Archivo guardado: {output_file}")
    logger.info("")
    logger.info("RECOMENDACIONES:")
    if fantasma:
        logger.info(f"  - {len(fantasma)} fantasma: Implementar cache negativo")
    if nuevos:
        logger.info(f"  - {len(nuevos)} nuevos: Actualizar universo o agregar manualmente")


if __name__ == "__main__":
    output_file = "/app/scripts/tickers_404_analysis.csv"
    asyncio.run(analyze_and_save_to_csv(output_file))
    print(f"\n✅ Análisis completado. Ver: {output_file}")

