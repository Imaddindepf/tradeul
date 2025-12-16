#!/usr/bin/env python3
"""
Script para enriquecer metadata de tickers en tickers_unified.

SOLO actualiza la tabla tickers_unified (y por ende la vista ticker_metadata).
NO afecta otras tablas como volume_slots, market_data_daily, etc.

Uso:
    python enrich_tickers_metadata.py                    # Enriquece todos los que faltan (limit 500)
    python enrich_tickers_metadata.py --limit 100        # Limitar a 100 símbolos
    python enrich_tickers_metadata.py --symbol CETY      # Enriquecer un símbolo específico
    python enrich_tickers_metadata.py --all              # Enriquecer TODOS (sin límite)
    python enrich_tickers_metadata.py --dry-run          # Solo mostrar qué haría, sin cambios
"""

import asyncio
import argparse
import os
import sys
from typing import Optional, Dict, List
from datetime import datetime

import httpx
import asyncpg

# Configuración
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "vjzI76TMiepqrMZKphpfs3SA54JFkhEx")
FMP_API_KEY = os.getenv("FMP_API_KEY", "CKIRTsvk5eIpetoB8FbvOuw2wW8kNJ5B")

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "tradeul")
DB_USER = os.getenv("POSTGRES_USER", "tradeul_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "tradeul_password_secure_123")


class TickerEnricher:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db_pool: Optional[asyncpg.Pool] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # Estadísticas
        self.stats = {
            "processed": 0,
            "enriched": 0,
            "polygon_success": 0,
            "fmp_fallback": 0,
            "failed": 0,
            "skipped": 0
        }
    
    async def connect(self):
        """Conectar a BD y crear cliente HTTP"""
        print(f"🔌 Conectando a BD: {DB_HOST}:{DB_PORT}/{DB_NAME}")
        self.db_pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            min_size=2,
            max_size=10
        )
        self.http_client = httpx.AsyncClient(timeout=15.0)
        print("✅ Conectado")
    
    async def close(self):
        """Cerrar conexiones"""
        if self.http_client:
            await self.http_client.aclose()
        if self.db_pool:
            await self.db_pool.close()
    
    async def get_symbols_to_enrich(self, limit: Optional[int] = 500, symbol: Optional[str] = None) -> List[str]:
        """Obtener símbolos que necesitan enriquecimiento (incluye company_name y exchange)"""
        async with self.db_pool.acquire() as conn:
            if symbol:
                # Símbolo específico
                row = await conn.fetchrow(
                    "SELECT symbol FROM tickers_unified WHERE symbol = $1",
                    symbol.upper()
                )
                return [row['symbol']] if row else []
            
            # Buscar símbolos que necesitan enriquecimiento
            # INCLUYE company_name y exchange como campos a verificar
            query = """
                SELECT symbol
                FROM tickers_unified
                WHERE is_actively_trading = true
                  AND (
                    company_name IS NULL OR company_name = ''
                    OR exchange IS NULL OR exchange = ''
                    OR market_cap IS NULL
                    OR sector IS NULL
                    OR shares_outstanding IS NULL
                    OR cik IS NULL
                  )
                ORDER BY symbol
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            rows = await conn.fetch(query)
            return [row['symbol'] for row in rows]
    
    async def fetch_from_polygon(self, symbol: str, retries: int = 2) -> Optional[Dict]:
        """Obtener datos de Polygon API con reintentos"""
        url = f"https://api.polygon.io/v3/reference/tickers/{symbol}"
        
        for attempt in range(retries + 1):
            try:
                resp = await self.http_client.get(
                    url,
                    params={"apiKey": POLYGON_API_KEY}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get('results')
                elif resp.status_code == 429:
                    await asyncio.sleep(1 + attempt)
                elif resp.status_code == 404:
                    return None  # No reintentar 404
            except Exception as e:
                if attempt == retries:
                    pass  # Silenciar en último intento
                await asyncio.sleep(0.5)
        
        return None
    
    async def fetch_from_fmp(self, symbol: str, retries: int = 2) -> Optional[Dict]:
        """Obtener datos de FMP API (fallback) con reintentos"""
        url = f"https://financialmodelingprep.com/api/v3/profile/{symbol}"
        
        for attempt in range(retries + 1):
            try:
                resp = await self.http_client.get(
                    url,
                    params={"apikey": FMP_API_KEY}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if data and len(data) > 0:
                        return data[0]
                    return None
                elif resp.status_code == 429:
                    await asyncio.sleep(1 + attempt)
                elif resp.status_code == 404:
                    return None
            except Exception as e:
                if attempt == retries:
                    pass
                await asyncio.sleep(0.5)
        
        return None
    
    async def enrich_symbol(self, symbol: str) -> bool:
        """Enriquecer un símbolo con datos de Polygon + FMP fallback"""
        self.stats["processed"] += 1
        
        # 1. Intentar Polygon primero
        polygon_data = await self.fetch_from_polygon(symbol)
        used_fmp = False
        
        # 2. Extraer campos de Polygon (INCLUYE company_name y exchange)
        company_name = polygon_data.get('name') if polygon_data else None
        exchange = polygon_data.get('primary_exchange') if polygon_data else None
        market_cap = polygon_data.get('market_cap') if polygon_data else None
        shares_outstanding = (
            polygon_data.get('share_class_shares_outstanding') or 
            polygon_data.get('weighted_shares_outstanding')
        ) if polygon_data else None
        float_shares = polygon_data.get('weighted_shares_outstanding') if polygon_data else None
        sector = polygon_data.get('sic_description') if polygon_data else None
        industry = polygon_data.get('sic_description') if polygon_data else None
        cik = polygon_data.get('cik') if polygon_data else None
        description = polygon_data.get('description') if polygon_data else None
        homepage_url = polygon_data.get('homepage_url') if polygon_data else None
        total_employees = polygon_data.get('total_employees') if polygon_data else None
        beta = None
        
        # 3. Si faltan campos críticos, usar FMP como fallback
        needs_fmp = (
            company_name is None or
            exchange is None or
            market_cap is None or 
            shares_outstanding is None or 
            sector is None or
            cik is None
        )
        
        if needs_fmp:
            fmp_data = await self.fetch_from_fmp(symbol)
            if fmp_data:
                used_fmp = True
                # Completar campos faltantes con FMP
                company_name = company_name or fmp_data.get('companyName')
                exchange = exchange or fmp_data.get('exchange')
                market_cap = market_cap or fmp_data.get('mktCap')
                shares_outstanding = shares_outstanding or fmp_data.get('sharesOutstanding')
                float_shares = float_shares or fmp_data.get('sharesOutstanding')
                sector = sector or fmp_data.get('sector')
                industry = industry or fmp_data.get('industry')
                cik = cik or fmp_data.get('cik')
                description = description or fmp_data.get('description')
                homepage_url = homepage_url or fmp_data.get('website')
                total_employees = total_employees or self._safe_int(fmp_data.get('fullTimeEmployees'))
                beta = fmp_data.get('beta')
        
        # 4. Si no tenemos nada útil, saltar
        if not (company_name or market_cap or shares_outstanding or sector or cik):
            self.stats["skipped"] += 1
            return False
        
        # 5. Actualizar BD (o simular en dry-run)
        if self.dry_run:
            print(f"  [DRY-RUN] Actualizaría: name={company_name}, exchange={exchange}, mktcap={market_cap}, sector={sector}")
            self.stats["enriched"] += 1
            return True
        
        try:
            await self._update_ticker(
                symbol=symbol,
                company_name=company_name,
                exchange=exchange,
                market_cap=market_cap,
                float_shares=float_shares,
                shares_outstanding=shares_outstanding,
                sector=sector,
                industry=industry,
                cik=cik,
                description=description,
                homepage_url=homepage_url,
                total_employees=total_employees,
                beta=beta
            )
            
            self.stats["enriched"] += 1
            if used_fmp:
                self.stats["fmp_fallback"] += 1
            else:
                self.stats["polygon_success"] += 1
            
            return True
            
        except Exception as e:
            print(f"  ❌ Error actualizando BD: {e}")
            self.stats["failed"] += 1
            return False
    
    async def _update_ticker(
        self,
        symbol: str,
        company_name: Optional[str],
        exchange: Optional[str],
        market_cap: Optional[float],
        float_shares: Optional[int],
        shares_outstanding: Optional[int],
        sector: Optional[str],
        industry: Optional[str],
        cik: Optional[str],
        description: Optional[str],
        homepage_url: Optional[str],
        total_employees: Optional[int],
        beta: Optional[float]
    ):
        """Actualizar ticker en tickers_unified (incluye company_name y exchange)"""
        query = """
            UPDATE tickers_unified SET
                company_name = COALESCE($2, company_name),
                exchange = COALESCE($3, exchange),
                market_cap = COALESCE($4, market_cap),
                float_shares = COALESCE($5, float_shares),
                shares_outstanding = COALESCE($6, shares_outstanding),
                sector = COALESCE($7, sector),
                industry = COALESCE($8, industry),
                cik = COALESCE($9, cik),
                description = COALESCE($10, description),
                homepage_url = COALESCE($11, homepage_url),
                total_employees = COALESCE($12, total_employees),
                beta = COALESCE($13, beta),
                updated_at = NOW()
            WHERE symbol = $1
        """
        
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                query,
                symbol,
                company_name,
                exchange,
                int(market_cap) if market_cap else None,
                int(float_shares) if float_shares else None,
                int(shares_outstanding) if shares_outstanding else None,
                sector,
                industry,
                cik,
                description,
                homepage_url,
                int(total_employees) if total_employees else None,
                float(beta) if beta else None
            )
    
    def _safe_int(self, value) -> Optional[int]:
        """Convertir valor a int de forma segura"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                value = ''.join(filter(str.isdigit, value))
            return int(value) if value else None
        except (ValueError, TypeError):
            return None
    
    async def run(self, limit: Optional[int] = 500, symbol: Optional[str] = None, concurrency: int = 30):
        """Ejecutar enriquecimiento"""
        await self.connect()
        
        try:
            # Obtener símbolos
            print(f"\n🔍 Buscando símbolos que necesitan enriquecimiento...")
            symbols = await self.get_symbols_to_enrich(limit=limit, symbol=symbol)
            
            if not symbols:
                print("✅ No hay símbolos que enriquecer")
                return
            
            print(f"📋 Encontrados {len(symbols)} símbolos para enriquecer")
            print(f"⚡ Concurrencia: {concurrency} requests simultáneos")
            
            if self.dry_run:
                print("🔸 MODO DRY-RUN: No se harán cambios reales")
            
            print("\n" + "="*60)
            
            # Procesar en paralelo con semáforo
            semaphore = asyncio.Semaphore(concurrency)
            completed = 0
            
            async def process_symbol(sym: str):
                nonlocal completed
                async with semaphore:
                    success = await self.enrich_symbol(sym)
                    completed += 1
                    if completed % 100 == 0 or completed == len(symbols):
                        print(f"  Progreso: {completed}/{len(symbols)} ({100*completed//len(symbols)}%)")
                    return success
            
            print("🚀 Procesando en paralelo...")
            tasks = [process_symbol(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Contar errores de ejecución
            errors = sum(1 for r in results if isinstance(r, Exception))
            if errors > 0:
                self.stats['failed'] += errors
            
            # Mostrar estadísticas
            print("\n" + "="*60)
            print("📊 ESTADÍSTICAS:")
            print(f"   Procesados:     {self.stats['processed']}")
            print(f"   Enriquecidos:   {self.stats['enriched']}")
            print(f"   - Polygon:      {self.stats['polygon_success']}")
            print(f"   - FMP fallback: {self.stats['fmp_fallback']}")
            print(f"   Saltados:       {self.stats['skipped']}")
            print(f"   Fallidos:       {self.stats['failed']}")
            
        finally:
            await self.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Enriquecer metadata de tickers en tickers_unified"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=500,
        help="Límite de símbolos a procesar (default: 500)"
    )
    parser.add_argument(
        "--symbol", "-s",
        type=str,
        help="Enriquecer un símbolo específico"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Procesar TODOS los símbolos (sin límite)"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Simular sin hacer cambios reales"
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=30,
        help="Requests simultáneos (default: 30)"
    )
    
    args = parser.parse_args()
    
    # Determinar límite
    limit = None if args.all else args.limit
    
    print("="*60)
    print("🚀 ENRIQUECEDOR DE METADATA DE TICKERS")
    print("="*60)
    print(f"   Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Límite:     {'Sin límite' if limit is None else limit}")
    print(f"   Símbolo:    {args.symbol or 'Todos los que necesiten'}")
    print(f"   Dry-run:    {'Sí' if args.dry_run else 'No'}")
    
    enricher = TickerEnricher(dry_run=args.dry_run)
    await enricher.run(limit=limit, symbol=args.symbol, concurrency=args.concurrency)


if __name__ == "__main__":
    asyncio.run(main())

