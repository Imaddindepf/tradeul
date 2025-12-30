#!/usr/bin/env python3
"""
Pipeline ULTRA Optimizado v2 - Funciona con 16GB RAM

Estrategia:
1. NO crear índices en DuckDB (causa OOM)
2. Cargar parquets directamente en queries (lazy loading)
3. Procesar noticias en batches de 5000
4. Usar JOINs con filtros de fecha para reducir datos
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import duckdb
from tqdm import tqdm

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
BASE_DIR = Path("/home/ubuntu/news-alpha-engine")
DATA_DIR = BASE_DIR / "data"
MINUTE_BARS_DIR = DATA_DIR / "price_data" / "flatfiles_minute"
OUTPUT_DIR = DATA_DIR / "professional"

# Límite de memoria para DuckDB (10GB de 16GB disponibles)
DUCKDB_MEMORY_LIMIT = "10GB"
BATCH_SIZE = 5000  # Noticias por batch

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "pipeline_v2.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# =============================================================================
# FUNCIONES
# =============================================================================

def load_news_with_exact_time():
    """Cargar noticias con timestamp exacto"""
    # Buscar archivo de noticias (priorizar professional, luego data)
    news_file = OUTPUT_DIR / "news_all_sessions.parquet"
    if not news_file.exists():
        news_file = DATA_DIR / "news_filtered_pro.parquet"
    if not news_file.exists():
        log.error(f"No existe archivo de noticias")
        sys.exit(1)
    log.info(f"📁 Usando: {news_file}")
    
    df = pd.read_parquet(news_file)
    log.info(f"📰 Noticias cargadas: {len(df):,}")
    
    # Normalizar columna de timestamp
    if 'published_ts' in df.columns:
        df['timestamp'] = pd.to_datetime(df['published_ts'])
    elif 'timestamp' not in df.columns:
        log.error("No hay columna de timestamp")
        sys.exit(1)
    
    # Asegurar que timestamp es datetime UTC
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
    
    # Extraer fecha para filtrar parquets
    df['date'] = df['timestamp'].dt.date
    
    return df


def get_available_dates():
    """Obtener fechas disponibles de minute bars"""
    parquet_files = list(MINUTE_BARS_DIR.glob("*.parquet"))
    dates = []
    for f in parquet_files:
        try:
            date_str = f.stem  # YYYY-MM-DD
            dates.append(datetime.strptime(date_str, "%Y-%m-%d").date())
        except:
            continue
    return set(dates)


def calculate_impact_for_batch(conn, news_batch, available_dates):
    """
    Calcular impacto para un batch de noticias usando DuckDB.
    
    Estrategia: Para cada fecha única en el batch, cargar ese parquet
    y hacer JOIN con las noticias de ese día.
    """
    results = []
    
    # Agrupar noticias por fecha
    news_batch['date'] = pd.to_datetime(news_batch['timestamp']).dt.date
    dates_in_batch = news_batch['date'].unique()
    
    for date in dates_in_batch:
        if date not in available_dates:
            continue
            
        # Noticias de este día
        day_news = news_batch[news_batch['date'] == date].copy()
        if len(day_news) == 0:
            continue
        
        # Cargar parquet de este día
        parquet_path = MINUTE_BARS_DIR / f"{date}.parquet"
        if not parquet_path.exists():
            continue
        
        try:
            # Registrar el parquet como vista temporal
            # window_start está en nanosegundos epoch, convertir a timestamp
            conn.execute(f"""
                CREATE OR REPLACE TEMP VIEW bars AS 
                SELECT 
                    ticker,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    to_timestamp(window_start / 1000000000) as timestamp
                FROM read_parquet('{parquet_path}')
            """)
            
            # Para cada noticia, calcular impacto
            for idx, news in day_news.iterrows():
                ticker = news['ticker']
                ts = news['timestamp']
                
                # Convertir a timestamp EST (mercado)
                ts_utc = pd.Timestamp(ts)
                if ts_utc.tzinfo is None:
                    ts_utc = ts_utc.tz_localize('UTC')
                ts_est = ts_utc.tz_convert('America/New_York')
                
                # Buscar precio en el momento de la noticia
                ts_str = ts_est.strftime('%Y-%m-%d %H:%M:%S')
                
                query = f"""
                    SELECT timestamp, open, high, low, close, volume
                    FROM bars
                    WHERE ticker = '{ticker}'
                    AND timestamp >= '{ts_str}'
                    ORDER BY timestamp
                    LIMIT 100
                """
                
                bars_df = conn.execute(query).fetchdf()
                
                if len(bars_df) == 0:
                    continue
                
                # Precio T0 (momento de la noticia)
                price_t0 = bars_df.iloc[0]['close']
                
                # Calcular impactos en diferentes horizontes
                impact_5min = None
                impact_15min = None
                impact_30min = None
                impact_1h = None
                
                # 5 minutos (~5 barras)
                if len(bars_df) >= 5:
                    price_5min = bars_df.iloc[4]['close']
                    impact_5min = (price_5min - price_t0) / price_t0 * 100
                
                # 15 minutos (~15 barras)
                if len(bars_df) >= 15:
                    price_15min = bars_df.iloc[14]['close']
                    impact_15min = (price_15min - price_t0) / price_t0 * 100
                
                # 30 minutos (~30 barras)
                if len(bars_df) >= 30:
                    price_30min = bars_df.iloc[29]['close']
                    impact_30min = (price_30min - price_t0) / price_t0 * 100
                
                # 1 hora (~60 barras)
                if len(bars_df) >= 60:
                    price_1h = bars_df.iloc[59]['close']
                    impact_1h = (price_1h - price_t0) / price_t0 * 100
                
                # ATR intradiario (de las primeras 60 barras disponibles)
                atr_bars = bars_df.head(60)
                if len(atr_bars) > 1:
                    tr = np.maximum(
                        atr_bars['high'] - atr_bars['low'],
                        np.maximum(
                            abs(atr_bars['high'] - atr_bars['close'].shift(1)),
                            abs(atr_bars['low'] - atr_bars['close'].shift(1))
                        )
                    )
                    atr = tr.mean()
                    atr_pct = (atr / price_t0) * 100 if price_t0 > 0 else None
                else:
                    atr_pct = None
                
                results.append({
                    'news_id': news.get('id', str(idx)),
                    'ticker': ticker,
                    'timestamp': ts,
                    'title': news.get('title', '') if 'title' in news.index else '',
                    'price_t0': price_t0,
                    'impact_5min': impact_5min,
                    'impact_15min': impact_15min,
                    'impact_30min': impact_30min,
                    'impact_1h': impact_1h,
                    'atr_pct': atr_pct,
                    'session': news.get('session', '') if 'session' in news.index else '',
                })
                
        except Exception as e:
            log.warning(f"Error procesando {date}: {e}")
            continue
    
    return results


def main():
    log.info("=" * 70)
    log.info("🚀 NEWS ALPHA ENGINE - PIPELINE OPTIMIZADO v2")
    log.info(f"Iniciado: {datetime.now()}")
    log.info("=" * 70)
    
    # Crear conexión DuckDB en memoria con límite
    log.info(f"🦆 Configurando DuckDB (límite: {DUCKDB_MEMORY_LIMIT})")
    conn = duckdb.connect(":memory:")
    conn.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT}'")
    conn.execute("SET threads = 4")
    
    # Cargar noticias
    news_df = load_news_with_exact_time()
    
    # Obtener fechas disponibles
    available_dates = get_available_dates()
    log.info(f"📅 Días de minute bars disponibles: {len(available_dates)}")
    
    # Filtrar noticias a solo fechas con datos
    news_df = news_df[news_df['date'].isin(available_dates)]
    log.info(f"📰 Noticias con datos de precios: {len(news_df):,}")
    
    if len(news_df) == 0:
        log.error("❌ No hay noticias con datos de precios disponibles")
        return
    
    # Procesar en batches
    all_results = []
    n_batches = (len(news_df) + BATCH_SIZE - 1) // BATCH_SIZE
    
    log.info(f"📊 Procesando {len(news_df):,} noticias en {n_batches} batches de {BATCH_SIZE}")
    
    for i in tqdm(range(n_batches), desc="Procesando batches"):
        start_idx = i * BATCH_SIZE
        end_idx = min((i + 1) * BATCH_SIZE, len(news_df))
        batch = news_df.iloc[start_idx:end_idx]
        
        batch_results = calculate_impact_for_batch(conn, batch, available_dates)
        all_results.extend(batch_results)
        
        # Log progreso cada 10 batches
        if (i + 1) % 10 == 0:
            log.info(f"  Batch {i+1}/{n_batches}: {len(all_results):,} resultados")
    
    conn.close()
    
    if len(all_results) == 0:
        log.error("❌ No se calcularon impactos")
        return
    
    # Crear DataFrame de resultados
    results_df = pd.DataFrame(all_results)
    log.info(f"✅ Impactos calculados: {len(results_df):,}")
    
    # Normalizar por ATR
    for col in ['impact_5min', 'impact_15min', 'impact_30min', 'impact_1h']:
        norm_col = f"{col}_atr"
        results_df[norm_col] = results_df[col] / results_df['atr_pct']
        results_df[norm_col] = results_df[norm_col].replace([np.inf, -np.inf], np.nan)
    
    # Clasificar impacto (basado en 15min normalizado por ATR)
    def classify_impact(row):
        val = row.get('impact_15min_atr')
        if pd.isna(val):
            return 'UNKNOWN'
        abs_val = abs(val)
        if abs_val >= 2.0:  # >= 2 ATRs
            return 'HIGH'
        elif abs_val >= 1.0:  # >= 1 ATR
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def classify_direction(row):
        val = row.get('impact_15min')
        if pd.isna(val):
            return 'UNKNOWN'
        if val > 0.1:
            return 'UP'
        elif val < -0.1:
            return 'DOWN'
        else:
            return 'NEUTRAL'
    
    results_df['impact_class'] = results_df.apply(classify_impact, axis=1)
    results_df['direction'] = results_df.apply(classify_direction, axis=1)
    
    # Estadísticas
    log.info("\n📊 ESTADÍSTICAS DE IMPACTO:")
    log.info(f"   Total con impacto calculado: {len(results_df):,}")
    
    valid_impact = results_df[results_df['impact_15min'].notna()]
    log.info(f"   Con impacto 15min válido: {len(valid_impact):,}")
    
    if len(valid_impact) > 0:
        log.info(f"\n   Distribución de clases:")
        for cls in ['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']:
            count = len(results_df[results_df['impact_class'] == cls])
            pct = count / len(results_df) * 100
            log.info(f"      {cls}: {count:,} ({pct:.1f}%)")
        
        log.info(f"\n   Distribución de dirección:")
        for dir in ['UP', 'DOWN', 'NEUTRAL', 'UNKNOWN']:
            count = len(results_df[results_df['direction'] == dir])
            pct = count / len(results_df) * 100
            log.info(f"      {dir}: {count:,} ({pct:.1f}%)")
        
        log.info(f"\n   Impacto 15min (%):")
        log.info(f"      Media: {valid_impact['impact_15min'].mean():.3f}%")
        log.info(f"      Std: {valid_impact['impact_15min'].std():.3f}%")
        log.info(f"      Min: {valid_impact['impact_15min'].min():.3f}%")
        log.info(f"      Max: {valid_impact['impact_15min'].max():.3f}%")
    
    # Guardar resultados
    output_file = OUTPUT_DIR / "impact_intraday_v2.parquet"
    results_df.to_parquet(output_file, index=False)
    log.info(f"\n💾 Guardado: {output_file}")
    
    log.info("\n" + "=" * 70)
    log.info("✅ PIPELINE COMPLETADO")
    log.info("=" * 70)


if __name__ == "__main__":
    main()

