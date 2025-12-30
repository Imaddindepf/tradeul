#!/usr/bin/env python3
"""
Pipeline ULTRA RÁPIDO v3 - Optimizado con procesamiento vectorizado

MEJORA CLAVE: En lugar de 1 query por noticia, procesa TODAS las noticias 
de un día de una sola vez usando operaciones vectorizadas de Pandas.

Estimado: ~30 minutos (vs 6 horas de v2)
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from tqdm import tqdm

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
BASE_DIR = Path("/home/ubuntu/news-alpha-engine")
DATA_DIR = BASE_DIR / "data"
MINUTE_BARS_DIR = DATA_DIR / "price_data" / "flatfiles_minute"
OUTPUT_DIR = DATA_DIR / "professional"

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "pipeline_v3.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


def load_news():
    """Cargar noticias con timestamp exacto"""
    news_file = OUTPUT_DIR / "news_all_sessions.parquet"
    if not news_file.exists():
        news_file = DATA_DIR / "news_filtered_pro.parquet"
    
    df = pd.read_parquet(news_file)
    log.info(f"📰 Noticias cargadas: {len(df):,}")
    
    # Normalizar timestamp
    if 'published_ts' in df.columns:
        df['timestamp'] = pd.to_datetime(df['published_ts'])
    
    # Asegurar UTC
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
    else:
        df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
    
    # Convertir a EST para alinear con barras
    df['timestamp_est'] = df['timestamp'].dt.tz_convert('America/New_York')
    df['date'] = df['timestamp_est'].dt.date
    
    return df


def get_available_dates():
    """Obtener fechas disponibles"""
    files = list(MINUTE_BARS_DIR.glob("*.parquet"))
    dates = {}
    for f in files:
        try:
            d = datetime.strptime(f.stem, "%Y-%m-%d").date()
            dates[d] = f
        except:
            continue
    return dates


def calculate_atr_from_bars(bars_df, periods=14):
    """Calcular ATR intradiario desde minute bars"""
    if len(bars_df) < 2:
        return np.nan
    
    high = bars_df['high'].values
    low = bars_df['low'].values
    close = bars_df['close'].values
    
    # True Range
    tr1 = high - low
    tr2 = np.abs(high[1:] - close[:-1])
    tr3 = np.abs(low[1:] - close[:-1])
    
    tr = np.maximum(tr1[1:], np.maximum(tr2, tr3))
    
    if len(tr) < periods:
        return np.mean(tr) if len(tr) > 0 else np.nan
    
    return np.mean(tr[:periods])


def process_day(date, parquet_path, news_day):
    """
    Procesar todas las noticias de UN día de forma vectorizada.
    
    Estrategia:
    1. Cargar todas las barras del día
    2. Para cada ticker único en las noticias, extraer sus barras
    3. Para cada noticia, encontrar la barra más cercana y calcular impacto
    """
    results = []
    
    try:
        # Cargar barras del día
        bars_df = pd.read_parquet(parquet_path)
        
        # Convertir window_start a timestamp EST
        bars_df['timestamp'] = pd.to_datetime(bars_df['window_start'], unit='ns')
        bars_df['timestamp'] = bars_df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('America/New_York')
        
        # Ordenar por ticker y timestamp
        bars_df = bars_df.sort_values(['ticker', 'timestamp'])
        
        # Tickers únicos en las noticias de este día
        tickers_in_news = news_day['ticker'].unique()
        
        # Filtrar barras solo para tickers con noticias (GRAN OPTIMIZACIÓN)
        bars_filtered = bars_df[bars_df['ticker'].isin(tickers_in_news)]
        
        if len(bars_filtered) == 0:
            return results
        
        # Crear índice para búsqueda rápida
        bars_by_ticker = {t: g.reset_index(drop=True) for t, g in bars_filtered.groupby('ticker')}
        
        # Procesar cada noticia
        for _, news in news_day.iterrows():
            ticker = news['ticker']
            news_ts = news['timestamp_est']
            
            if ticker not in bars_by_ticker:
                continue
            
            ticker_bars = bars_by_ticker[ticker]
            
            # Encontrar índice de la barra >= timestamp de la noticia
            mask = ticker_bars['timestamp'] >= news_ts
            if not mask.any():
                continue
            
            start_idx = mask.idxmax()
            
            # Precio T0
            price_t0 = ticker_bars.loc[start_idx, 'close']
            if price_t0 <= 0 or pd.isna(price_t0):
                continue
            
            # Calcular impactos en diferentes horizontes
            impact_5min = None
            impact_15min = None
            impact_30min = None
            impact_1h = None
            
            # Barras disponibles después de la noticia
            bars_after = ticker_bars.loc[start_idx:]
            n_bars = len(bars_after)
            
            if n_bars >= 5:
                price_5 = bars_after.iloc[4]['close']
                impact_5min = ((price_5 - price_t0) / price_t0) * 100
            
            if n_bars >= 15:
                price_15 = bars_after.iloc[14]['close']
                impact_15min = ((price_15 - price_t0) / price_t0) * 100
            
            if n_bars >= 30:
                price_30 = bars_after.iloc[29]['close']
                impact_30min = ((price_30 - price_t0) / price_t0) * 100
            
            if n_bars >= 60:
                price_60 = bars_after.iloc[59]['close']
                impact_1h = ((price_60 - price_t0) / price_t0) * 100
            
            # ATR intradiario (primeras 60 barras)
            atr = calculate_atr_from_bars(bars_after.head(60))
            atr_pct = (atr / price_t0) * 100 if atr and price_t0 > 0 else None
            
            results.append({
                'news_id': news.get('id', ''),
                'ticker': ticker,
                'timestamp': news['timestamp'],
                'title': news.get('title', ''),
                'price_t0': price_t0,
                'impact_5min': impact_5min,
                'impact_15min': impact_15min,
                'impact_30min': impact_30min,
                'impact_1h': impact_1h,
                'atr_pct': atr_pct,
                'session': news.get('session', ''),
                'date': str(date),
            })
            
    except Exception as e:
        log.warning(f"Error procesando {date}: {e}")
    
    return results


def main():
    log.info("=" * 70)
    log.info("🚀 NEWS ALPHA ENGINE - PIPELINE v3 ULTRA RÁPIDO")
    log.info(f"Iniciado: {datetime.now()}")
    log.info("=" * 70)
    
    # Cargar noticias
    news_df = load_news()
    
    # Obtener fechas disponibles
    date_files = get_available_dates()
    log.info(f"📅 Días de minute bars: {len(date_files)}")
    
    # Filtrar noticias a fechas con datos
    news_df = news_df[news_df['date'].isin(date_files.keys())]
    log.info(f"📰 Noticias con datos de precios: {len(news_df):,}")
    
    # Agrupar por fecha
    news_by_date = news_df.groupby('date')
    dates_to_process = sorted(news_by_date.groups.keys())
    
    log.info(f"📆 Días a procesar: {len(dates_to_process)}")
    
    # Procesar día por día
    all_results = []
    
    for date in tqdm(dates_to_process, desc="Procesando días"):
        parquet_path = date_files.get(date)
        if not parquet_path:
            continue
        
        news_day = news_by_date.get_group(date)
        
        day_results = process_day(date, parquet_path, news_day)
        all_results.extend(day_results)
        
        # Log cada 50 días
        if len(dates_to_process) > 50 and dates_to_process.index(date) % 50 == 0:
            log.info(f"   Progreso: {dates_to_process.index(date)}/{len(dates_to_process)} días, {len(all_results):,} resultados")
    
    if len(all_results) == 0:
        log.error("❌ No se calcularon impactos")
        return
    
    # Crear DataFrame
    results_df = pd.DataFrame(all_results)
    log.info(f"✅ Impactos calculados: {len(results_df):,}")
    
    # Normalizar por ATR
    for col in ['impact_5min', 'impact_15min', 'impact_30min', 'impact_1h']:
        norm_col = f"{col}_atr"
        results_df[norm_col] = results_df[col] / results_df['atr_pct']
        results_df[norm_col] = results_df[norm_col].replace([np.inf, -np.inf], np.nan)
    
    # Clasificar impacto (15min normalizado por ATR)
    def classify_impact(val):
        if pd.isna(val):
            return 'UNKNOWN'
        abs_val = abs(val)
        if abs_val >= 2.0:
            return 'HIGH'
        elif abs_val >= 1.0:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    def classify_direction(val):
        if pd.isna(val):
            return 'UNKNOWN'
        if val > 0.1:
            return 'UP'
        elif val < -0.1:
            return 'DOWN'
        else:
            return 'NEUTRAL'
    
    results_df['impact_class'] = results_df['impact_15min_atr'].apply(classify_impact)
    results_df['direction'] = results_df['impact_15min'].apply(classify_direction)
    
    # Estadísticas
    log.info("\n" + "=" * 50)
    log.info("📊 ESTADÍSTICAS DE IMPACTO")
    log.info("=" * 50)
    
    valid = results_df[results_df['impact_15min'].notna()]
    log.info(f"Total con impacto válido: {len(valid):,}")
    
    log.info("\nDistribución de clases:")
    for cls in ['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']:
        count = len(results_df[results_df['impact_class'] == cls])
        pct = count / len(results_df) * 100 if len(results_df) > 0 else 0
        log.info(f"   {cls}: {count:,} ({pct:.1f}%)")
    
    log.info("\nDistribución de dirección:")
    for d in ['UP', 'DOWN', 'NEUTRAL', 'UNKNOWN']:
        count = len(results_df[results_df['direction'] == d])
        pct = count / len(results_df) * 100 if len(results_df) > 0 else 0
        log.info(f"   {d}: {count:,} ({pct:.1f}%)")
    
    if len(valid) > 0:
        log.info(f"\nImpacto 15min (%):")
        log.info(f"   Media: {valid['impact_15min'].mean():.4f}%")
        log.info(f"   Std: {valid['impact_15min'].std():.4f}%")
        log.info(f"   Min: {valid['impact_15min'].min():.4f}%")
        log.info(f"   Max: {valid['impact_15min'].max():.4f}%")
        
        high_impact = valid[valid['impact_class'] == 'HIGH']
        if len(high_impact) > 0:
            log.info(f"\nNoticias HIGH impact:")
            log.info(f"   Total: {len(high_impact):,}")
            log.info(f"   Movimiento medio: {high_impact['impact_15min'].abs().mean():.2f}%")
    
    # Guardar
    output_file = OUTPUT_DIR / "impact_intraday_v3.parquet"
    results_df.to_parquet(output_file, index=False)
    log.info(f"\n💾 Guardado: {output_file}")
    log.info(f"   Tamaño: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
    
    log.info("\n" + "=" * 70)
    log.info("✅ PIPELINE COMPLETADO")
    log.info(f"   Tiempo total: {datetime.now()}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()


